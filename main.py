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
from gcloud import bigquery, storage, datastore

import googlemaps


DEFAULT_TIMEZONE = 'US/Pacific'
DEFAULT_LOGOTEXT = 'SUBWAY'
BIGQUERY_PROJECT_ID = 'kinetic-anvil-797'
PASS_MEM = Memory()


app = Flask(__name__)
app.config.from_object(config)
gstorage = storage.Client(project=app.config['PROJECT_ID'])
gds = datastore.Client(project=app.config['PROJECT_ID'])


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
    cardInfo.addAuxiliaryField('expires', offerexpdt, 'EXPIRES',
                               type='Date', changeMessage='Coupon updated to expire on %@')

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


    ####

    # New expiration time
    odate = datetime.datetime.strptime('11/11/2016', "%m/%d/%Y")
    otime = datetime.time(23, 59, 59, 0)
    offerexpdt_obj = datetime.datetime.combine(odate, otime)
    offerexpdt_obj = timezone(DEFAULT_TIMEZONE).localize(offerexpdt_obj)
    offerexpdt = offerexpdt_obj.isoformat('T')
    now_utc = datetime.datetime.now(timezone('UTC'))
    pass_utc = offerexpdt_obj.astimezone(timezone('UTC'))
    logging.info(now_utc.isoformat(' '))
    logging.info(pass_utc.isoformat(' '))

    cardInfo = Coupon()
    cardInfo.addPrimaryField('offer', '', '') # Text on strip image
    cardInfo.addAuxiliaryField('expires', offerexpdt, 'EXPIRES',
                               type='Date', changeMessage='Coupon updated to expire on %@')

    organizationName = 'Mobivity'
    passTypeIdentifier = 'pass.com.mobivity.scannerdemo'
    teamIdentifier = 'D96C59RED5'

    newpassfile = Pass(cardInfo, \
                    passTypeIdentifier=passTypeIdentifier, \
                    organizationName=organizationName, \
                    teamIdentifier=teamIdentifier)
    newpassfile.serialNumber = passfile.serialNumber

    msg = fname + ' ' + lname + '\n'
    msg += offertext + '\n'
    msg += uid + '\n'
    msg += '11/11/2016' + '\n'
    newpassfile.barcode = Barcode(message=msg, format=BarcodeFormat.QR)
    newpassfile.foregroundColor = 'rgb(255, 255, 255)'
    newpassfile.backgroundColor = 'rgb(72,158,59)'
    newpassfile.logoText = DEFAULT_LOGOTEXT
    for (lat, lng) in storeGeo:
        newpassfile.addLocation(lat, lng, 'Store nearby.')
    newpassfile.addFile('icon.png', open('static/images/pass/icon.png', 'r'))
    newpassfile.addFile('logo.png', open('static/images/pass/logo.png', 'r'))
    newpassfile.voided = (now_utc==pass_utc)
    newpassfile.expirationDate = offerexpdt
    newpassfile.addFile('strip.png', StringIO(offerimg))
    newpassfile.addFile('strip@2x.png', StringIO(offerimgHR))
    newpassfile.webServiceURL = 'https://mobivitypassbook-staging.appspot.com/passkit/'
    newpassfile.authenticationToken = 'vxwxd7J8AlNNFPS8k0a0FfUFtq0ewzFdc'  # TEMP

    # Create and output the Passbook file (.pkpass)
    newpkpass = newpassfile.create('static/cert/certificate.pem', 'static/cert/key.pem', 'static/cert/wwdr.pem', '')
    newpkpass.seek(0)

    bucket = gstorage.get_bucket(app.config['PROJECT_ID'])
    blob = bucket.blob('newpass.pkpass', chunk_size=262144)
    blob.upload_from_file(newpkpass, content_type='application/vnd.apple.pkpass')

    ####

    # Send old
    return send_file(pkpass, mimetype='application/vnd.apple.pkpass')


# [START Passkit Support]

@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>/<serialNumber>',
          methods=['POST', 'DELETE'])
def register_pass(version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber):

    pushtoken = request.json['pushToken']
    logging.error('PASSKIT TOKEN: {}'.format(pushtoken))

    if request.method == 'POST':

        # Register device and pass
        with gds.transaction():
            tkey = gds.key('pushToken', '{}'.format(pushtoken))
            tentity = gds.get(tkey)
            if not tentity:
                tentity = datastore.Entity(key=tkey)
                tentity.update({
                    'pushToken': pushtoken
                })
                gds.put(tentity)

        # HACK save serial
        with gds.transaction():
            skey = gds.key('serial', '{}'.format(serialNumber))
            sentity = gds.get(skey)
            if not sentity:
                sentity = datastore.Entity(key=skey)
                sentity.update({
                    'serial': serialNumber
                })
                gds.put(sentity)

        # Registration suceeds
        return make_response('Successful registration!', 201)

    else: #request.method == 'DELETE'

        with gds.transaction():
            tkey = gds.key('pushToken', '{}'.format(pushtoken))
            gds.delete(tkey)

        # Unregister pass
        return make_response('Successful unregistration!', 200)

    pass


@app.route('/passkit/<version>/devices/<deviceLibraryIdentifier>/' +
          'registrations/<passTypeIdentifier>', methods=['GET'])
def get_device_serials(version, deviceLibraryIdentifier, passTypeIdentifier):

    # Retrieve serial
    query = gds.query(kind='serial')
    results = [
        '{serial}'.format(**x)
        for x in query.fetch(limit=5)
    ]
    logging.error('QUERY SERIAL: {}'.format(', '.join(results)))
    serial = results[0]

    tag = request.args.get('passesUpdatedSince')
    resp = json.dumps({'lastUpdated': '{}'.format(uuid4().hex), 'serialNumbers': ['{}'.format(serial)]})

    return Response(response=resp, status=200, mimetype='application/json')


@app.route('/passkit/<version>/passes/<passTypeIdentifier>/<serialNumber>', methods=['GET'])
def get_latest_pass(version, passTypeIdentifier, serialNumber):

    # Download new pass
    newpkpass = StringIO()
    bucket = gstorage.get_bucket(app.config['PROJECT_ID'])
    blob = bucket.get_blob('newpass.pkpass')
    blob.download_to_file(newpkpass)
    newpkpass.seek(0)

    # resp = make_response(send_file(latestPkpass, mimetype='application/vnd.apple.pkpass'))
    # resp.status_code = 200
    # return resp
    return send_file(newpkpass, mimetype='application/vnd.apple.pkpass')

@app.route('/passkit/<version>/log', methods=['POST'])
def log_passkit(version):
    logs = request.get_json()['logs']
    logging.error('PASSKIT LOG: '.format(logs))
    return Response(response=json.dumps({'success': True}), status=200, mimetype='application/json')

# [END Passkit Support]


# [START PUSH NOTIFICATION SUPPORT]

@app.route('/push')
def push_notification():

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
    query = gds.query(kind='pushToken')
    results = [
        '{pushToken}'.format(**x)
        for x in query.fetch(limit=5)
    ]
    logging.error('QUERY PUSHTOKEN: {}'.format(', '.join(results)))
    pushtoken = results[0]

    # PASSES MUST BE PROCESSED BY THE PRODUCTION APNS! NOT DEVELOPMENT!
    client = apns.Client(ssl_context=context, sandbox=False)
    msg = apns.Message(id=push_id)
    msg.payload = json.dumps({})
    logging.error('PAYLOAD: {}'.format(msg.payload))
    apns_id = client.push(msg, pushtoken)
    logging.error('MEM TOKEN: {}'.format(pushtoken))
    logging.error('PUSH-id: {}, APNS-id: {}'.format(UUID(push_id), apns_id))


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

