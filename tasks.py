import logging

from flask import current_app
from gcloud import pubsub, storage
import psq
import urllib3
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


# [START get_imgload_queue]
def get_imgload_queue():
    ps_client = pubsub.Client(project=current_app.config['PROJECT_ID'])
    return psq.Queue(ps_client, name='imgload',
                     extra_context=current_app.app_context)
# [END get_imgload_queue]


# [START load_img]
def load_img(img_url='', img_highres_url=''):

    http = urllib3.PoolManager()

    if img_url:
        hreq = http.request('GET', img_url, preload_content=False)
        img_file = StringIO(hreq.read())
    if img_highres_url:
        hreq = http.request('GET', img_highres_url, preload_content=False)
        img_highres_file = StringIO(hreq.read())
    hreq.release_conn()

    # Store images to blob stroage
    storage_client = storage.Client(project=current_app.config['PROJECT_ID'])
    bucket = storage_client.get_bucket(current_app.config['PROJECT_ID'])
    blob = bucket.blob('img.png', chunk_size=262144)
    blob.upload_from_file(img_file)
    blob = bucket.blob('img_highres.png', chunk_size=262144)
    blob.upload_from_file(img_highres_file)

    return
# [END load_img]


def get_img():

    # Get images from blob storage
    img = StringIO()
    imgHR = StringIO()
    storage_client = storage.Client(project=current_app.config['PROJECT_ID'])
    bucket = storage_client.get_bucket(current_app.config['PROJECT_ID'])

    try:
        blob = bucket.get_blob('img.png')
        blob.download_to_file(img)
        blob = bucket.get_blob('img_highres.png')
        blob.download_to_file(imgHR)
    except:
        raise

    img.seek(0)
    imgHR.seek(0)
    return img, imgHR

