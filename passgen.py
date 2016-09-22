import logging
import urllib3
import datetime
from pytz import timezone

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import imgload
import zipquery
from passbook.models import Pass, Coupon, Barcode, BarcodeFormat
from gcloud.exceptions import ClientError

DEFAULT_TIMEZONE = 'US/Pacific'
DEFAULT_LOGOTEXT = 'SUBWAY'
DEFAULT_FORECOLOR = 'rgb(255, 255, 255)'
DEFAULT_BACKCOLOR = 'rgb(72,158,59)'

organizationName = 'Mobivity'
teamIdentifier = 'D96C59RED5'
passTypeIdentifier = 'pass.com.mobivity.scannerdemo'
webServiceURL = 'https://mobivitypassbook-staging.appspot.com/passkit/'
# webServiceURL = 'https://mobpass.localtunnel.me/passkit/'

class PassGenerator(object):

    def __init__(self):
        pass

    def generate(self, pass_entity):

        if not pass_entity:
            logging.error('PASSGEN NO ENTITY!')
            return None

        # Auth info
        authToken = pass_entity['authToken']
        serialNumber = pass_entity['serialNumber']
        hexSignature = pass_entity['hexSignature']
        # User info
        uid = pass_entity['uid']
        fname = pass_entity['fname']
        lname = pass_entity['lname']
        # Context info
        zipcode = pass_entity['zipcode']
        # Offer info
        offerimg = pass_entity['offerImage']
        offerimgHR = pass_entity['offerImageHighRes']
        offertext = pass_entity['offerText']
        offerexp = pass_entity['offerExpiration']
        # Redeem info
        redeemed = pass_entity['redeemed']

        logging.error("PASSGEN AUTHTOKEN: {}".format(authToken))
        logging.error("PASSGEN SERIALNUM: {}".format(serialNumber))
        logging.error("PASSGEN TEXT: {}".format(offertext))
        logging.error("PASSGEN EXPIRATION: {}".format(offerexp))
        logging.error("PASSGEN REDEEMED: {}".format(redeemed))

        # Context info
        # QUERY MAY EXCEED  PROJECT LIMITS
        storeLocations = zipquery.get_store_from_zip(zipcode)

        # Offer info
        odate = datetime.datetime.strptime(offerexp, "%m/%d/%Y")
        otime = datetime.time(23, 59, 59, 0)
        offerexpdt_obj = datetime.datetime.combine(odate, otime)
        offerexpdt_obj = timezone(DEFAULT_TIMEZONE).localize(offerexpdt_obj)
        offerexpdt = offerexpdt_obj.isoformat('T')
        barcodeMsg = '{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n{}'.format(
            uid, fname, lname, '6" Meatball Sub', '8/9/2016',
            offertext, offerexp, serialNumber, hexSignature
        )

        # Add primary and auxiliary fields
        cardInfo = Coupon()
        cardInfo.addPrimaryField('offer', '', '')  # Text on strip image
        cardInfo.addAuxiliaryField('expires', offerexpdt, 'EXPIRES', type='Date',
                                   changeMessage='Coupon updated to expire on %@.')
        # HACK to support push notification when redeemed
        # Change value from <tab> to <space> when redeemed
        redeemed_field = '\t' if not redeemed else ' '
        cardInfo.addPrimaryField('redeemed', redeemed_field, '',
                                 changeMessage='Coupon has been redeemed.%@')

        # Create pass object
        passfile = Pass(cardInfo,
                        passTypeIdentifier=passTypeIdentifier,
                        organizationName=organizationName,
                        teamIdentifier=teamIdentifier)
        passfile.serialNumber = serialNumber
        passfile.authenticationToken = authToken
        passfile.webServiceURL = webServiceURL

        # Add barcode
        passfile.barcode = Barcode(message=barcodeMsg,
                                   format=BarcodeFormat.QR)

        # Add context info (location and time)
        for (lat, lng) in storeLocations:
            passfile.addLocation(lat, lng, 'Store nearby.')

        # HACK test location notification on iphone and android
        # 12760 High Bluff Drive
        passfile.addLocation(32.9503377, -117.2403383, 'Mobivity nearby.')
        # 12770 High Bluff Drive (Wifi location)
        passfile.addLocation(32.950414, -117.240039, 'Mobivity wifi nearby.')

        now_utc = datetime.datetime.now(timezone('UTC'))
        pass_utc = offerexpdt_obj.astimezone(timezone('UTC'))
        passfile.voided = True if redeemed else (now_utc == pass_utc)
        passfile.expirationDate = offerexpdt
        logging.info(now_utc.isoformat(' '))
        logging.info(pass_utc.isoformat(' '))

        # Add customizations
        # Including the icon and logo is necessary for the passbook to be valid
        passfile.foregroundColor = DEFAULT_FORECOLOR
        passfile.backgroundColor = DEFAULT_BACKCOLOR
        passfile.logoText = DEFAULT_LOGOTEXT
        passfile.addFile('icon.png', open('static/images/pass/icon.png', 'r'))
        passfile.addFile('logo.png', open('static/images/pass/logo.png', 'r'))

        # Retrieve queued image load results
        try:
            offerimg_file = imgload.get_img(serialNumber, 'strip')
            offerimgHR_file = imgload.get_img(serialNumber, 'strip@2x')
            assert offerimg_file
            assert offerimg_file
            logging.error('PASSGEN IMAGE PRELOAD Success.')
        except:
            http = urllib3.PoolManager()
            hreq = http.request('GET', offerimg, preload_content=False)
            offerimg_file = StringIO(hreq.read())
            hreq = http.request('GET', offerimgHR, preload_content=False)
            offerimgHR_file = StringIO(hreq.read())
            hreq.release_conn()
            logging.error('PASSGEN IMAGE PRELOAD TimeoutError.')

        # Queue delete image task
        q = imgload.get_imgload_queue()
        q.enqueue(imgload.delete_img, serialNumber, 'strip')
        q.enqueue(imgload.delete_img, serialNumber, 'strip@2x')

        passfile.addFile('strip.png', offerimg_file)
        passfile.addFile('strip@2x.png', offerimgHR_file)

        # Create .pkpass file
        pkpass = passfile.create('static/cert/certificate.pem',
                                 'static/cert/key.pem',
                                 'static/cert/wwdr.pem', '')
        pkpass.seek(0)

        logging.error('PASSGEN COMPLETED.')

        return pkpass

