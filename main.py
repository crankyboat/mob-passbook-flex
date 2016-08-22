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

from flask import Flask, render_template, send_from_directory, send_file, request
from passbook.models import Pass, StoreCard, Barcode, BarcodeFormat
from uuid import uuid4


app = Flask(__name__)


@app.route('/')
def hello():
    return render_template('index.html')

@app.route('/pass')
def send_pass():

    uid = request.args.get('uid')
    fname = request.args.get('fname')
    lname = request.args.get('lname')
    msg = fname + ' ' + lname + '\n'
    msg += 'Get a free 6" Sub when you buy a 30oz drink\n'
    msg += uid + '\n'
    msg += '6" Meatball Sandwich\n'
    msg += '8/9/16\n'

    cardInfo = StoreCard()
    cardInfo.addPrimaryField('name', 'Free Food', 'Free food at Mobivity SD!')

    organizationName = 'Mobivity'
    passTypeIdentifier = 'pass.com.mobivity.scannerdemo'
    teamIdentifier = 'D96C59RED5'

    passfile = Pass(cardInfo, \
                    passTypeIdentifier=passTypeIdentifier, \
                    organizationName=organizationName, \
                    teamIdentifier=teamIdentifier)
    passfile.serialNumber = uuid4().hex
    passfile.barcode = Barcode(message=msg, format=BarcodeFormat.QR)
    passfile.foregroundColor = 'rgb(255, 255, 255)'
    passfile.backgroundColor = 'rgb(72,158,59)'

    # Including the icon and logo is necessary for the passbook to be valid.
    passfile.addFile('icon.png', open('static/images/pass/icon.png', 'r'))
    passfile.addFile('logo.png', open('static/images/pass/logo.png', 'r'))

    # Create and output the Passbook file (.pkpass)
    pkpass = passfile.create('static/cert/certificate.pem', 'static/cert/key.pem', 'static/cert/wwdr.pem', '')
    pkpass.seek(0)

    return send_file(pkpass, mimetype='application/vnd.apple.pkpass')
    # return send_from_directory('static', 'Test.pkpass', mimetype='application/vnd.apple.pkpass')

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

