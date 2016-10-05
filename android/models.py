import logging
import itertools
import datetime, time
from pytz import timezone
import config


class ClassRedemptionChannel:
    ONLINE = 'online'
    STORE = 'instore'
    BOTH = 'both'
    REDUCT = 'temporaryPriceReduction'


class ClassReviewStatus:
    DRAFT = 'draft'
    REVIEW = 'underReview'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class ObjectBarcodeType:
    AZTEC = 'aztec'
    CODEBAR = 'codabar'
    CODE128 = 'code128'
    CODE39 = 'code39'
    MATRIX = 'dataMatrix'
    EAN13 = 'ean13'
    EAN8 = 'ean8'
    ITF14 = 'itf14'
    PDF417 = 'pdf417'
    PDF417COMP = 'pdf417Compact'
    QRCODE = 'qrCode'
    TEXT = 'textOnly'
    UPCA = 'upcA'
    UPCE = 'upcE'


class ObjectState:
    ACTIVE = 'active'
    COMPLETE = 'completed'
    EXPIRED = 'expired'
    INACTIVE = 'inactive'


class OfferTemplate:
    def addLocation(self, lat, lng, name='', phone=''):

        location = {
            'kind': 'walletobjects#latLongPoint',
            'latitude': lat,
            'longitude': lng
        }

        if name or phone:
            location.update({'metadata': {'kind': 'walletobjects#locationMetadata'}})
            if name:
                location['metadata']['locationName'] = name
            if phone:
                location['metadata']['phoneNumber'] = phone

        self.locations.append(location)

    def addMessage(self, id, header, body, start_date='', end_date='',
                   action_uri='', action_description='',
                   image_uri='', image_description=''):

        message = {
            'id': id,
            'kind': 'walletobjects#walletObjectMessage',
            'header': header,
            'body': body
        }

        if start_date or end_date:
            message.update({'displayInterval': {'kind': 'walletobjects#timeInterval'}})
            if start_date:
                message['displayInterval']['start'] = {'date': start_date}
            if end_date:
                message['displayInterval']['end'] = {'date': end_date}
        if action_uri or action_description:
            message.update({'actionUri': {'kind': 'walletobjects#uri'}})
            if action_uri:
                message['actionUri']['uri'] = action_uri
            if action_description:
                message['actionUri']['description'] = action_description
        if image_uri or image_description:
            message.update({
                'image': {
                    'kind': 'walletobjects#image',
                    'sourceUri': {'kind': 'walletobjects#uri'}
                }
            })
            if image_uri:
                message['image']['sourceUri']['uri'] = image_uri
            if image_description:
                message['image']['sourceUri']['description'] = image_description

        self.messages.append(message)

    def addImageModule(self, uri, description=''):

        imageModule = {
            'mainImage': {
                'kind': 'walletobjects#image',
                'sourceUri': {
                    'kind': 'walletobjects#uri',
                    'uri': uri
                }
            }
        }

        if description:
            imageModule['mainImage']['sourceUri']['description'] = description

        self.imageModules.append(imageModule)

    def addTextModule(self, header, body):

        textModule = {
            'header': header,
            'body': body
        }
        self.textModules.append(textModule)

    def setInfoModule(self, max_row, max_col, info_labels, info_values,
                      show_last_updated_time=True):

        assert max_row * max_col == len(info_labels)
        assert max_row * max_col == len(info_values)

        infoModule = {
            'labelValueRows': [{'columns': []} for r in xrange(max_row)],
            'showLastUpdateTime': show_last_updated_time
        }
        for r, c in itertools.product(xrange(max_row), xrange(max_col)):
            label = info_labels[r * max_col + c]
            value = info_values[r * max_col + c]
            infoModule['labelValueRows'][r]['columns'].append({'label': label, 'value': value})

        self.infoModule = infoModule

    def addLinksModule(self, uri_list, description_list):

        assert len(uri_list) == len(description_list)

        linksModule = {'uris': []}
        for (uri, description) in zip(uri_list, description_list):
            linksModule['uris'].append({
                'kind': 'walletobjects#uri',
                'uri': uri
            })
            if description:
                linksModule['uris'][-1]['description'] = description

        self.linksModule = linksModule


class OfferClass(OfferTemplate):
    def __init__(self, issuer_id, class_id, issuer_name, provider,
                 title, title_image_uri, title_image_description='',
                 details='', fine_print=''):

        # Fold info
        self.id = '{}.{}'.format(issuer_id, class_id)
        self.issuerName = issuer_name
        self.provider = provider
        self.title = title
        self.titleImageUri = title_image_uri
        self.titleImageDescription = title_image_description

        # Class info
        self.details = details
        self.finePrint = fine_print
        self.homepageUri = None
        self.helpUri = None

        # Optional info modules
        self.locations = []
        self.imageModules = []
        self.messages = []
        self.textModules = []
        self.infoModule = None
        self.linksModule = None

    def json_dict(self):

        d = {

            'kind': 'walletobjects#offerClass',
            'id': self.id,
            'issuerName': self.issuerName,
            'provider': self.provider,
            'redemptionChannel': ClassRedemptionChannel.BOTH,
            'allowMultipleUsersPerObject': True,

            'title': self.title,
            'titleImage': {
                'kind': 'walletobjects#image',
                'sourceUri': {
                    'kind': 'walletobjects#uri',
                    'uri': self.titleImageUri,
                    'description': self.titleImageDescription  # where does this appear?
                }
            },

            'renderSpecs': [
                {
                    'viewName': 'g_list',
                    'templateFamily': '1.offer_list'
                },
                {
                    'viewName': 'g_expanded',
                    'templateFamily': '1.offer_expanded'
                }
            ],

            # 'reviewStatus': ClassReviewStatus.DRAFT,  # 'REVEW' for production
            'reviewStatus': ClassReviewStatus.REVIEW,
            'review': {
                'comments': ''
            }
            # 'locations': [
            #     {
            #         'kind': 'walletobjects#latLongPoint',
            #         'latitude': double,
            #         'longitude': double,
            #         'metadata': {
            #             'kind': 'walletobjects#locationMetadata',
            #             'locationName': string,
            #             'phoneNumber': string
            #         }
            #     }
            # ],
            # 'messages': [
            #     {
            #         'kind': 'walletobjects#walletObjectMessage',
            #         'header': string,
            #         'body': string,
            #         'displayInterval': {
            #             'kind': 'walletobjects#timeInterval',
            #             'start': {
            #                 'date': datetime
            #             },
            #             'end': {
            #                 'date': datetime
            #             }
            #         },
            #         'actionUri': {
            #             'kind': 'walletobjects#uri',
            #             'uri': string,
            #             'description': string
            #         },
            #         'image': {
            #             'kind': 'walletobjects#image',
            #             'sourceUri': {
            #                 'kind': 'walletobjects#uri',
            #                 'uri': string,
            #                 'description': string
            #             }
            #         },
            #         'id': string
            #     }
            # ],
            # 'imageModulesData': [
            #     {
            #         'mainImage': {
            #             'kind': 'walletobjects#image',
            #             'sourceUri': {
            #                 'kind': 'walletobjects#uri',
            #                 'uri': string,
            #                 'description': string
            #             }
            #         }
            #     }
            # ],
            # 'textModulesData': [
            #     {
            #         'header': string,
            #         'body': string
            #     }
            # ],
            # 'infoModuleData': {
            #
            #     'labelValueRows': [
            #         {
            #
            #             'columns': [
            #                 {
            #                     'label': string,
            #                     'value': string
            #                 }
            #             ]
            #         }
            #     ],
            #     'showLastUpdateTime': boolean
            # },
            # 'linksModuleData': {
            #     'uris': [
            #         {
            #             'kind': 'walletobjects#uri',
            #             'uri': string,
            #             'description': string
            #         }
            #     ]
            # },
            # 'homepageUri': {
            #     'kind': 'walletobjects#uri',
            #     'uri': string,
            #     'description': string
            # },
            # 'helpUri': {
            #     'kind': 'walletobjects#uri',
            #     'uri': string,
            #     'description': string
            # },

        }

        # Class only
        if self.details:
            d.update({'details': self.details})
        if self.finePrint:
            d.update({'finePrint': self.finePrint})
        # if self.homepageUri:
        #     d.update({'homepageUri': self.homepageUri})
        if self.helpUri:
            d.update({'helpUri': self.helpUri})

        # Optional
        if self.locations:
            d.update({'locations': self.locations})
        if self.messages:
            d.update({'messages': self.messages})
        if self.imageModules:
            d.update({'imageModulesData': self.imageModules})
        if self.textModules:
            d.update({'textModulesData': self.textModules})
        if self.infoModule:
            d.update({'infoModuleData': self.infoModule})
        if self.linksModule:
            d.update({'linksModuleData': self.linksModule})

        return d

    # def addHomepage(self, uri, description=''):
    #
    #     homepageUri = {
    #         'kind': 'walletobjects#uri',
    #         'uri': uri
    #     }
    #
    #     if description:
    #         homepageUri['description'] = description
    #
    #     self.homepageUri = homepageUri

    def addHelp(self, uri, description=''):

        helpUri = {
            'kind': 'walletobjects#uri',
            'uri': uri
        }

        if description:
            helpUri['description'] = description

        self.helpUri = helpUri


class OfferObject(OfferTemplate):

    def __init__(self, issuer_id, class_id, object_id,
                 expiration_datetime, start_datetime=None, version='1'):

        # Fold info
        self.id = '{}.{}'.format(issuer_id, object_id)
        self.classId = '{}.{}'.format(issuer_id, class_id)
        self.validTimeIntervalStart = None
        self.validTimeIntervalEnd = None
        self.validTimeIntervalStartDatetime = None
        self.validTimeIntervalEndDatetime = None
        self.setValidTimeInterval('validTimeIntervalStart', start_datetime)
        self.setValidTimeInterval('validTimeIntervalEnd', expiration_datetime)
        self.barcode = None

        # State info (subject to change: 'active'/'completed'/'expired'/'inactive')
        active = self.validTimeIntervalStartDatetime < self.validTimeIntervalEndDatetime
        self.state = ObjectState.ACTIVE if active else ObjectState.EXPIRED
        self.version = version

        # Optional info
        self.locations = []
        self.imageModules = []
        self.messages = []
        self.textModules = []
        self.infoModule = None
        self.linksModule = None

    def json_dict(self):

        d = {

            'kind': 'walletobjects#offerObject',
            'id': self.id,
            'classId': self.classId,
            'version': self.version,
            'state': self.state,
            'validTimeInterval': {
                'kind': 'walletobjects#timeInterval',
                'start': {
                    'date': self.validTimeIntervalStart
                },
                'end': {
                    'date': self.validTimeIntervalEnd
                }
            },

            # 'hasUsers': True,  # Set by platform
            # 'classReference': {}  # offerclass Resource # Set by platform?

        }

        if self.barcode:
            d.update({'barcode': self.barcode})

        # Optional
        if self.locations:
            d.update({'locations': self.locations})
        if self.messages:
            d.update({'messages': self.messages})
        if self.imageModules:
            d.update({'imageModulesData': self.imageModules})
        if self.textModules:
            d.update({'textModulesData': self.textModules})
        if self.infoModule:
            d.update({'infoModuleData': self.infoModule})
        if self.linksModule:
            d.update({'linksModuleData': self.linksModule})

        return d

    def addBarcode(self, value, alternate_text='\t', codetype=ObjectBarcodeType.QRCODE):

        barcode = {
            'kind': 'walletobjects#barcode',
            'type': codetype,
            'value': value,
            'alternateText': alternate_text
        }

        self.barcode = barcode

    def setValidTimeInterval(self, attr, value):

        if isinstance(value, datetime.datetime):
            odatetime = value.astimezone(timezone('UTC'))
            setattr(self, attr + 'Datetime', odatetime)
            setattr(self, attr, odatetime.strftime('%Y-%m-%dT%H:%M:%S.00Z'))

        elif isinstance(value, str) or isinstance(value, unicode):  # 9/15/2016
            try:
                odate = datetime.datetime.strptime(value, '%m/%d/%Y')
                otime = datetime.time(23, 59, 59, 0)
                odatetime = datetime.datetime.combine(odate, otime)
                odatetime = timezone(config.DEFAULT_TIMEZONE).localize(odatetime)
                odatetime = odatetime.astimezone(timezone('UTC'))
                setattr(self, attr + 'Datetime', odatetime)
                setattr(self, attr, odatetime.strftime('%Y-%m-%dT%H:%M:%S.00Z'))
            except:
                logging.error('Bad validTimeInterval value.')
                setattr(self, attr + 'Datetime', None)
                setattr(self, attr, None)

        else:  # None
            now_utc = datetime.datetime.now(timezone('UTC'))
            setattr(self, attr + 'Datetime', now_utc)
            setattr(self, attr, now_utc.strftime('%Y-%m-%dT%H:%M:%S.00Z'))


class RequestJwt(object):

    def __init__(self, ser_acc_email, domains=[]):
        self.serviceAccountEmailAddress = ser_acc_email
        self.origins = domains
        self.offerClasses = []
        self.offerObjects = []
        self.loyaltyClasses = []
        self.loyaltyObjects = []

    def json_dict(self):
        jwt = {
            'iss': self.serviceAccountEmailAddress,
            'aud': 'google',
            'typ': 'savetowallet',
            'iat': int(time.time()),
            'payload': {
                'webserviceResponse': {
                    'result': 'approved',
                    'message': 'Success.'
                },
                'loyaltyClasses': [],  # Loyalty classes
                'loyaltyObjects': [],  # Loyalty objects
                'offerClasses': [],  # Offer classes
                'offerObjects': []  # Offer objects
            },
            'origins': []
        }

        if self.origins:
            jwt.update({'origins': self.origins})
        for loyaltyClass in self.loyaltyClasses:
            jwt['payload']['loyaltyClasses'].append(loyaltyClass.json_dict())
        for loyaltyObject in self.loyaltyObjects:
            jwt['payload']['loyaltyObjects'].append(loyaltyObject.json_dict())
        for offerClass in self.offerClasses:
            jwt['payload']['offerClasses'].append(offerClass.json_dict())
        for offerObject in self.offerObjects:
            jwt['payload']['offerObjects'].append(offerObject.json_dict())

        return jwt


if __name__ == '__main__':
    o_class = OfferObject(1, 2, 3, '9/1/2016')
    print 'Start: ' + o_class.validTimeIntervalStart
    print 'End: ' + o_class.validTimeIntervalEnd
    print o_class.state