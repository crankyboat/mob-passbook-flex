#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import config
from models import OfferClass, OfferObject, RequestJwt
try:
    import simplejson as json
except ImportError:
    import json

import httplib2
from googleapiclient.discovery import build_from_document
from oauth2client import crypt
from oauth2client.service_account import ServiceAccountCredentials


class SaveToAndroidApiHandler(object):

    def __init__(self):

        # Load key
        key_file_path = config.SERVICE_ACCOUNT_PRIVATE_KEY_PATH
        with file(key_file_path, 'rb') as f:
            self.key = f.read()

        # Create credentials
        svc_acct_email = config.SERVICE_ACCOUNT_EMAIL_ADDRESS
        scopes = [config.SERVICE_AUTH_SCOPE]
        credentials = ServiceAccountCredentials.from_p12_keyfile(
            svc_acct_email, key_file_path, scopes=scopes)

        # Authorize connection
        http = httplib2.Http()
        http = credentials.authorize(http)

        # Build service
        disc_file_path = config.DISCOVERY_FILE_PATH
        with file(disc_file_path, 'rb') as f:
            disc_content = f.read()
        self.service = build_from_document(disc_content, 'walletobjects', http=http)

    def insert_offer_class(self, new_offer_class=True):

        offer_class = OfferClass(config.ISSUER_ID,
                                 config.OFFER_CLASS_ID,
                                 config.ISSUER_NAME,
                                 config.PROVIDER,
                                 title='SUBWAY Weekly Offers',
                                 title_image_uri='https://s3-us-west-1.amazonaws.com/mobivitypassbook-staging/subway_logo.png')
        offer_class.addLocation(32.950414, -117.240039, 'Mobivity')
        offer_class.addLinksModule(['http://www.subway.com/en-us'], ['SUBWAY Home']) # addHomepage doesn't work
        offer_class.finePrint = u'Additional charges for extras and deluxe. Plus tax. No cash value. 1 coupon per customer. ' \
                                u'May not be combined with other offers, coupons, or discount cards. Void if transferred, sold, auctioned, reproduced, or altered. ' \
                                u'No coupon necessary. SUBWAY® is a Registered Trademark of Subway IP Inc. © 2016 Subway IP Inc.'

        if new_offer_class:
            api_request = self.service.offerclass().insert(
                body=offer_class.json_dict()
            )
        else:
            api_request = self.service.offerclass().update(
                resourceId='{}.{}'.format(config.ISSUER_ID, config.OFFER_CLASS_ID),
                body=offer_class.json_dict()
            )

        api_response = api_request.execute()

        if 'error' in api_response.keys():
            logging.error('Error inserting object {}.'.format(config.OFFER_CLASS_ID))
        else:
            logging.error('Successfully inserted object {}.'.format(config.OFFER_CLASS_ID))

        return offer_class

    def create_offer_object(self, offer_object_id, offer_text, offer_expiration,
                            offer_barcode_message, offer_image_url, version='1'):


        offer_object = OfferObject(
            config.ISSUER_ID,
            config.OFFER_CLASS_ID,
            offer_object_id,
            offer_expiration, version=version
        )
        offer_object.addBarcode(value=offer_barcode_message, alternate_text=offer_object_id)
        offer_object.addImageModule(offer_image_url)
        offer_object.addMessage(0, 'Offer Details', offer_text)

        return offer_object

    def createSignedJwt(self, offer_object):

        requestDomains = ['https://mobivitypassbook-staging.appspot.com', 'https://mobpass.localtunnel.me',
                          'http://mobivitypassbook-staging.appspot.com', 'http://mobpass.localtunnel.me']
        requestJwt = RequestJwt(config.SERVICE_ACCOUNT_EMAIL_ADDRESS, requestDomains)
        requestJwt.offerObjects.append(offer_object)

        jwt = requestJwt.json_dict()
        signer = crypt.Signer.from_string(self.key)
        signed_jwt = crypt.make_signed_jwt(signer, jwt)
        # logging.error('JWT: {}'.format(jwt))
        # logging.error('Signed JWT: {}'.format(signed_jwt))
        return signed_jwt

    def getOfferObject(self, offer_object_id):

        api_target = self.service.offerobject()
        api_request = api_target.get(resourceId='{}.{}'.format(config.ISSUER_ID, offer_object_id))
        api_response = api_request.execute() #returns a dictionary
        return api_response

    def updateOfferObject(self, offer_object_id, offer_object_dict):
        api_target = self.service.offerobject()
        api_request = api_target.update(
            resourceId='{}.{}'.format(config.ISSUER_ID, offer_object_id),
            body=offer_object_dict
        )
        api_response = api_request.execute()
        # logging.error('UPDATE OFFER API RESPONSE: {}'.format(api_response))

        logging.error('Succesfully updated object.')
        if 'error' in api_response.keys():
            logging.error('Error updating object {}.{}'.format(config.ISSUER_ID, offer_object_id))
        return

    def listOfferObjects(self):

        api_target = self.service.offerobject()
        api_request = api_target.list(classId='{}.{}'.format(config.ISSUER_ID, config.OFFER_CLASS_ID), maxResults='25')
        results = api_request.execute()

        logging.error('LIST OFFER API: ')
        logging.error('ResultsPerPage: {}'.format(results['pagination']['resultsPerPage']))
        if 'nextPageToken' in results['pagination']:
            logging.error('NextPageToken: {}'.format(results['pagination']['nextPageToken']))
        # logging.error('Resources: {}'.format(results['resources']))

        offer_list = ['(version, state, id, barcode)'] + [
            '{version}, {state}, {id}, {barcode}'.format(**offer)
            for offer in results['resources']
        ]
        return '\n'.join(offer_list)


if __name__ == '__main__':
    s2ap = SaveToAndroidApiHandler()
    # offer_class = s2ap.insert_offer_class(new_offer_class=False)