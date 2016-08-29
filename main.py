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

from flask import Flask, render_template, send_from_directory, send_file, request
from passbook.models import Pass, Coupon, Barcode, BarcodeFormat

# Pass generation
from uuid import uuid4
from pytz import timezone
import datetime
import urllib
import urllib3
from mem import Memory
import tasks
import config
import psq

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
    offerexpdt = datetime.datetime.combine(odate, otime)
    offerexpdt = timezone(DEFAULT_TIMEZONE).localize(offerexpdt)
    offerexpdt = offerexpdt.isoformat('T')

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

    # Including the icon and logo is necessary for the passbook to be valid.
    passfile.addFile('icon.png', open('static/images/pass/icon.png', 'r'))
    passfile.addFile('logo.png', open('static/images/pass/logo.png', 'r'))
    # passfile.addFile('strip.png', StringIO(urllib.urlopen(offerimg).read()))
    # passfile.addFile('strip@2x.png', StringIO(urllib.urlopen(offerimgHR).read()))

    # Retrieve queued result
    try:
        offerimg, offerimgHR = PASS_MEM.loadimg.result(timeout=1)
    except psq.task.TimeoutError:
        http = urllib3.PoolManager()
        req = http.request('GET', offerimg, preload_content=False)
        offerimg = req.read()
        req.release_conn()
        req = http.request('GET', offerimgHR, preload_content=False)
        offerimgHR = req.read()
        req.release_conn()
        logging.error('Preload TimeoutError.')
    passfile.addFile('strip.png', StringIO(offerimg))
    passfile.addFile('strip@2x.png', StringIO(offerimgHR))

    # Create and output the Passbook file (.pkpass)
    pkpass = passfile.create('static/cert/certificate.pem', 'static/cert/key.pem', 'static/cert/wwdr.pem', '')
    pkpass.seek(0)

    return send_file(pkpass, mimetype='application/vnd.apple.pkpass')

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

