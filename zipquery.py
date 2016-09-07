import logging
import googlemaps
from gcloud import bigquery

GEOCODE_API_KEY = 'AIzaSyDiiA_SRmtBpv-SmR1jsPLJHpgg0l9a0Bk'
BIGQUERY_PROJECT_ID = 'kinetic-anvil-797'

def get_store_from_zip(zipcode):

    # Lookup zipcode lat/lng bound
    # Using geocoding API
    geo_key = GEOCODE_API_KEY
    geo_client = googlemaps.Client(geo_key)
    results = geo_client.geocode(zipcode)
    ne = results[0]['geometry']['bounds']['northeast']
    sw = results[0]['geometry']['bounds']['southwest']
    bounds = (sw['lat'], ne['lat'], sw['lng'], ne['lng'])
    logging.info('ZIP BOUNDS: {}'.format(bounds))

    # Query store locations within lat/lng bound
    # Depends on Christian's tables!
    client = bigquery.Client(project=BIGQUERY_PROJECT_ID)
    QUERY = """
        SELECT lat,lng
        FROM christian_playground.subway_coords
        WHERE (lat BETWEEN {} AND {})
        AND (lng BETWEEN {} AND {})
    """.format(*bounds)
    query = client.run_sync_query(QUERY)
    query.timeout_ms = 1000
    query.run()
    logging.info('ZIP STORES: {}'.format(query.rows[:10]))

    return query.rows[:10]