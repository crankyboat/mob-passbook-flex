import logging

from flask import current_app
from gcloud import pubsub, datastore
import psq
import urllib3
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


# [START get_imgload_queue]
def get_imgload_queue():
    ps_client = pubsub.Client(project=current_app.config['PROJECT_ID'])
    ds_client = datastore.Client(project=current_app.config['PROJECT_ID'])
    return psq.Queue(
        ps_client,
        name='imgload',
        storage=psq.DatastoreStorage(ds_client),
        extra_context=current_app.app_context)
# [END get_imgload_queue]


# [START load_img]
def load_img(imgUrl='', imgHRUrl=''):
    http = urllib3.PoolManager()

    if imgUrl:
        req = http.request('GET', imgUrl, preload_content=False)
        offerimg = req.read()
        req.release_conn()
    if imgHRUrl:
        req = http.request('GET', imgHRUrl, preload_content=False)
        offerimgHR = req.read()
        req.release_conn()

    return offerimg, offerimgHR
# [END load_img]

def dumbdumb():
    return 'DUMB DUMB!'