import logging
try:
    import simplejson as json
except ImportError:
    import json

import ssl
import apns
import urllib3
import datetime
from uuid import uuid4, UUID


def push_notification_apple(pushToken):

    if apns.make_ssl_context:
        get_context = apns.make_ssl_context
    else:
        get_context = apns.make_ossl_context

    # Connect
    context = get_context(
        certfile='static/cert/certificate.pem',
        keyfile='static/cert/key.pem',
        password=''
    )
    push_id = uuid4().hex

    # PASSES MUST BE PROCESSED BY THE PRODUCTION APNS! NOT DEVELOPMENT!
    apns_client = apns.Client(ssl_context=context, sandbox=False)
    apns_message_exp = datetime.datetime(2016, 12, 31)  # HACK
    apns_message = apns.Message(id=push_id, expiration=apns_message_exp)
    apns_message.payload = {}
    apns_id = apns_client.push(apns_message, pushToken)
    logging.error('PUSH APPLE message id: {}'.format(UUID(push_id)))
    logging.error('PUSH APPLE APNS id: {}'.format(apns_id))

    return 'Push iOS!\n' \
           'Openssl: {}\n' \
           'Push token:{}\n' \
           'APNS id:{}'.format(ssl._OPENSSL_API_VERSION, pushToken, apns_id)


def push_notification_android(pushToken):

    # HACK Retrieve passType
    passTypeIdentifier = 'pass.com.mobivity.scannerdemo'
    walletPassApiKey = '5d2c8fb3e1e34dab898fe14a24f0cef0'

    # Post a request to WalletPass API
    http = urllib3.PoolManager()

    push_message_encoded = json.dumps({
        'passTypeIdentifier': '{}'.format(passTypeIdentifier),
        'pushTokens': ['{}'.format(pushToken)]
    }).encode('utf-8')

    hreq = http.request(
        method='POST',
        url='https://walletpasses.appspot.com/api/v1/push',
        body=push_message_encoded,
        headers={'Content-Type': 'application/json',
                 'Authorization': '{}'.format(walletPassApiKey)}
    )
    logging.error('PUSH ANDROID: {}, {}'.format(hreq.status, hreq.data))

    return 'Push Android!\n' \
           'Push token:{}\n' \
           'Status: {}\n' \
           'Response: {}'.format(pushToken, hreq.status, hreq.data)
