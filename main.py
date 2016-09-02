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

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
try:
    import simplejson as json
except ImportError:
    import json

from flask import Flask, Response, render_template, send_from_directory, send_file, request, make_response
from passbook.models import Pass, Coupon, Barcode, BarcodeFormat

# Pass generation
from uuid import uuid4, UUID
from pytz import timezone
import datetime
import urllib3
from mem import Memory
import tasks
import config
import psq

# Push Notification Service
import apns

# Bigquery
from gcloud import bigquery
import googlemaps


DEFAULT_TIMEZONE = 'US/Pacific'
DEFAULT_LOGOTEXT = 'SUBWAY'
BIGQUERY_PROJECT_ID = 'kinetic-anvil-797'
PASS_MEM = Memory()


app = Flask(__name__)
app.config.from_object(config)


# [START imgload_queue]
with app.app_context():
    imgload_queue = tasks.get_imgload_queue()
# [END imgload_queue]


def _get_store_from_zip(zipcode):

    # Lookup zipcode by geocoding API
    geoKey = 'AIzaSyDiiA_SRmtBpv-SmR1jsPLJHpgg0l9a0Bk'
    geoClient = googlemaps.Client(geoKey)
    results = geoClient.geocode(zipcode)
    ne = results[0]['geometry']['bounds']['northeast']
    sw = results[0]['geometry']['bounds']['southwest']
    bounds = (sw['lat'], ne['lat'], sw['lng'], ne['lng'])
    logging.info(bounds)

    # Query stores
    client = bigquery.Client(project=BIGQUERY_PROJECT_ID)
    # Depends on Christian's tables!
    QUERY = """
        SELECT lat,lng
        FROM christian_playground.subway_coords
        WHERE (lat BETWEEN {} AND {})
        AND (lng BETWEEN {} AND {})
    """.format(*bounds) # USE BETWEEN INSTEAD!
    query = client.run_sync_query(QUERY)
    query.timeout_ms = 1000
    query.run()
    logging.info(query.rows[:10])

    return query.rows[:10]


@app.route('/')
def hello():

    # Queue load image task
    offerimg = request.args.get('offerImage')
    offerimgHR = request.args.get('offerImageHighRes')
    q = tasks.get_imgload_queue()
    PASS_MEM.loadimg = q.enqueue(tasks.load_img, offerimg, offerimgHR)

    return render_template('index.html')


@app.route('/bigtable/<zipcode>')
def get_geo(zipcode):
    _get_store_from_zip(zipcode)
    return 'Hello Bigquery!'


@app.route('/pass')
def send_pass():

    # User info
    uid = request.args.get('uid')
    fname = request.args.get('fname')
    lname = request.args.get('lname')

    # Context info
    zipcode = request.args.get('zipcode')
    storeGeo = _get_store_from_zip(zipcode)

    # Offer info
    offerimg = request.args.get('offerImage')
    offerimgHR = request.args.get('offerImageHighRes')
    offertext = request.args.get('offerText')
    offerexp = request.args.get('offerExpiration')
    odate = datetime.datetime.strptime(offerexp, "%m/%d/%Y")
    otime = datetime.time(23, 59, 59, 0)
    offerexpdt_obj = datetime.datetime.combine(odate, otime)
    offerexpdt_obj = timezone(DEFAULT_TIMEZONE).localize(offerexpdt_obj)
    offerexpdt = offerexpdt_obj.isoformat('T')

    msg = fname + ' ' + lname + '\n'
    msg += offertext + '\n'
    msg += uid + '\n'
    msg += offerexp + '\n'

    cardInfo = Coupon()
    cardInfo.addPrimaryField('offer', '', '') # Text on strip image
    cardInfo.addAuxiliaryField('expires', offerexpdt, 'EXPIRES', type='Date')

    organizationName = 'Mobivity'
    passTypeIdentifier = 'pass.com.mobivity.scannerdemo'
    teamIdentifier = 'D96C59RED5'

    passfile = Pass(cardInfo, \
                    passTypeIdentifier=passTypeIdentifier, \
                    organizationName=organizationName, \
                    teamIdentifier=teamIdentifier)
    passfile.serialNumber = uuid4().hex

    # Customize the pass
    passfile.barcode = Barcode(message=msg, format=BarcodeFormat.QR)
    passfile.foregroundColor = 'rgb(255, 255, 255)'
    passfile.backgroundColor = 'rgb(72,158,59)'
    passfile.logoText = DEFAULT_LOGOTEXT
    for (lat,lng) in storeGeo:
        passfile.addLocation(lat, lng, 'Store nearby.')
    now_utc = datetime.datetime.now(timezone('UTC'))
    pass_utc = offerexpdt_obj.astimezone(timezone('UTC'))
    logging.info(now_utc.isoformat(' '))
    logging.info(pass_utc.isoformat(' '))
    passfile.voided = (now_utc==pass_utc)
    passfile.expirationDate = offerexpdt

    # Including the icon and logo is necessary for the passbook to be valid.
    passfile.addFile('icon.png', open('static/images/pass/icon.png', 'r'))
    passfile.addFile('logo.png', open('static/images/pass/logo.png', 'r'))
    # passfile.addFile('strip.png', StringIO(urllib.urlopen(offerimg).read()))
    # passfile.addFile('strip@2x.png', StringIO(urllib.urlopen(offerimgHR).read()))

    # Retrieve queued result
    try:
        offerimg, offerimgHR = PASS_MEM.loadimg.result(timeout=1)
    except: # psq.task.TimeoutError or PASS_MEM==NoneType
        http = urllib3.PoolManager()
        req = http.request('GET', offerimg, preload_content=False)
        offerimg = req.read()
        req.release_conn()
        req = http.request('GET', offerimgHR, preload_content=False)
        offerimgHR = req.read()
        req.release_conn()
        logging.error('IMAGE PRELOAD TimeoutError.')
    passfile.addFile('strip.png', StringIO(offerimg))
    passfile.addFile('strip@2x.png', StringIO(offerimgHR))

    # Include info for update
    # Below line prevents pass from being downloaded when deployed on GAE
    # passfile.webServiceURL = 'http://127.0.0.1:8080/passkit/'
    passfile.webServiceURL = 'https://mobivitypassbook-staging.appspot.com/passkit/'
    passfile.authenticationToken = 'vxwxd7J8AlNNFPS8k0a0FfUFtq0ewzFdc' # TEMP

    # Create and output the Passbook file (.pkpass)
    pkpass = passfile.create('static/cert/certificate.pem', 'static/cert/key.pem', 'static/cert/wwdr.pem', '')
    pkpass.seek(0)

    return send_file(pkpass, mimetype='application/vnd.apple.pkpass')


# [START Passkit Support]

@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>/<serialNumber>',
          methods=['POST', 'DELETE'])
def register_pass(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber):

    if request.method == 'POST':

        # Register device and pass
        logging.error('Push Token: {}'.format(request.json['pushToken']))
        PASS_MEM.pushtoken = request.json['pushToken']

        # Registration suceeds
        return make_response('Successful registration!', 201)

    else: #request.method == 'DELETE'

        PASS_MEM.pushtoken = None

        # Unregister pass
        return make_response('Successful unregistration!', 200)

    pass


@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>', methods=['GET'])
def get_device_serials(version, deviceLibraryIdentifier, passTypeIdentifier):

    tag = request.args.get('passesUpdatedSince')
    resp = json.dumps({'lastUpdated': 'prev_tag', 'serialNumbers': ['633dfac9ea9d4bbc89c60a208ee83458']})

    return Response(response=resp, status=200, mimetype='application/json')


@app.route('/passkit/<version>/passes/<passTypeIdentifier>/<serialNumber>', methods=['GET'])
def get_latest_pass(version, passTypeIdentifier, serialNumber):

    latestPass = json.dumps(
        {"serialNumber": "633dfac9ea9d4bbc89c60a208ee83458","organizationName": "Mobivity", "description": "", "coupon":{"auxiliaryFields": [{"timeStyle": "PKDateStyleShort", "dateStyle": "PKDateStyleShort", "value": "2016-11-11T23:59:59-07:00", "label": "EXPIRES", "key": "expires", "changeMessage": "", "isRelative": False, "textAlignment": "PKTextAlignmentLeft"}],"primaryFields": [{"changeMessage": "", "textAlignment": "PKTextAlignmentLeft", "value": "", "key": "offer", "label": ""}]}, "barcode": {"message": "Jonathan Twomley\nFREE 6-INCH CLASSIC SUB WITH PURCHASE OF A 30 OZ DRINK\n10153420835831891\n11/11/2016\n", "altText": "", "messageEncoding": "iso-8859-1", "format": "PKBarcodeFormatQR"}, "passTypeIdentifier": "pass.com.mobivity.scannerdemo", "locations": [{"latitude": 32.854299, "altitude": 0.0, "relevantText": "Store nearby.", "longitude": -117.2051141}, {"latitude": 32.8690181, "altitude": 0.0, "relevantText": "Store nearby.", "longitude": -117.2150024}, {"latitude": 32.8707537, "altitude": 0.0, "relevantText": "Store nearby.", "longitude": -117.2109368}, {"latitude": 32.8753618, "altitude": 0.0, "relevantText": "Store nearby.", "longitude": -117.2358622}], "authenticationToken": "vxwxd7J8AlNNFPS8k0a0FfUFtq0ewzFdc", "webServiceURL": "https://mobivitypassbook-staging.appspot.com/passkit/", "teamIdentifier": "D96C59RED5", "formatVersion": 1, "foregroundColor": "rgb(255, 255, 255)", "expirationDate": "2016-11-11T23:59:59-07:00", "backgroundColor": "rgb(72,158,59)", "suppressStripShine": False, "logoText": "SUBWAY", "barcodes": [{"message": "Jonathan Twomley\nFREE 6-INCH CLASSIC SUB WITH PURCHASE OF A 30 OZ DRINK\n10153420835831891\n9/11/2016\n", "altText": "", "messageEncoding": "iso-8859-1", "format": "PKBarcodeFormatQR"}]}
    )
    return Response(response=latestPass, status=200, mimetype='application/json')


@app.route('/passkit/<version>/log', methods=['POST'])
def log_passkit(version):

    logs = request.get_json()['logs']
    return Response(response=json.dumps({'success': True}), status=200, mimetype='application/json')

# [END Passkit Support]


# [START PUSH NOTIFICATION SUPPORT]

@app.route('/push')
def push_notification():

    import ssl
    import OpenSSL
    from OpenSSL._util import lib as OpenSSLlib
    logging.error('OpenSSL version: {}'.format(OpenSSL.__version__))
    logging.error('OpenSSL lib has ALPN: {}'.format(OpenSSLlib.Cryptography_HAS_ALPN)) #The test that failed on GAE
    logging.error('SSL openssl version: {}'.format(ssl._OPENSSL_API_VERSION))
    # logging.error('SSL has ALPN: {}'.format(ssl.HAS_ALPN)) #Failed on GAE because of older python version

    if apns.make_ssl_context:
        get_context = apns.make_ssl_context
    else:
        get_context = apns.make_ossl_context

    logging.error('SSL context version: {}'.format(get_context))

    # Connect
    context = get_context(
        certfile='static/cert/certificate.pem',
        keyfile='static/cert/key.pem',
        password=''
    )
    push_id = uuid4().hex

    # PASSES MUST BE PROCESSED BY THE PRODUCTION APNS! NOT DEVELOPMENT!
    client = apns.Client(ssl_context=context, sandbox=False)
    msg = apns.Message(id=push_id)
    PASS_MEM.pushtoken = '56ce0a56f2515ff002d5865fd1086beb80bb5c19403095fd607040a88580b67a'
    apns_id = client.push(msg, PASS_MEM.pushtoken)
    logging.error('Push id: {}, APNS_id: {}'.format(UUID(push_id), apns_id))

    return 'Push!\n{}\n{}\n{}\n{}\n'.format(
        OpenSSL.__version__,
        OpenSSLlib.Cryptography_HAS_ALPN,
        ssl._OPENSSL_API_VERSION,
        apns_id
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

