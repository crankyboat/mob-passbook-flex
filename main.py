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
from uuid import uuid4

# Push Notification Service
import push

# Pass Generation
import tasks
from passgen import PassGenerator

# Passkit Web Service
from passkit import PasskitWebService

# Basic Auth
from functools import wraps


app = Flask(__name__)
app.config.from_object(config)
gstorage = storage.Client(project=app.config['PROJECT_ID'])
gds = datastore.Client(project=app.config['PROJECT_ID'])
passkit = PasskitWebService(datastoreClient=gds,
                            storageClient=gstorage)
passgen = PassGenerator()


with app.app_context():
    imgload_queue = tasks.get_imgload_queue()


def build_response(response,
                   status=400,
                   contenttype='text',
                   lastmodified=''):

    response_wrapper = make_response(response)
    response_wrapper.status_code = status
    response_wrapper.headers['Pragma'] = 'no-cache'
    response_wrapper.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, pre-check=0, post-check=0'

    if contenttype == 'text':
        response_wrapper.headers['Content-Type'] = 'text/plain; charset=utf-8'
    elif contenttype == 'json':
        response_wrapper.headers['Content-Type'] = 'application/json'
    elif contenttype == 'html':
        response_wrapper.headers['Content-Type'] = 'text/html; charset=utf-8'
    elif contenttype == 'pkpass':   # Should already be handled by send_file(file, mimetype='application/vnd.apple.pkpass')
        response_wrapper.headers['Content-Type'] = 'application/vnd.apple.pkpass'

    if lastmodified:
        response_wrapper.headers['Last-Modified'] = '{}'.format(lastmodified)

    return response_wrapper


# [START BASIC AUTH SUPPORT]

def check_auth(auth):

    header, token = auth.split()
    pass_auth_header = 'MobivityOffer'  # TEMP
    pass_auth_token = '2ec6c5e11fe449d090cacae58d3cfda2'  # TEMP
    return header == pass_auth_header and \
           token == pass_auth_token


def authenticate():

    response = make_response('Authentication failure.')
    response.headers['WWW-Authenticate'] = 'Basic realm="MOBIVITY"'
    response.status_code = 401
    return response


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization')
        if not auth or not check_auth(auth):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# [END BASIC AUTH SUPPORT]


@app.route('/')
def hello():

    # TODO Ensure unique serial behavior
    # between access to '/' and '/pass'

    # Generate serialNumber
    serialNumber = uuid4().hex

    # Sign serialNumber
    import hashlib
    salt = '08f92b7a-7b90-11e6-8b77-86f30ca893d3'
    message = '{}{}'.format(serialNumber, salt)
    signedMessage = hashlib.md5()
    signedMessage.update(message.encode())
    signedMessageHex = signedMessage.hexdigest()

    # Queue load image task
    offerimg = request.args.get('offerImage')
    offerimgHR = request.args.get('offerImageHighRes')
    q = tasks.get_imgload_queue()
    q.enqueue(tasks.load_img, offerimg, serialNumber, 'strip')
    q.enqueue(tasks.load_img, offerimgHR, serialNumber, 'strip@2x')

    return build_response(
        render_template(
            'index.html',
            serialNumber=serialNumber,
            hexSignature=signedMessageHex
        ),
        status=200,
        contenttype='html'
    )


@app.route('/pass')
def send_pass():

    # Save authtoken to datastore
    pass_auth = 'vxwxd7J8AlNNFPS8k0a0FfUFtq0ewzFdc' # TEMP
    passkit.add_pass_authtoken(pass_auth)

    # Add pass to datastore
    pass_entity = passkit.add_pass(request.args.get('serialNumber'), request.args.get('hexSignature'), pass_auth,
                                   request.args.get('uid'), request.args.get('fname'), request.args.get('lname'), request.args.get('zipcode'),
                                   request.args.get('offerImage'), request.args.get('offerImageHighRes'),
                                   request.args.get('offerText'), request.args.get('offerExpiration'))

    logging.error('PASS SERIAL: {}'.format(request.args.get('serialNumber')))

    # Generate pass file
    pkpass = passgen.generate(pass_entity)

    # TODO If unsuccessful should remove pass_entity

    lastModified = passkit.get_http_dt_from_timestamp(pass_entity['lastUpdated'])

    # Send pass file
    return build_response(
        send_file(pkpass, mimetype='application/vnd.apple.pkpass'),
        status=200,
        contenttype='pkpass',
        lastmodified=lastModified
    )


# [START Passkit Support]

@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>/<serialNumber>',
          methods=['POST', 'DELETE'])
def registration(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber):

    authTitle, authToken = request.headers['Authorization'].split()
    logging.error('/PASSKIT/REGIST AUTHTOKEN: {}'.format(authToken))

    # Authenticate
    if not passkit.authenticate_authtoken(authTitle, authToken):
        return 'Unauthorized request.', 401

    # Register
    if request.method == 'POST':
        pushToken = request.json['pushToken']
        status = passkit.register_pass_to_device(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber, pushToken, authTitle)

        logging.error('/PASSKIT/REGIST PUSHTOKEN: {}'.format(pushToken))
        logging.error('/PASSKIT/REGIST STATUS: {}'.format(status))

        if status == 200:
            return build_response(
                'Serial number already exists.',
                status=200
            )
        elif status == 201:
            return build_response(
                'Registration successful.',
                status=201
            )
        else:
            return build_response(
                'Bad request.',
                status=400
            )

    # Unregister
    else: #request.method == 'DELETE'
        status = passkit.unregister_pass_to_device(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber)

        logging.error('/PASSKIT/UNREGIST STATUS: {}'.format(status))

        if status == 200:
            return build_response(
                'Unregistration successful.',
                status=200
            )
        else:
            return build_response(
                'Bad request.',
                status=400
            )


@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>', methods=['GET'])
def get_serials_for_device(version, deviceLibraryIdentifier, passTypeIdentifier):

    updatedSinceTag = request.args.get('passesUpdatedSince')
    payload, status = passkit.get_serials_for_device(version, deviceLibraryIdentifier, passTypeIdentifier, updatedSinceTag)

    logging.error('/PASSKIT/GETSERIAL PAYLOAD: {}'.format(payload))
    logging.error('/PASSKIT/GETSERIAL STATUS: {}'.format(status))

    if status == 200:
        return build_response(
            payload,
            status=200,
            contenttype='json'
        )
    elif status == 204:
        return build_response(
            'No matching passes.',
            status=204
        )
    else:
        return build_response(
            'Bad request.',
            status=400
        )


@app.route('/passkit/<version>/passes/<passTypeIdentifier>/<serialNumber>', methods=['GET'])
def get_updated_pass_for_device(version, passTypeIdentifier, serialNumber):

    logging.error('/PASSKIT/GETUPDATE AUTH HEADER: {}'.format(request.headers['Authorization']))
    authTitle, authToken = request.headers['Authorization'].split()
    logging.error('/PASSKIT/GETUPDATE AUTHTOKEN: {}'.format(authToken))

    # Authenticate
    if not passkit.authenticate_authtoken(authTitle, authToken):
        return 'Unauthorized request.', 401

    # Parse If-Modified-Since header
    modifiedSince = passkit.get_timestamp_from_http_dt(request.headers.get('If-Modified-Since'))
    logging.error('/PASSKIT/GETUPDATE modified-since: {}'.format(modifiedSince))

    # Download new pass
    newpass_entity, status = passkit.get_updated_pass_for_device(version, passTypeIdentifier, serialNumber, modifiedSince)
    logging.error('/PASSKIT/GETUPDATE STATUS: {}'.format(status))

    if status == 200:

        # TODO Add 'last-modified' header
        lastModified = passkit.get_http_dt_from_timestamp(newpass_entity['lastUpdated'])

        # Generate new pass
        newpkpass = passgen.generate(newpass_entity)

        return build_response(
            send_file(newpkpass, mimetype='application/vnd.apple.pkpass'),
            status=200,
            lastmodified=lastModified
        )
    elif status == 304:
        return build_response(
            'Pass has not changed.',
            status=304
        )
    else:
        return build_response(
            'Bad request.',
            status=400
        )

@app.route('/passkit/<version>/log', methods=['POST'])
def log(version):

    # Retrieve and log
    logs = request.json['logs']
    logging.error('/PASSKIT/LOG: {}'.format(logs))

    return build_response(
        json.dumps({'logs': logs}),
        status=200,
        contenttype='json'
    )

# [END Passkit Support]


# [START PUSH NOTIFICATION SUPPORT]

@app.route('/push/<deviceLibraryIdentifier>', methods=['POST'])
@requires_auth
def push_notification(deviceLibraryIdentifier):

    pushToken, platform = passkit.get_device_info(deviceLibraryIdentifier)

    if platform == 'Apple':
        return build_response(
            push.push_notification_apple(pushToken),
            status=200
        )
    elif platform == 'Android':
        return build_response(
            push.push_notification_android(pushToken),
            status=200
        )
    else:
        return build_response(
            'Bad request.',
            status=400
        )


@app.route('/pass/update', methods=['POST'])
@requires_auth
def update_pass_expiration():

    status = passkit.update_pass_expiration(request.args.get('serialNumber'),
                                            request.args.get('offerExpiration'))

    return build_response(
        'Serial: {}\nSuccess: {}'.format(
            request.args.get('serialNumber'),
            status == 200
        ),
        status=status
    )


@app.route('/pass/redeem', methods=['POST'])
@requires_auth
def redeem_pass():

    # EXPOSED TO HOOK SERVICE
    # Requires basic auth

    status = passkit.redeem_pass(request.args.get('serialNumber'))

    return build_response(
        'Serial: {}\nSuccess: {}'.format(
            request.args.get('serialNumber'),
            status == 200
        ),
        status=status
    )


@app.route('/pass/list', methods=['GET'])
@requires_auth
def list_passes():

    # List passes with their associated deviceLibraryIdentifier (many-to-one)
    return build_response(
        passkit.list_passes_with_devicelibid(),
        status=200
    )


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

