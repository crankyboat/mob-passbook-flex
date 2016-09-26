import unittest
from main import app
from delayed_assert import expect, assert_expectations
from gcloud import storage, datastore
try:
    import simplejson as json
except ImportError:
    import json


class AppTestCase(unittest.TestCase):

    def setUp(self):

        # Flask app
        self.client = app.test_client()
        self.auth = 'MobivityOffer 2ec6c5e11fe449d090cacae58d3cfda2'

        self.pass_token = 'vxwxd7J8AlNNFPS8k0a0FfUFtq0ewzFdc'
        self.pass_params = 'uid=1234567890&fname=Oliver&lname=Twist&' \
                           'offerText=FREE%206-INCH%20CLASSIC%20SUB%20WITH%20PURCHASE%20OF%20A%2030%20OZ%20DRINK&' \
                           'offerImage=https://s3-us-west-2.amazonaws.com/donotdeletethis/strip.png&' \
                           'offerImageHighRes=https://s3-us-west-2.amazonaws.com/donotdeletethis/strip%402x.png&' \
                           'zipcode=92122&offerExpiration=12/31/2016'
        self.pass_serial = '0933024510'
        self.pass_hexsig = '0910075651'
        self.pass_newexp = '1/1/2017'
        self.devicelibid = '0330268080227531129'
        self.passtypeid = 'mobivity.subways.pass'

        self.push_token = '23939889'

        self.bogus_serial = '0800000000'
        self.bogus_hexsig = '0800000111'
        self.bogus_devicelibid = '0227531129033026808'
        self.bogus_token = '0800111111'

        # Gcloud
        self.storage = storage.Client(project=app.config['PROJECT_ID'])
        self.ds = datastore.Client(project=app.config['PROJECT_ID'])

    def tearDown(self):
        # Remove all fake entries from datastore
        key = self.ds.key('Passes', '{}'.format(self.pass_serial))
        if self.ds.get(key):
            self.ds.delete(key)
        key = self.ds.key('Device', '{}'.format(self.devicelibid))
        if self.ds.get(key):
            self.ds.delete(key)
        key = self.ds.key('Registration', '{}'.format(self.devicelibid),
                           'RegistrationPassType', '{}'.format(self.passtypeid))
        if self.ds.get(key):
            self.ds.delete(key)


    # Utils
    def createPass(self):
        return self.client.get('/pass?serialNumber={}&hexSignature={}&{}'.format(
            self.pass_serial, self.pass_hexsig, self.pass_params))

    def createRegistration(self):
        return self.client.post(
            '/passkit/v1/devices/{}/registrations/{}/{}'.format(self.devicelibid, self.passtypeid, self.pass_serial),
            headers={'Authorization': 'ApplePass {}'.format(self.pass_token)},
            content_type='application/json',
            data=json.dumps({'pushToken': self.push_token})
        )

    def deleteRegistration(self):
        return self.client.delete(
            '/passkit/v1/devices/{}/registrations/{}/{}'.format(self.devicelibid, self.passtypeid, self.pass_serial),
            headers={'Authorization': 'ApplePass {}'.format(self.pass_token)},
            content_type='application/json',
            data=json.dumps({'pushToken': self.push_token})
        )


    # WEB

    def test_generate_index(self):
        rv = self.client.get('/?{}'.format(self.pass_params))
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        expect(rv.headers['Content-Type'] == 'text/html; charset=utf-8', 'Content type should be html.')
        assert_expectations()

    def test_generate_pass(self):
        rv = self.createPass()
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        expect(rv.headers['Content-Type'] == 'application/vnd.apple.pkpass', 'Content type should be a wallet pass.')
        expect(rv.headers['Last-Modified'], 'Last-Modified header should be set.')
        pass_key = self.ds.key('Passes', '{}'.format(self.pass_serial))
        expect(self.ds.get(pass_key), 'Pass should be created on gcloud datastore.')
        assert_expectations()


    # PASSKIT

    def test_registration_bogus_token(self):
        rv = self.client.post(
            '/passkit/v1/devices/{}/registrations/{}/{}'.format(self.devicelibid, self.passtypeid, self.pass_serial),
            headers={'Authorization': 'ApplePass {}'.format(self.bogus_token)}
        )
        expect(rv.status_code == 401, 'Status code should be 401 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_registration_new(self):
        rv = self.createRegistration()
        expect(rv.status_code == 201, 'Status code should be 201 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_registration_repeat(self):
        self.createRegistration()
        rv = self.createRegistration()
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_unregistration(self):
        rv = self.deleteRegistration()
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_unregistration_bogus(self): # Returns 200 since doesn't matter
        rv = self.client.delete(
            '/passkit/v1/devices/{}/registrations/{}/{}'.format(self.bogus_devicelibid, self.passtypeid, self.bogus_serial),
            headers={'Authorization': 'ApplePass {}'.format(self.pass_token)},
            content_type='application/json',
            data=json.dumps({'pushToken': self.push_token})
        )
        expect(rv.status_code == 200, 'Status code should be 400 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_getserial_all(self):
        self.createRegistration()
        rv = self.client.get('/passkit/v1/devices/{}/registrations/{}'.format(self.devicelibid, self.passtypeid))
        j = json.loads(rv.data)
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        expect(rv.headers['Content-Type'] == 'application/json', 'Content type should be json but is {}.'.format(rv.headers['Content-Type']))
        expect(self.pass_serial in j['serialNumbers'], 'List returned should contain registered serial number.')
        assert_expectations()

    def test_getserial_bogus(self):
        rv = self.client.get('/passkit/v1/devices/{}/registrations/{}'.format(self.bogus_devicelibid, self.passtypeid))
        expect(rv.status_code == 204, 'Status code should be 204 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_getserial_new(self): # Should return nothing
        self.createRegistration()
        rv = self.client.get('/passkit/v1/devices/{}/registrations/{}?passesUpdatedSince=2874501139'.format(self.devicelibid, self.passtypeid))
        expect(rv.status_code == 204, 'Status code should be 204 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_getupdate_unconditional(self):
        self.createPass()
        pass_key = self.ds.key('Passes', '{}'.format(self.pass_serial))
        expect(self.ds.get(pass_key), 'Pass should be created on gcloud datastore.')
        rv = self.client.get(
            '/passkit/v1/passes/{}/{}'.format(self.passtypeid, self.pass_serial),
            headers={'Authorization': 'ApplePass {}'.format(self.pass_token)}
        )
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        expect(rv.headers['Content-Type'] == 'application/vnd.apple.pkpass', 'Content type should be a wallet pass.')
        expect(rv.headers['Last-Modified'], 'Last-Modified header should be set.')
        assert_expectations()

    def test_getupdate_ifmodifiedsince(self):
        self.createPass()
        pass_key = self.ds.key('Passes', '{}'.format(self.pass_serial))
        expect(self.ds.get(pass_key), 'Pass should be created on gcloud datastore.')
        rv = self.client.get(
            '/passkit/v1/passes/{}/{}'.format(self.passtypeid, self.pass_serial),
            headers={'Authorization': 'ApplePass {}'.format(self.pass_token), 'If-Modified-Since': 'Thu, 05 Dec 2016 19:43:31 GMT'}
        )
        expect(rv.status_code == 304, 'Status code should be 304 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_getupdate_bogus(self):
        rv = self.client.get(
            '/passkit/v1/passes/{}/{}'.format(self.passtypeid, self.bogus_serial),
            headers={'Authorization': 'ApplePass {}'.format(self.pass_token)}
        )
        expect(rv.status_code == 400, 'Status code should be 400 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_log(self):
        log_message = 'This is an example log message.'
        rv = self.client.post('/passkit/v1/log', content_type='application/json', data=json.dumps({'logs': log_message}))
        j = json.loads(rv.data)
        expect(rv.status_code == 200, 'Status code should be 200 but is {}'.format(rv.status_code))
        expect(rv.headers['Content-Type'] == 'application/json', 'Content type should be json but is {}.'.format(rv.headers['Content-Type']))
        expect(j['logs'] == log_message, 'Log message should be echoed.')
        assert_expectations()


    # PASSKIT SUPPORT

    def test_redeem_no_auth(self):
        rv = self.client.post('/pass/redeem?serialNumber={}'.format(self.pass_serial))
        expect(rv.status_code == 401, 'Status code should be 401 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_redeem_bogus_pass(self):
        rv = self.client.post('/pass/redeem?serialNumber={}'.format(self.bogus_serial),
                              headers={'Authorization': self.auth})
        expect(rv.status_code == 400, 'Status code should be 400 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_redeem(self):
        self.createPass()
        pass_key = self.ds.key('Passes', '{}'.format(self.pass_serial))
        expect(self.ds.get(pass_key), 'Pass should be created on gcloud datastore.')
        rv = self.client.post('/pass/redeem?serialNumber={}'.format(self.pass_serial),
                              headers={'Authorization': self.auth})
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_update_bogus_pass(self):
        rv = self.client.post('/pass/update?serialNumber={}&offerExpiration=1/1/3016'.format(self.bogus_serial),
                              headers={'Authorization': self.auth})
        expect(rv.status_code == 400, 'Status code should be 400 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_update(self):
        self.createPass()
        pass_key = self.ds.key('Passes', '{}'.format(self.pass_serial))
        expect(self.ds.get(pass_key), 'Pass should be created on gcloud datastore.')
        rv = self.client.post('/pass/update?serialNumber={}&offerExpiration=1/1/3016'.format(self.pass_serial),
                              headers={'Authorization': self.auth})
        expect(rv.status_code == 200, 'Status code should be 200 but is {}.'.format(rv.status_code))
        assert_expectations()

    def test_push_bogus_device(self):
        rv = self.client.post('/push/{}'.format(self.bogus_devicelibid), headers={'Authorization': self.auth})
        expect(rv.status_code == 400, 'Status code should be 400 but is {}.'.format(rv.status_code))
        assert_expectations()


if __name__ == '__main__':
    unittest.main()
