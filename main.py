# Copyright 2015 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START app]
import logging
import config
try:
    import simplejson as json
except ImportError:
    import json

from flask import Flask, render_template, send_file, request, Response, make_response
from gcloud import storage, datastore
from uuid import uuid4, UUID

# Push Notification Service
import apns

# Passkit Web Service
from passkit import PasskitWebService
from passgen import PassGenerator
import tasks


app = Flask(__name__)
app.config.from_object(config)
gstorage = storage.Client(project=app.config['PROJECT_ID'])
gds = datastore.Client(project=app.config['PROJECT_ID'])
passkit = PasskitWebService(datastoreClient=gds,
                            storageClient=gstorage)
passgen = PassGenerator()


# [START imgload_queue]
with app.app_context():
    imgload_queue = tasks.get_imgload_queue()
# [END imgload_queue]


@app.route('/')
def hello():

    # Queue load image task
    offerimg = request.args.get('offerImage')
    offerimgHR = request.args.get('offerImageHighRes')
    q = tasks.get_imgload_queue()
    q.enqueue(tasks.load_img, offerimg, offerimgHR)

    return render_template('index.html')


@app.route('/pass')
def send_pass():

    # Save authtoken to datastore
    pass_auth = 'vxwxd7J8AlNNFPS8k0a0FfUFtq0ewzFdc' # TEMP
    passkit.add_pass_authtoken(pass_auth)

    # Add pass to datastore
    pass_serial = uuid4().hex
    pass_entity = passkit.add_pass(pass_serial, pass_auth, request.args.get('uid'),
                                   request.args.get('fname'), request.args.get('lname'), request.args.get('zipcode'),
                                   request.args.get('offerImage'), request.args.get('offerImageHighRes'),
                                   request.args.get('offerText'), request.args.get('offerExpiration'))
    logging.error('SERIAL: {}'.format(pass_serial))

    # Generate pass file
    pkpass = passgen.generate(pass_entity)

    # Send pass file
    return send_file(pkpass, mimetype='application/vnd.apple.pkpass')


# [START Passkit Support]

@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>/<serialNumber>',
          methods=['POST', 'DELETE'])
def registration(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber):

    authTitle, authToken = request.headers['Authorization'].split()
    logging.error('PASSKIT AUTHTOKEN: {}'.format(authToken))

    # Authenticate
    if not passkit.authenticate_authtoken(authTitle, authToken):
        return 'Unauthorized request.', 401

    # Register
    if request.method == 'POST':
        pushToken = request.json['pushToken']
        logging.error('PASSKIT PUSHTOKEN: {}'.format(pushToken))
        status = passkit.register_pass_to_device(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber, pushToken)
        if status == 200:
            return 'Serial number already exists.', 200
        elif status == 201:
            return 'Registration successful.', 201
        else:
            return 'Bad request.', 400

    # Unregister
    else: #request.method == 'DELETE'
        status = passkit.unregister_pass_to_device(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber)
        if status == 200:
            return 'Unregistration successful.', 200
        else:
            return 'Bad request.', 400


@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>', methods=['GET'])
def get_serials_for_device(version, deviceLibraryIdentifier, passTypeIdentifier):

    updatedSinceTag = request.args.get('passesUpdatedSince')
    payload, status = passkit.get_serials_for_device(version, deviceLibraryIdentifier, passTypeIdentifier, updatedSinceTag)

    if status == 200:
        return payload, 200, {'Content-Type': 'application/json'}
    elif status == 204:
        return 'No matching passes.', 204
    else:
        return 'Bad request.', 400


@app.route('/passkit/<version>/passes/<passTypeIdentifier>/<serialNumber>', methods=['GET'])
def get_updated_pass_for_device(version, passTypeIdentifier, serialNumber):

    authTitle, authToken = request.headers['Authorization'].split()
    logging.error('PASSKIT AUTHTOKEN: {}'.format(authToken))

    # Authenticate
    if not passkit.authenticate_authtoken(authTitle, authToken):
        return 'Unauthorized request.', 401

    # Download new pass
    newpass_entity, status = passkit.get_updated_pass_for_device(version, passTypeIdentifier, serialNumber)
    newpkpass = passgen.generate(newpass_entity)

    if status == 200:
        return send_file(newpkpass, mimetype='application/vnd.apple.pkpass')
    elif status == 304:
        return 'Pass has not changed.', 304
    else:
        return 'Bad request.', 400

@app.route('/passkit/<version>/log', methods=['POST'])
def log(version):

    # Retrieve and log
    logs = request.get_json()['logs']
    logging.error('PASSKIT LOG {}: '.format(version, logs))
    return "Recorded logs.", 200

# [END Passkit Support]


# [START PUSH NOTIFICATION SUPPORT]

@app.route('/push/<deviceLibraryIdentifier>')
def push_notification(deviceLibraryIdentifier):

    import ssl, OpenSSL
    from OpenSSL._util import lib as OpenSSLlib
    logging.error('OpenSSL version: {}'.format(OpenSSL.__version__))
    logging.error('OpenSSL lib has ALPN: {}'.format(OpenSSLlib.Cryptography_HAS_ALPN)) #The test that failed on GAE
    logging.error('SSL openssl version: {}'.format(ssl._OPENSSL_API_VERSION))
    logging.error('SSL has ALPN: {}'.format(hasattr(ssl, 'HAS_ALPN')))

    if apns.make_ssl_context:
        get_context = apns.make_ssl_context
    else:
        get_context = apns.make_ossl_context
    logging.error('APNS3 SSL context version: {}'.format(get_context))

    # Connect
    context = get_context(
        certfile='static/cert/certificate.pem',
        keyfile='static/cert/key.pem',
        password=''
    )
    push_id = uuid4().hex

    # Retrieve pushtoken
    key = gds.key('Device', deviceLibraryIdentifier)
    entity = gds.get(key)
    if entity:
        pushtoken = entity['pushToken']
        logging.error('QUERY PUSHTOKEN: {}'.format(pushtoken))
    else:
        logging.error('QUERY PUSHTOKEN NOT FOUND.')

    # PASSES MUST BE PROCESSED BY THE PRODUCTION APNS! NOT DEVELOPMENT!
    client = apns.Client(ssl_context=context, sandbox=False)
    msg = apns.Message(id=push_id)
    msg.payload = json.dumps({})
    apns_id = client.push(msg, pushtoken)
    logging.error('PUSH-id: {}, APNS-id: {}'.format(UUID(push_id), apns_id))

    return 'Push!\n{}\n{}\n{}\n{}\n'.format(
        OpenSSL.__version__,
        OpenSSLlib.Cryptography_HAS_ALPN,
        ssl._OPENSSL_API_VERSION,
        apns_id
    ), 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/pass/update/')
def update_pass_expiration():

    serialNumber = request.args.get('serialNumber')
    offerExpiration = request.args.get('offerExpiration')
    status = passkit.update_pass_expiration(serialNumber, offerExpiration)
    return '{}\nSuccess: {}'.format(
        serialNumber,
        status == 200
    ), 200, {'Content-Type': 'text/plain; charset=utf-8'}


# [END PUSH NOTIFICATION SUPPORT]


@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
# [END app]

