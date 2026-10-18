"""Host-only IMS share-redaction tests; never start a device capture."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/diagnostics/capture_ims_wifi_cycle_termux.sh'

@unittest.skipUnless(shutil.which('bash') and shutil.which('sed'), 'bash and sed required')
class WifiCyclePrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding='utf-8')
        p = subprocess.run(['bash', '-n', str(SCRIPT)], capture_output=True, text=True)
        if p.returncode:
            raise AssertionError(p.stderr)
        match = re.search(r'(?ms)^redact_stream\(\) \{\n.*?^\}', cls.source)
        if match is None:
            raise AssertionError('redactor missing')
        cls.redactor = match.group(0) + '\nredact_stream\n'

    def redact(self, value):
        p = subprocess.run(['bash', '-c', self.redactor], input=value, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_synthetic_subscriber_identities(self):
        samples = [
            'IMSI=466920123456789', 'ICCID=89888612345678901234',
            'IMEI: 355000123456789', 'MSISDN=0912345678',
            'IMPI: 466920123456789@ims.mnc001.mcc466.3gppnetwork.org',
            'IMPU=sip:+886912345678@ims.example.org',
            'P-Asserted-Identity: <sip:+886912345678@ims.example.org>',
            'Contact: <sips:private-user@ims.example.org;transport=tls>',
            'tel:+886912345678', 'urn:gsma:imei:355000123456789',
            'subscriberId=466920123456789', 'SSID="PrivateWifi"',
            'BSSID=aa:bb:cc:dd:ee:ff', 'user@example.org',
            '203.0.113.21 2001:db8:abcd::1',
        ]
        redacted = self.redact('\n'.join(samples)+'\n')
        for secret in (
            '466920123456789', '89888612345678901234', '355000123456789',
            '0912345678', '886912345678', 'private-user', 'PrivateWifi',
            'aa:bb:cc:dd:ee:ff', 'user@example.org', '203.0.113.21', '2001:db8:abcd::1'
        ):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, redacted)

    def test_preserves_failure_codes(self):
        original = 'SIP;cause=503; AAA: result_code=0 exp_result_code=5065 W2L callId=487\n'
        self.assertEqual(self.redact(original), original)

    def test_safe_share_paths(self):
        s = self.source
        self.assertRegex(s, r'dumpsys secims[^\n]*\| redact_stream')
        self.assertIn('"$notes" | redact_stream >>"$OBSERVATIONS"', s)
        self.assertIn('"$manual_notes" | redact_stream >>"$OBSERVATIONS"', s)
        self.assertIn('} | redact_stream >"$SHARE_ROOT/runtime_identity.txt"', s)
        self.assertIn('sanitize_share_files\n\nSHARE_ARCHIVE=', s)
        self.assertLess(s.index('sanitize_share_files\n\nSHARE_ARCHIVE='),
                        s.index('tar -czf "$SHARE_ARCHIVE"'))

if __name__ == '__main__':
    unittest.main()
