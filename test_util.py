import unittest
import zipquery
from test_delayed_assert import expect, assert_expectations

class UtilTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_zipquery(self):
        result1 = zipquery.get_store_from_zip(92122) # California
        result2 = zipquery.get_store_from_zip(92111) # California
        result3 = zipquery.get_store_from_zip(85001) # Outside California
        result4 = zipquery.get_store_from_zip(00000) # Nonexistent
        expect(len(result1) <= 10, "Result should contain at most 10 locations.")
        expect(len(result2) <= 10, "Result should contain at most 10 locations.")
        expect(len(result3) <= 10, "Result should contain at most 10 locations.")
        expect(len(result4) <= 10, "Result should contain at most 10 locations.")
        assert_expectations()


if __name__ == '__main__':
    unittest.main()
