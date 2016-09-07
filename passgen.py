import logging
import urllib3
import datetime
from pytz import timezone

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from passbook.models import Pass, Coupon, Barcode, BarcodeFormat
import zipquery, tasks

DEFAULT_TIMEZONE = 'US/Pacific'
DEFAULT_LOGOTEXT = 'SUBWAY'
DEFAULT_FORECOLOR = 'rgb(255, 255, 255)'
DEFAULT_BACKCOLOR = 'rgb(72,158,59)'

organizationName = 'Mobivity'
passTypeIdentifier = 'pass.com.mobivity.scannerdemo'
teamIdentifier = 'D96C59RED5'
webServiceURL = 'https://mobivitypassbook-staging.appspot.com/passkit/'

class PassGenerator(object):

    def __init__(self):
        pass

    def generate(self, pass_entity):

        # Auth info
        authToken = pass_entity['authToken']
        serialNumber = pass_entity['serialNumber']
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

        # Context info
        # storeLocations = zipquery.get_store_from_zip(zipcode)
        # TEMP PROJECT QUERY EXCEEDED LIMITS
        storeLocations = []

        # Offer info
        odate = datetime.datetime.strptime(offerexp, "%m/%d/%Y")
        otime = datetime.time(23, 59, 59, 0)
        offerexpdt_obj = datetime.datetime.combine(odate, otime)
        offerexpdt_obj = timezone(DEFAULT_TIMEZONE).localize(offerexpdt_obj)
        offerexpdt = offerexpdt_obj.isoformat('T')
        barcodeMsg = '{} {}\n{}\n{}\n{}\n'.format(fname, lname, offertext, uid, offerexp)

        # Add primary and auxiliary fields
        cardInfo = Coupon()
        cardInfo.addPrimaryField('offer', '', '')  # Text on strip image
        cardInfo.addAuxiliaryField('expires', offerexpdt, 'EXPIRES',
                                   type='Date',
                                   changeMessage='Coupon updated to expire on %@')

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
        now_utc = datetime.datetime.now(timezone('UTC'))
        pass_utc = offerexpdt_obj.astimezone(timezone('UTC'))
        passfile.voided = (now_utc == pass_utc)
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
            offerimg_file, offerimgHR_file = tasks.get_img()
            logging.error('IMAGE PRELOAD Success.')
        except:
            http = urllib3.PoolManager()
            hreq = http.request('GET', offerimg, preload_content=False)
            offerimg_file = StringIO(hreq.read())
            hreq = http.request('GET', offerimgHR, preload_content=False)
            offerimgHR_file = StringIO(hreq.read())
            hreq.release_conn()
            logging.error('IMAGE PRELOAD TimeoutError.')
        passfile.addFile('strip.png', offerimg_file)
        passfile.addFile('strip@2x.png', offerimgHR_file)

        # Create .pkpass file
        pkpass = passfile.create('static/cert/certificate.pem',
                                 'static/cert/key.pem',
                                 'static/cert/wwdr.pem', '')
        pkpass.seek(0)

        return pkpass



