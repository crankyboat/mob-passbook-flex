import logging

from flask import current_app
from gcloud import pubsub, storage
import psq
import urllib3
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


def get_imgload_queue():
    ps_client = pubsub.Client(project=current_app.config['PROJECT_ID'])
    return psq.Queue(ps_client, name='imgload',
                     extra_context=current_app.app_context)


def get_bucket():
    storage_client = storage.Client(project=current_app.config['PROJECT_ID'])
    bucket = storage_client.get_bucket(current_app.config['PROJECT_ID'])
    return bucket


def load_img(imgUrl='', imgSerial='', imgFilename=''):

    if not imgUrl or not imgSerial or not imgFilename:
        return

    http = urllib3.PoolManager()
    hreq = http.request('GET', imgUrl, preload_content=False)
    imgFile = StringIO(hreq.read())
    hreq.release_conn()

    # Store images to blob stroage
    try:
        bucket = get_bucket()
        blob = bucket.blob('{}_{}.png'.format(imgSerial, imgFilename), chunk_size=262144)
        blob.upload_from_file(imgFile)
    except:
        raise

    return


def get_img(imgSerial='', imgFilename=''):

    if not imgSerial or not imgFilename:
        return None

    # Get image from blob storage
    try:
        bucket = get_bucket()
        imgFile = StringIO()
        blob = bucket.get_blob('{}_{}.png'.format(imgSerial, imgFilename))
        blob.download_to_file(imgFile)
    except:
        raise

    imgFile.seek(0)
    return imgFile


def delete_img(imgSerial='', imgFilename=''):

    if not imgSerial or not imgFilename:
        return

    # Delete image from blob storage
    try:
        bucket = get_bucket()
        bucket.delete_blob('{}_{}.png'.format(imgSerial, imgFilename))
    except:
        logging.error('PSQWORKER IMGLOAD DELETE ERROR.')

    return


def cleanup():

    # Delete all images from storage
    try:
        bucket = get_bucket()
        for blob in bucket.list_blobs():
            blob.delete()
        return 200
    except:
        logging.error('PSQWORKER CLEANUP ERROR.')
        return 400


