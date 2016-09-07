import logging
import datetime
import time
from pytz import timezone
from gcloud import datastore
try:
    import simplejson as json
except ImportError:
    import json


class PasskitWebService(object):

    def __init__(self, datastoreClient, storageClient):

        # Initialize gcloud clients
        self.gds = datastoreClient
        self.gstorage = storageClient

        # Datastore tables

        ### Device table ###
        # key = ('Device', 'deviceLibraryIdentifier')
        # fields = {'deviceLibraryIdentifier', 'pushToken'}

        ### Passes table ###
        # key = ('Passes', 'serialNumber')
        # fields = {'serialNumber', 'passTypeIdentifier', 'lastUpdated', etc.(all info on pass)}

        ### Registration table ###
        # key = ('Registration', 'deviceLibraryIdentifier', 'RegistrationPassType', 'passTypeIdentifier')
        # fields = {'deviceLibraryIdentifier', 'passTypeIdentifier', 'serialNumbers'(array)}


### [BEGIN Passkit Web Service Support] ###

    def register_pass_to_device(self, version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber, pushToken):

        try:
            with self.gds.transaction():

                # Update device table
                key = self.gds.key('Device', '{}'.format(deviceLibraryIdentifier))
                entity = self.gds.get(key)
                if not entity:
                    entity = datastore.Entity(key=key)
                    entity.update({
                        'deviceLibraryIdentifier': deviceLibraryIdentifier,
                        'pushToken': pushToken
                    })
                    self.gds.put(entity)

                # Update registration table
                key = self.gds.key('Registration', '{}'.format(deviceLibraryIdentifier),
                                   'RegistrationPassType', '{}'.format(passTypeIdentifier))
                entity = self.gds.get(key)
                if not entity:
                    entity = datastore.Entity(key=key)
                    entity.update({
                        'deviceLibraryIdentifier': deviceLibraryIdentifier,
                        'passTypeIdentifier': passTypeIdentifier,
                        'serialNumbers': [serialNumber]
                    })
                else:
                    serialNumbers = set(entity['serialNumbers'])

                    if serialNumber in serialNumbers:
                        return 200

                    serialNumbers.add(serialNumber)
                    entity['serialNumbers'] = list(serialNumbers)
                self.gds.put(entity)

                # Registration succeeds
                return 201
        except:
            return 400

    def unregister_pass_to_device(self, version, deviceLibraryIdentifier, passTypeIdentifier, serialNumber):

        try:
            with self.gds.transaction():

                # Update registration table
                key = self.gds.key('Registration', '{}'.format(deviceLibraryIdentifier),
                                   'RegistrationPassType', '{}'.format(passTypeIdentifier))
                entity = self.gds.get(key)
                if entity:

                    serialNumbers = set(entity['serialNumbers'])

                    if serialNumber in serialNumbers:
                        serialNumbers.remove(serialNumber)

                    if len(serialNumbers) == 0:
                        self.gds.delete(key)
                    else:
                        entity['serialNumbers'] = list(serialNumbers)
                        self.gds.put(entity)

                # If no more device entries in the registration table
                parent_key = self.gds.key('Registration', '{}'.format(deviceLibraryIdentifier))
                query = self.gds.query(kind='RegistrationPassType',
                                       ancestor=parent_key)

                if len(list(query.fetch())) == 0:

                    # Update device table
                    key = self.gds.key('Device', '{}'.format(deviceLibraryIdentifier))
                    entity = self.gds.get(key)
                    if entity:
                        self.gds.delete(key)

                # Unregistration succeeds
                return 200
        except:
            return 400

    def get_serials_for_device(self, version, deviceLibraryIdentifier, passTypeIdentifier, updatedSinceTag):

        # try:

        # Query registration table
        key = self.gds.key('Registration', deviceLibraryIdentifier,
                           'RegistrationPassType', passTypeIdentifier)
        entity = self.gds.get(key)

        # Find serials the device is registered for
        if entity:

            serialNumbers = set(entity['serialNumbers'])
            now_timestamp = self.get_current_timestamp()

            assert len(serialNumbers) > 0
            assert isinstance(now_timestamp, float)

            # Query passes table
            if not updatedSinceTag:

                # Return all
                results = list(serialNumbers)

            else:

                # Return only serials with a newer tag
                updatedSince = float(updatedSinceTag)
                query = self.gds.query(kind='Passes')
                query.add_filter('lastUpdated', '>', updatedSince)
                results = [
                    '{serialNumber}'.format(**q)
                    for q in query.fetch()
                ]

            # No new serials for the device
            if len(results) == 0:
                return None, 204
            # Yes new serials for the device
            else:
                return json.dumps({
                    'lastUpdated': str(now_timestamp),
                    'serialNumbers': results
                }), 200

        # No serials for the device
        else:
            return None, 204
        # except:
        #     import sys
        #     logging.error('EXCEPT: {}'.format(sys.exc_info()[0]))
        #     return None, 400

    def get_updated_pass_for_device(self, version, passTypeIdentifier, serialNumber):

        pass_key = self.gds.key('Passes', '{}'.format(serialNumber))
        pass_entity = self.gds.get(pass_key)

        # TODO Add support for passtype and memcache
        # Currently passtype not stored
        # passTypeIdentifier == pass_entity['passTypeIdentifier']
        if pass_entity:
            return pass_entity, 200

        return None, 400


### [END Passkit Web Service Support] ###


    def add_pass_authtoken(self, authToken):

        # Overwrite if exists
        with self.gds.transaction():

            key = self.gds.key('AuthList', 'default',
                               'AuthToken', 'mobipass')
            entity = self.gds.get(key)
            if not entity:
                entity = datastore.Entity(key=key)
                entity.update({
                    'authToken': '{}'.format(authToken)
                })
            else:
                entity['authToken'] = '{}'.format(authToken)
            self.gds.put(entity)

        return

    def authenticate_authtoken(self, authTitle, authToken):

        # Strong consistency enforced through ancestor query
        key = self.gds.key('AuthList', 'default',
                      'AuthToken', 'mobipass')
        entity = self.gds.get(key)

        return entity and \
               authTitle == 'ApplePass' and \
               authToken == entity['authToken']

    def add_pass(self, serialNumber, authToken,
                 uid, fname, lname, zipcode,
                 offerImage, offerImageHighRes,
                 offerText, offerExpiration):

        pass_key = self.gds.key('Passes', '{}'.format(serialNumber))
        pass_entity = datastore.Entity(key=pass_key)
        pass_entity.update({

            # Auth info
            'serialNumber': serialNumber,
            'authToken': authToken,

            # User info
            'uid': uid,
            'fname': fname,
            'lname': lname,

            # Context info
            'zipcode': zipcode,

            # Offer info
            'offerImage': offerImage,
            'offerImageHighRes': offerImageHighRes,
            'offerText': offerText,
            'offerExpiration': offerExpiration,

            # Timestamp
            'lastUpdated': self.get_current_timestamp()

        })
        self.gds.put(pass_entity)

        return pass_entity

    def delete_pass(self, pass_serial):

        # WHEN?
        pass_key = self.gds.key('Passes', '{}'.format(pass_serial))
        self.gds.delete(pass_key)
        return

    def update_pass_expiration(self, serialNumber, offerExpiration):

        try:
            with self.gds.transaction():
                pass_key = self.gds.key('Passes', '{}'.format(serialNumber))
                pass_entity = self.gds.get(pass_key)
                if pass_entity:
                    pass_entity['offerExpiration'] = offerExpiration
                    pass_entity['lastUpdated'] = self.get_current_timestamp()
                    self.gds.put(pass_entity)
                    return 200
                else:
                    return 400
        except:
            return 400

    def get_current_timestamp(self):

        # Generate current timestamp
        now_utc = datetime.datetime.now(timezone('UTC'))
        now_timestamp = time.mktime(now_utc.timetuple())

        return  now_timestamp
