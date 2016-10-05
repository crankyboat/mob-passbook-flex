import logging
from gcloud import datastore
try:
    import simplejson as json
except ImportError:
    import json

class PlatformRecord(object):

    def __init__(self, datastoreClient):

        # Initialize gcloud client
        self.gds = datastoreClient

        # Datastore table

        #### Platform table ####
        # key = ('Platform', 'serialNumber')
        # fields = {'serialNumber', 'platform:{apple|android}}

    def record_platform(self, serialNumber, platform):

        logging.error('PLATFORM: {}'.format(platform))

        with self.gds.transaction():

            key = self.gds.key('Platform', '{}'.format(serialNumber))
            entity = self.gds.get(key)
            if not entity:
                entity = datastore.Entity(key=key)
                entity.update({
                    'serialNumber': '{}'.format(serialNumber),
                    'platform': '{}'.format(platform)
                })
            else:
                entity['platform'] = '{}'.format(platform)
            self.gds.put(entity)

    def get_platform(self, serialNumber):

        key = self.gds.key('Platform', '{}'.format(serialNumber))
        entity = self.gds.get(key)

        if entity:
            logging.error('GET PLATFORM: {}'.format(entity['platform']))
            return entity['platform']
        else:
            logging.error('GET PLATFORM NONE!')
            return None



