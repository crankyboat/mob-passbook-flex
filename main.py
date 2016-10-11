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

from flask import Flask, render_template, send_file, request, make_response, redirect, url_for
from gcloud import storage, datastore
from uuid import uuid4
import hashlib

# Apple Push Notification Service
import push

# Apple Pass Generation
import imgload
from passgen import PassGenerator

# Apple Passkit Web Service
from passkit import PasskitWebService

# Android Save to Android Pay Api
from android.s2ap import SaveToAndroidApiHandler

# Platform check
from platinfo import PlatformRecord

# Basic Auth
from functools import wraps


app = Flask(__name__)
app.config.from_object(config)
gstorage = storage.Client(project=app.config['PROJECT_ID'])
gds = datastore.Client(project=app.config['PROJECT_ID'])
passkit = PasskitWebService(datastoreClient=gds,
                            storageClient=gstorage)
passgen = PassGenerator()
s2ap = SaveToAndroidApiHandler()
platinfo = PlatformRecord(datastoreClient=gds)


with app.app_context():
    imgload_queue = imgload.get_imgload_queue()


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

    paramList = [
        request.args.get('uid'), request.args.get('fname'),
        request.args.get('lname'), '6" Meatball Sub', '8/9/2016',
        request.args.get('offerText'), request.args.get('offerExpiration')
    ]

    # Generate serialNumber from params
    # serialNumber = uuid4().hex

    serialList = paramList + [
        request.args.get('offerImage'), request.args.get('offerImageHighRes'),
        request.args.get('zipcode')
    ]
    serialSalt = app.config['DEFAULT_SERIAL_SALT']
    serialMessage = '{}{}'.format(''.join(serialList), serialSalt)
    signedSerialMessage = hashlib.md5()
    signedSerialMessage.update(serialMessage.encode())
    serialNumber = signedSerialMessage.hexdigest()

    # Barcode message to hash
    originalList = paramList + [serialNumber]
    originalMessage = '{}\n'.format('\n'.join(originalList))

    # Sign message
    salt = app.config['DEFAULT_SIGNATURE_SALT']
    message = '{}{}'.format(originalMessage, salt)
    signedMessage = hashlib.md5()
    signedMessage.update(message.encode())
    signedMessageHex = signedMessage.hexdigest()
    qrcodeText = '{}{}'.format(originalMessage, signedMessageHex)
    logging.error('QRCODE TEXT: {}'.format(qrcodeText.replace('\n', '\\n')))


    # Check platform
    # logging.error('String: {}'.format(request.user_agent.string))
    logging.error('Platform: {}'.format(request.user_agent.platform))
    logging.error('Browser: {}'.format(request.user_agent.browser))
    platform = request.user_agent.platform.lower()

    if platform == 'android':

        # Record platform info
        platinfo.record_platform(serialNumber, 'android')

        # Assume offer class has been created
        # offer_class = s2ap.insert_offer_class()

        offer_object = s2ap.get_offer_object(serialNumber)

        if offer_object:
            logging.error('OFFER_OBJECT ALREADY EXISTS.')

        # Create and sign offer object
        offer_object = s2ap.create_offer_object(
            offer_object_id=serialNumber,
            offer_text=request.args.get('offerText'),
            offer_expiration=request.args.get('offerExpiration'),
            offer_barcode_message=qrcodeText,
            offer_image_url=request.args.get('offerImageHighRes'),
            offer_zipcode=request.args.get('zipcode'),
            version='1'
        )

        signed_jwt = s2ap.create_signed_jwt(offer_object)

        # TODO Adding offer information to datastore
        # Should NOT be in the passkit tables
        # Um but these info are probably in google merchant center?
        # If so then do not need to maintain, simply query

    elif platform == 'iphone' or platform == 'ios':

        # Record platform info
        platinfo.record_platform(serialNumber, 'apple')

        # Queue load image task
        offerimg = request.args.get('offerImage')
        offerimgHR = request.args.get('offerImageHighRes')
        q = imgload.get_imgload_queue()
        q.enqueue(imgload.load_img, offerimg, serialNumber, 'strip')
        q.enqueue(imgload.load_img, offerimgHR, serialNumber, 'strip@2x')

        signed_jwt = ''

    else: #browser

        # Do nothing
        signed_jwt = ''

    return build_response(
        render_template(
            'index.html',
            qrcodeText=qrcodeText,
            serialNumber=serialNumber,
            hexSignature=signedMessageHex,
            signed_jwt=signed_jwt
        ),
        status=200,
        contenttype='html'
    )


@app.route('/pass')
def send_pass():

    # Save authtoken to datastore
    pass_auth = app.config['DEFAULT_AUTHTOKEN']
    passkit.add_pass_authtoken(pass_auth)

    # Add pass to datastore
    pass_entity = passkit.add_pass(
        request.args.get('serialNumber'), request.args.get('hexSignature'), pass_auth,
        request.args.get('uid'), request.args.get('fname'), request.args.get('lname'), request.args.get('zipcode'),
        request.args.get('offerImage'), request.args.get('offerImageHighRes'),
        request.args.get('offerText'), request.args.get('offerExpiration')
    )

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

    authTitle, authToken = request.headers['Authorization'].split()
    logging.error('/PASSKIT/GETUPDATE AUTH HEADER: {}'.format(request.headers['Authorization']))
    logging.error('/PASSKIT/GETUPDATE AUTHTOKEN: {}'.format(authToken))

    # Authenticate
    if not passkit.authenticate_authtoken(authTitle, authToken):
        return 'Unauthorized request.', 401

    # Parse If-Modified-Since header
    modifiedSince = passkit.get_timestamp_from_http_dt(request.headers.get('If-Modified-Since'))
    logging.error('/PASSKIT/GETUPDATE modified-since: {}'.format(request.headers.get('If-Modified-Since')))

    # Download new pass
    newpass_entity, status = passkit.get_updated_pass_for_device(version, passTypeIdentifier, serialNumber, modifiedSince)
    logging.error('/PASSKIT/GETUPDATE STATUS: {}'.format(status))

    if status == 200:

        # Add Last-Modified header
        lastModified = passkit.get_http_dt_from_timestamp(newpass_entity['lastUpdated'])
        logging.error('/PASSKIT/GETUPDATE last-modified: {}'.format(lastModified))

        # Generate new pass
        newpkpass = passgen.generate(newpass_entity)

        return build_response(
            send_file(newpkpass, mimetype='application/vnd.apple.pkpass'),
            status=200,
            contenttype='pkpass',
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
    deviceLibraryIdentifier = passkit.get_devicelibid_of_pass(request.args.get('serialNumber'))
    logging.error('UPDATE EXPIRATION API STATUS {}, DEVICE {}.'.format(status, deviceLibraryIdentifier))

    if status == 200 and deviceLibraryIdentifier:
        push_notification(deviceLibraryIdentifier)
        logging.error('UPDATE EXPIRATION PUSHED.')

    return build_response(
        'Serial: {}\nSuccess: {}'.format(
            request.args.get('serialNumber'),
            status == 200
        ),
        status=status
    )


# @app.route('/pass/redeem', methods=['GET', 'POST'])
# @requires_auth
# def redeem_pass():
def redeem_pass(request):

    # EXPOSED TO HOOK SERVICE
    # Requires basic auth
    # Sends push notification to device

    if request.method == 'GET': #VERIFY

        status = passkit.verify_pass(request.args.get('serialNumber'))
        deviceLibraryIdentifier = passkit.get_devicelibid_of_pass(request.args.get('serialNumber'))
        logging.error('VERIFY API STATUS {}, DEVICE {}.'.format(status, deviceLibraryIdentifier))

        if status == 200 and deviceLibraryIdentifier:
            logging.error('VERIFIED.')
        else:
            logging.error('VERIFICATION FAILED.')

        return build_response(
            'Serial: {}\nVerified: {}'.format(
                request.args.get('serialNumber'),
                (status == 200 and deviceLibraryIdentifier != None)
            ),
            status=status
        )

    else:   # if request.method == 'POST'   #REDEEM

        status = passkit.redeem_pass(request.args.get('serialNumber'))
        deviceLibraryIdentifier = passkit.get_devicelibid_of_pass(request.args.get('serialNumber'))
        logging.error('REDEEM API STATUS {}, DEVICE {}.'.format(status, deviceLibraryIdentifier))

        if status == 200 and deviceLibraryIdentifier:
            push_notification(deviceLibraryIdentifier)
            logging.error('REDEEM PUSHED.')

        return build_response(
            'Serial: {}\nRedeemed: {}'.format(
                request.args.get('serialNumber'),
                (status == 200 and deviceLibraryIdentifier != None)
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

@app.route('/redeem', methods=['GET', 'POST'])
@requires_auth
def redeem_apple_and_android():

    serialNumber = request.args.get('serialNumber')
    platform = platinfo.get_platform(serialNumber)

    # Redirect code 307 preserves request method
    if platform == 'android':
        # return redirect('/android/redeem?serialNumber={}'.format(serialNumber), code=307)
        return redeem_android_offer(request)
    elif platform == 'apple':
        # return redirect('/pass/redeem?serialNumber={}'.format(serialNumber), code=307)
        return redeem_pass(request)
    else:
        return build_response('No platform information.')


# @app.route('/android/redeem', methods=['GET', 'POST'])
# @requires_auth
# def redeem_android_offer():
def redeem_android_offer(request):

    if request.method == 'GET': #VERIFY

        status = s2ap.verify_offer_object(request.args.get('serialNumber'))

        if status == 200:
            logging.error('ANDROID/VERIFY succeeded.')
        else: # status == 400
            logging.error('ANDROID/VERIFY failed.')

        return build_response(
            'Serial: {}\nVerified: {}'.format(
                request.args.get('serialNumber'),
                status == 200
            ),
            status=status
        )

    else: #request.method == 'POST: #REDEEM

        status = s2ap.redeem_offer_object(request.args.get('serialNumber'))

        if status == 200:
            logging.error('ANDROID/REDEEM succeeded.')
        else:   # status == 400
            logging.error('ANDROID/REDEEM failed.')

        return build_response(
            'Serial: {}\nRedeemed: {}'.format(
                request.args.get('serialNumber'),
                status == 200
            ),
            status=status
        )


@app.route('/android/list', methods=['GET'])
@requires_auth
def list_android_offers():

    return build_response(
        s2ap.list_offer_objects(),
        status=200
    )


# [START cron]
@app.route('/cleanup/storage')
def cleanup_storage():

    status = imgload.cleanup()
    return build_response(
        'Daily storage cleanup.\nStatus: {}'.format(status),
        status=status
    )
# [END cron]

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

