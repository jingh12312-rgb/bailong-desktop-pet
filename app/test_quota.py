import unittest,json,threading,tempfile
from pathlib import Path
from unittest.mock import patch
import quota

class Tests(unittest.TestCase):
    def test_transport_error_retries_once(self):
        error=quota.classify_error('failed to fetch codex rate limits: error sending request for url (https://example.invalid)','rate_limits')
        with patch('quota._read_quota_once',side_effect=[error,{'rateLimits':{}}]) as read,patch('quota.time.sleep'):
            self.assertEqual(quota.read_quota(log_path=False),{'rateLimits':{}})
            self.assertEqual(read.call_count,2)
    def test_auth_failure_does_not_retry(self):
        error=quota.classify_error('401 Unauthorized')
        with patch('quota._read_quota_once',side_effect=error) as read:
            with self.assertRaises(quota.QuotaFailure):quota.read_quota(log_path=False)
            self.assertEqual(read.call_count,1)
    def test_retry_is_bounded_and_cancelable(self):
        with patch('quota._read_quota_once',side_effect=quota.classify_error('error sending request')) as read,patch('quota.time.sleep'):
            with self.assertRaises(quota.QuotaFailure):quota.read_quota(log_path=False)
            self.assertEqual(read.call_count,2)
        stop=threading.Event();stop.set()
        with patch('quota._read_quota_once',side_effect=quota.classify_error('error sending request')) as read:
            with self.assertRaises(quota.QuotaFailure):quota.read_quota(cancel=stop,log_path=False)
            self.assertEqual(read.call_count,1)
    def test_diagnostics_do_not_contain_raw_url_or_tokens(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'log.jsonl'
            error=quota.classify_error('error sending request for url https://example.invalid/?token=FAKE_TEST_VALUE')
            quota.log_attempt(1,.2,error,path)
            data=path.read_text(encoding='utf-8');self.assertNotIn('http',data);self.assertNotIn('FAKE_TEST_VALUE',data)
            self.assertEqual(json.loads(data)['result'],'network')

if __name__=='__main__':unittest.main()
