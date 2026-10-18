"""Synthetic, host-only privacy tests. Never contact a device or use real logs."""
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/diagnostics/capture_ims_wifi_cycle_termux.sh'
SOURCE = SCRIPT.read_text(encoding='utf-8')


def function(name):
    match = re.search(r'(?ms)^' + name + r'\(\) \{\n.*?^\}', SOURCE)
    if match is None:
        raise AssertionError(f'{name} missing')
    return match.group(0) + '\n'


REDACTOR = function('redact_stream')
DIAGNOSTIC = ('10-18 12:34:56.789 1234 5678 I M11W2L: W2L L2W '
              'SIP;cause=503; AAA: result_code=0 exp_result_code=5065 '
              'callId=487 sessionId=12 RAT=18 target=LTE retry=-1 duration_ms=120000\n')
# These identifiers are invented test fixtures, not captured subscriber data.
SECRET_LINES = [
    'IMSI=466920123456789', 'ICCID=89888612345678901234',
    'IMEI: 355000123456789', 'MSISDN=0912345678',
    'IMPI: fixture-user@ims.example.org',
    'IMPU=sip:+886912345678@ims.example.org',
    'P-Asserted-Identity: "Fixture Display Name" <sip:+886912345678@ims.example.org>',
    'Contact: <sips:fixture-user@ims.example.org;transport=tls>',
    'tel:+886912345678', 'urn:gsma:imei:355000123456789',
    'subscriberId=466920123456789', 'SSID="Fixture Wifi"',
    'BSSID=aa:bb:cc:dd:ee:ff', 'fixture-user@example.org',
    '203.0.113.21 fe80::abcd:1234', 'call 0912-345-678 or 0912 345 678',
]
REVIEW_LINES = [
    'M11W2L origNumber:0912-345-678',
    'M11W2L WIFI_SSID: SecretHome',
    'IpSec ipsec_key: CAFEBABECAFEBABECAFEBABE',
    'Epdg Authorization=Bearer fixture-token',
]
REVIEW_SECRETS = ('0912-345-678', 'SecretHome', 'CAFEBABECAFEBABECAFEBABE', 'fixture-token')
SECRET_LINES.extend(REVIEW_LINES)
PRIVATE_BYTES = (DIAGNOSTIC + '\n'.join(SECRET_LINES) + '\n').encode()


@unittest.skipUnless(shutil.which('bash') and shutil.which('sed'), 'bash and sed required')
class WifiCyclePrivacyTests(unittest.TestCase):
    def redact(self, value):
        p = subprocess.run(['bash', '-eu', '-c', REDACTOR + 'redact_stream'],
                           input=value, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_bash_syntax(self):
        p = subprocess.run(['bash', '-n', str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_synthetic_subscriber_identities(self):
        redacted = self.redact('\n'.join(SECRET_LINES) + '\n')
        for secret in ('466920123456789', '89888612345678901234', '355000123456789',
                       '0912345678', '886912345678', 'fixture-user', 'Fixture Wifi',
                       'Fixture Display Name', 'aa:bb:cc:dd:ee:ff', '203.0.113.21',
                       'fe80::abcd:1234', '0912-345-678', '0912 345 678'):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, redacted)

    def test_preserves_timestamps_and_diagnostics(self):
        for line in (DIAGNOSTIC, '12:34:56.789\n', '00:00:00.000 23:59:59.999\n',
                     '2026-10-18T12:34:56.789+08:00\n',
                     '12:34:56.123456789 00:00:00.000000000 00:00:09.12345678\n',
                     '2026-10-18T12:34:56Z captured_at=2026-10-18T12:34:56+00:00\n',
                     'phase=cycle1_vowifi marker=SNAPSHOT_lte_20261018_123456\n',
                     'epdg_data0 state=UP rmnet_data1 IMS slot=0 cause=503 5065\n',
                     'std::function Result::toString\n',
                     'IpSec enc cbc(aes) cause=503 exp_result_code=5065\n',
                     'Phone Id = 0 iwlan_handover_policy_string_array=source=IWLAN,target=EUTRAN\n',
                     'telephony_jar_sha256=' + 'abc123456789def01' * 4 + '\n'):
            with self.subTest(line=line):
                self.assertEqual(self.redact(line), line)

    def test_ipv6_forms_and_scope(self):
        addresses = ['fe80::1', 'fe80::abcd:1234', '::', '::1', '2001:db8::',
                     '2001:db8:1::2:3:4', '01:02:03:04:05:06:07:08', '2001:db8:0:1:2:3:4:5',
                     '::ffff:192.0.2.21', '::192.0.2.21',
                     '2001:db8:1:2:3:4:192.0.2.21', '2001:db8::192.0.2.21',
                     'FE80::ABCD:1234%wlan0', '[fe80::1%25wlan0]:5060', 'fe80::1/64']
        for address in addresses:
            with self.subTest(address=address):
                self.assertIn('[redacted-ipv6]', self.redact(address + '\n'))
                self.assertNotIn('192.0.2.21', self.redact(address + '\n'))
                self.assertNotIn('wlan0', self.redact(address + '\n'))
        # Exercise every possible zero-compression run and both expanded/canonical forms.
        for first in range(8):
            for count in range(1, 9 - first):
                groups = [format(i + 1, 'x') for i in range(8)]
                groups[first:first + count] = ['0'] * count
                address = ipaddress.IPv6Address(':'.join(groups))
                for spelling in (str(address), address.exploded):
                    with self.subTest(spelling=spelling):
                        self.assertEqual(self.redact(spelling + '\n'), '[redacted-ipv6]\n')

    def test_multiple_adjacent_addresses(self):
        self.assertEqual(self.redact('fe80::1 fe80::2 203.0.113.1 203.0.113.2\n'),
                         '[redacted-ipv6] [redacted-ipv6] [redacted-ipv4] [redacted-ipv4]\n')

    def test_formatted_phones(self):
        for phone in ('0912-345-678', '0912 345 678', '0912.345.678',
                      '+886 912 345 678', '+886 (0)912-345-678', '886-912-345-678',
                      '(02) 2345-6789', '02-2345-6789', '+1 (202) 555-0123',
                      '0044 20 7946 0123', 'sip:+886 912 345 678@ims.example.org',
                      'caller:0912-345-678', '0912345678', 'tel:0912 345 678', '0912-345-678 0912-345-679'):
            with self.subTest(phone=phone):
                out = self.redact('dial ' + phone + '; cause=503 exp_result_code=5065\n')
                self.assertNotRegex(out, r'\d[ .()-]*\d[ .()-]*\d[ .()-]*\d[ .()-]*\d')
                self.assertIn('cause=503 exp_result_code=5065', out)

    def test_structured_values_and_aliases(self):
        for field in ('mImsi', 'mIccId', 'icc_id', 'mSubscriberId', 'IMEI0', 'IMEISV',
                      'line1Number', 'phone_number', 'simSerialNumber', 'mImpi', 'mImpu',
                      'private_identity', 'public_identity', 'impu_list', 'serialno'):
            for value in ('"fixture secret"', "'fixture secret'", '["fixture secret", "other"]'):
                with self.subTest(field=field, value=value):
                    out = self.redact(f'{{"{field}": {value}, "cause":503}}\n')
                    self.assertNotIn('fixture', out)
                    self.assertNotIn('other', out)
                    self.assertIn('"cause":503', out)
        self.assertNotIn('0123456789', self.redact('IMSI=466 92 0123456789; cause=503\n'))
        self.assertNotIn('fixture-user@ims', self.redact('identity=fixture-user@ims\n'))
        self.assertNotIn('89888612345678901234', self.redact('card 89888612345678901234F\n'))
        self.assertNotIn('fixture-token', self.redact('Authorization: Bearer fixture-token\n'))

    def test_review_regressions_preserve_diagnostic_suffix(self):
        prefix = '10-18 12:34:56.123456789 I '
        suffix = ' cause=503 exp_result_code=5065 callId=487 RAT=18 W2L L2W marker=SNAPSHOT_lte_20261018_123456'
        for line in REVIEW_LINES:
            with self.subTest(line=line):
                out = self.redact(prefix + line + suffix + '\n')
                for secret in REVIEW_SECRETS:
                    self.assertNotIn(secret, out)
                self.assertTrue(out.startswith(prefix))
                self.assertTrue(out.endswith(suffix + '\n'), out)
                self.assertNotIn('\x1e', out)

    def test_phone_and_wifi_field_variants(self):
        for field in ('origNumber', 'orig_number', 'mOrigNumber', 'originalNumber', 'originNumber',
                      'originating_number', 'callingNumber', 'called_number',
                      'dialedNumber', 'dialled_number', 'remoteNumber', 'peer_number',
                      'fromNumber', 'to_number'):
            for separator in (':', '=', ' : ', ' = '):
                with self.subTest(field=field, separator=separator):
                    out = self.redact(f'M11W2L {field}{separator}0912-345-678 RAT=18\n')
                    self.assertNotIn('0912', out)
                    self.assertNotIn('345-678', out)
                    self.assertIn('RAT=18', out)
        for field in ('WIFI_SSID', 'wifiSsid', 'mWifiSsid', 'WLAN_SSID', 'SSID'):
            for value in ('SecretHome', 'Secret Home', '"Secret Home"', "'Secret Home'",
                          '["Secret Home", "Other Home"]'):
                with self.subTest(field=field, value=value):
                    out = self.redact(f'M11W2L {field}: {value} callId=487 RAT=18 W2L cause=503\n')
                    self.assertNotIn('Secret', out)
                    self.assertNotIn('Home', out)
                    self.assertNotIn('Other', out)
                    self.assertTrue(out.endswith('callId=487 RAT=18 W2L cause=503\n'))

    def test_ipsec_key_aliases_and_xfrm_algorithm_forms(self):
        for field in ('ipsec_key', 'ipSecKey', 'mIpSecKey', 'ip_sec_key',
                      'ipsec_auth_key', 'ipsec_enc_key', 'ipsec_encryption_key',
                      'authKey', 'mAuthKey', 'mEncKey', 'enc_key', 'integrity_key', 'cipherKey',
                      'ike_key', 'esp_key', 'xfrm_key', 'SK_d', 'SK_ai', 'SK_er',
                      'pre_shared_key', 'PSK', 'wpa_psk', 'password'):
            for value in ('CAFEBABECAFEBABECAFEBABE', '"fixture key"',
                          '["fixture key", "other key"]'):
                with self.subTest(field=field, value=value):
                    out = self.redact(f'IpSec {field}: {value}; cause=503 RAT=18\n')
                    self.assertNotIn('CAFEBABE', out)
                    self.assertNotIn('fixture', out)
                    self.assertNotIn('other', out)
                    self.assertIn('cause=503 RAT=18', out)
        for form in ('auth-trunc hmac(sha256)', 'enc cbc(aes)', 'aead rfc4106(gcm(aes))'):
            out = self.redact(f'IpSec {form} 0xCAFEBABECAFEBABECAFEBABE 128 cause=503\n')
            self.assertNotIn('CAFEBABE', out)
            self.assertIn(form, out)
            self.assertIn('128 cause=503', out)

    def test_authorization_and_bearer_variants(self):
        for field in ('Authorization', 'authorization', 'Proxy-Authorization',
                      'proxy_authorization', 'authToken', 'access_token', 'refreshToken',
                      'bearer_token', 'Bearer'):
            for value in ('Bearer fixture-token', 'bEaReR eyJ.fixture.signature==',
                          'Basic Zml4dHVyZTpwYXNz', '"Bearer fixture-token"',
                          '"fixture-token"'):
                for separator in (':', '=', ' = '):
                    with self.subTest(field=field, value=value, separator=separator):
                        out = self.redact(f'Epdg {field}{separator}{value} callId=487 RAT=18 cause=503 exp_result_code=5065\n')
                        self.assertNotIn('fixture-token', out)
                        self.assertNotIn('eyJ.fixture.signature', out)
                        self.assertNotIn('Zml4dHVyZTpwYXNz', out)
                        self.assertTrue(out.endswith('callId=487 RAT=18 cause=503 exp_result_code=5065\n'), out)
        out = self.redact('Epdg Bearer fixture-token, Basic Zml4dHVyZTpwYXNz; cause=503\n')
        self.assertNotIn('fixture-token', out)
        self.assertNotIn('Zml4dHVyZTpwYXNz', out)
        self.assertIn('cause=503', out)

    def test_credential_values_cannot_impersonate_diagnostics(self):
        for token in ('503', '5065', '12:34:56.123456789'):
            for scheme in ('Bearer', 'Basic'):
                out = self.redact(f'Epdg Authorization={scheme} {token}; cause=503 RAT=18\n')
                self.assertNotIn(scheme + ' ' + token, out)
                self.assertNotIn(token, out.split(';')[0])
                self.assertIn('cause=503 RAT=18', out)
        for value in ('503', '5065', 'W2L', 'L2W', '12:34:56.123456789'):
            out = self.redact(f'WIFI_SSID: {value}; cause=503 RAT=18\n')
            self.assertNotIn(value, out.split(';')[0])
            self.assertIn('cause=503 RAT=18', out)
        out = self.redact('IMSI=466 503 5065 123456; cause=503 RAT=18\n')
        self.assertNotIn('123456', out)
        self.assertNotIn('5065', out)
        self.assertIn('cause=503 RAT=18', out)
        for separator in (': ', '='):
            header = ('Epdg Authorization' + separator +
                      'Digest username="fixture-user", nonce="fixture-nonce", response="CAFEBABECAFEBABE"\n')
            out = self.redact(header)
            for secret in ('fixture-user', 'fixture-nonce', 'CAFEBABE'):
                self.assertNotIn(secret, out)
        suffix = ' Call ID:487 RAT:18 CODEX_IMS_CYCLE HANDOVER_COMPLETE'
        out = self.redact('12:34:56.789 WIFI_SSID: Secret Home' + suffix + '\n')
        self.assertNotIn('Secret', out)
        self.assertNotIn('Home', out)
        self.assertTrue(out.endswith(suffix + '\n'), out)

    def test_redaction_is_idempotent(self):
        data = PRIVATE_BYTES.decode()
        once = self.redact(data)
        self.assertEqual(self.redact(once), once)

    def test_archive_contents_and_private_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            share, private = root / 'SHARE_THIS', root / '_PRIVATE_DO_NOT_SHARE'
            share.mkdir(); private.mkdir()
            (share / 'summary.txt').write_bytes(PRIVATE_BYTES)
            (share / '.hidden.txt').write_bytes(PRIVATE_BYTES)
            (private / 'raw.txt').write_bytes(PRIVATE_BYTES + b'\x00\xff')
            p = self.package(root)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual((private / 'raw.txt').read_bytes(), PRIVATE_BYTES + b'\x00\xff')
            with tarfile.open(root / 'PRIVATE_FULL_CAPTURE.tar.gz') as archive:
                self.assertEqual(archive.extractfile('./raw.txt').read(), PRIVATE_BYTES + b'\x00\xff')
            with tarfile.open(root / 'SHARE_THIS.tar.gz') as archive:
                names = [m.name for m in archive if m.isfile()]
                self.assertEqual(set(names), {'./summary.txt', './.hidden.txt'})
                for name in names:
                    content = archive.extractfile(name).read().decode()
                    self.assertEqual(content, self.redact(PRIVATE_BYTES.decode()))
                    self.assertIn(DIAGNOSTIC, content)
            self.assertFalse((root / '.SHARE_THIS.tar.gz.tmp').exists())

    def package(self, root, setup=''):
        command = ('set -eu\numask 077\n' + REDACTOR + function('sanitize_share_files') +
                   function('write_capture_archives') +
                   'CAPTURE_ROOT="$1"\nSHARE_ROOT="$1/SHARE_THIS"\n'
                   'PRIVATE_ROOT="$1/_PRIVATE_DO_NOT_SHARE"\n' + setup + '\nwrite_capture_archives\n')
        return subprocess.run(['bash', '-c', command, 'privacy-test', str(root)],
                              capture_output=True, text=True, timeout=15)

    def test_failed_sanitization_never_publishes_and_keeps_private(self):
        for bad in ('symlink', 'directory', 'binary', 'filename', 'sed_failure'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                share, private = root / 'SHARE_THIS', root / '_PRIVATE_DO_NOT_SHARE'
                share.mkdir(); private.mkdir()
                (private / 'raw.txt').write_bytes(PRIVATE_BYTES)
                (share / 'summary.txt').write_bytes(PRIVATE_BYTES)
                setup = ''
                if bad == 'symlink':
                    (share / 'bad.txt').symlink_to(private / 'raw.txt')
                elif bad == 'directory':
                    (share / 'bad').mkdir()
                elif bad == 'binary':
                    (share / 'bad.txt').write_bytes(b'fixture\x00binary')
                elif bad == 'filename':
                    (share / '0912-345-678_summary.txt').write_text('fixture')
                else:
                    setup = 'redact_stream() { return 42; }'
                p = self.package(root, setup)
                self.assertNotEqual(p.returncode, 0)
                self.assertFalse((root / 'SHARE_THIS.tar.gz').exists())
                with tarfile.open(root / 'PRIVATE_FULL_CAPTURE.tar.gz') as archive:
                    self.assertEqual(archive.extractfile('./raw.txt').read(), PRIVATE_BYTES)

    def test_failed_share_tar_never_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'SHARE_THIS').mkdir(); (root / '_PRIVATE_DO_NOT_SHARE').mkdir()
            (root / 'SHARE_THIS/summary.txt').write_bytes(PRIVATE_BYTES)
            (root / '_PRIVATE_DO_NOT_SHARE/raw.txt').write_bytes(PRIVATE_BYTES)
            p = self.package(root, r'''tar() {
    case "$2" in
        */.SHARE_THIS.tar.gz.tmp) printf partial >"$2"; return 42 ;;
        *) command tar "$@" ;;
    esac
}''')
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((root / 'SHARE_THIS.tar.gz').exists())
            self.assertFalse((root / '.SHARE_THIS.tar.gz.tmp').exists())
            self.assertTrue((root / 'PRIVATE_FULL_CAPTURE.tar.gz').exists())

    def test_private_tar_failure_does_not_touch_share(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'SHARE_THIS').mkdir(); (root / '_PRIVATE_DO_NOT_SHARE').mkdir()
            share_file = root / 'SHARE_THIS/summary.txt'
            share_file.write_bytes(PRIVATE_BYTES)
            (root / '_PRIVATE_DO_NOT_SHARE/raw.txt').write_bytes(PRIVATE_BYTES)
            p = self.package(root, 'tar() { return 42; }')
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((root / 'SHARE_THIS.tar.gz').exists())
            self.assertEqual(share_file.read_bytes(), PRIVATE_BYTES)

    def test_failed_staging_move_never_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'SHARE_THIS').mkdir(); (root / '_PRIVATE_DO_NOT_SHARE').mkdir()
            (root / 'SHARE_THIS/summary.txt').write_bytes(PRIVATE_BYTES)
            (root / '_PRIVATE_DO_NOT_SHARE/raw.txt').write_bytes(PRIVATE_BYTES)
            p = self.package(root, 'mv() { return 42; }')
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((root / 'SHARE_THIS.tar.gz').exists())
            with tarfile.open(root / 'PRIVATE_FULL_CAPTURE.tar.gz') as archive:
                self.assertEqual(archive.extractfile('./raw.txt').read(), PRIVATE_BYTES)

    def test_capture_directory_collision_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            existing = root / 'ims_wifi_cycle_20261018_123456'
            existing.mkdir()
            sentinel = existing / 'SHARE_THIS.tar.gz'
            sentinel.write_bytes(b'existing synthetic archive')
            prefix = SOURCE[:SOURCE.index('\ncleanup()')]
            p = subprocess.run(['bash', '-c',
                                'date() { printf 20261018_123456; }\n' + prefix,
                                'privacy-test', str(root)], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(sentinel.read_bytes(), b'existing synthetic archive')
            self.assertFalse((existing / '_PRIVATE_DO_NOT_SHARE').exists())

    def test_call_observations_keep_raw_private_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / 'USER_OBSERVATIONS.tsv'
            share = root / 'shared.tsv'
            command = ('set -eu\n' + REDACTOR + function('record_call_result') +
                       'PRIVATE_ROOT="$1"\nOBSERVATIONS="$2"\nrecord_call_result w2l\n')
            p = subprocess.run(['bash', '-c', command, 'privacy-test', str(root), str(share)],
                               input='failed\nVoLTE\nfixture 0912 345 678 fe80::1 cause=503\n',
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('0912 345 678 fe80::1', raw.read_text())
            self.assertEqual(share.read_text(), self.redact(raw.read_text()))
            self.assertIn('w2l\tfailed\tVoLTE', share.read_text())
            self.assertIn('cause=503', share.read_text())

    def test_full_capture_with_fake_android(self):
        # The real script runs with fake su/getprop/sleep. No Android commands execute.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binpath = root / 'bin'; binpath.mkdir()
            mock = r'''#!/usr/bin/env python3
import os, re, sys
from pathlib import Path
cmd = sys.argv[2] if len(sys.argv) > 2 else ''
state = Path(os.environ['MOCK_STATE'])
fixture = Path(os.environ['MOCK_FIXTURE']).read_text()
if cmd == 'id':
    print('uid=0(root) gid=0(root)')
elif cmd.startswith('logcat '):
    raw = re.search(r">'([^']+)'", cmd).group(1)
    err = re.search(r"2>'([^']+)'", cmd).group(1)
    Path(raw).write_text(fixture)
    Path(err).write_text(fixture)
    state.write_text(raw)
    print('12345')
elif cmd.startswith('log -t '):
    with Path(state.read_text()).open('a') as f:
        f.write('10-18 12:34:56.789 I CODEX_IMS_CYCLE: ' + cmd.split("'")[1] + '\n')
elif cmd.startswith('kill ') or cmd.startswith('/system/bin/pm ') or cmd.startswith('getprop '):
    pass
elif cmd == 'ip -br addr':
    print('epdg_data0 UP 203.0.113.21/32 fe80::1/64')
elif cmd.startswith('sha256sum '):
    print('abc123456789def01' * 4 + '  fixture')
else:
    print(fixture, end='')
'''
            for name, content in {'su': mock, 'sleep': '#!/bin/sh\nexit 0\n',
                                  'getprop': '#!/bin/sh\ncat "$MOCK_FIXTURE"\n',
                                  'termux-wake-lock': '#!/bin/sh\nexit 0\n',
                                  'termux-wake-unlock': '#!/bin/sh\nexit 0\n'}.items():
                path = binpath / name; path.write_text(content); path.chmod(0o700)
            fixture = root / 'fixture.txt'; fixture.write_bytes(PRIVATE_BYTES)
            env = dict(os.environ, PATH=str(binpath) + os.pathsep + os.environ['PATH'],
                       IMS_CAPTURE_MODE='handover', MOCK_STATE=str(root / 'state'),
                       MOCK_FIXTURE=str(fixture))
            outroot = root / 'captures'
            p = subprocess.run(['bash', str(SCRIPT), str(outroot)],
                               input='baseline\n' + ' | '.join(REVIEW_LINES) + '\nsecond\nfixture note\nstop\n',
                               capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)
            captures = list(outroot.glob('ims_wifi_cycle_*'))
            self.assertEqual(len(captures), 1)
            capture = captures[0]
            with tarfile.open(capture / 'PRIVATE_FULL_CAPTURE.tar.gz') as private:
                self.assertTrue(private.extractfile('./logcat_all_private.txt').read().startswith(PRIVATE_BYTES))
                raw_notes = private.extractfile('./USER_OBSERVATIONS.tsv').read().decode()
                for line in REVIEW_LINES:
                    self.assertIn(line, raw_notes)
                self.assertIn(PRIVATE_BYTES, private.extractfile('./baseline/secims.txt').read())
            with tarfile.open(capture / 'SHARE_THIS.tar.gz') as share:
                files = {m.name: share.extractfile(m).read().decode() for m in share if m.isfile()}
                self.assertEqual(set(files), {'./USER_OBSERVATIONS.tsv', './runtime_identity.txt',
                                             './baseline_summary.txt', './second_summary.txt',
                                             './capture_health.txt', './logcat_stderr_redacted.txt',
                                             './key_timeline_redacted.txt'})
                for name, text in files.items():
                    with self.subTest(share_file=name):
                        for secret in REVIEW_SECRETS:
                            self.assertNotIn(secret, text)
                        self.assertNotIn('\x1e', text)
                for name in ('./key_timeline_redacted.txt', './baseline_summary.txt',
                             './runtime_identity.txt', './logcat_stderr_redacted.txt'):
                    # Prove the fixture passed through this path, not just that a
                    # filter discarded the entire source line.
                    self.assertIn('origNumber', files[name])
                    self.assertIn('WIFI_SSID', files[name])
                    self.assertIn('ipsec_key', files[name])
                    self.assertIn('Authorization', files[name])
                all_text = '\n'.join(files.values())
                self.assertNotIn('0912-345-678', all_text)
                self.assertNotIn('fe80::1', all_text)
                self.assertNotIn('466920123456789', all_text)
                self.assertIn('12:34:56.789', all_text)
                self.assertIn('exp_result_code=5065', all_text)
                self.assertIn('cause=503', all_text)
                self.assertNotIn('address_fingerprint_salt', all_text)
                hashes = []
                for phase in ('baseline', 'second'):
                    summary = share.extractfile(f'./{phase}_summary.txt').read().decode()
                    match = re.search(r'capture_salted_line_sha256=([0-9a-f]{64})', summary)
                    self.assertIsNotNone(match)
                    hashes.append(match.group(1))
                self.assertEqual(hashes[0], hashes[1])
                unsalted = hashlib.sha256(b'epdg_data0 UP 203.0.113.21/32 fe80::1/64').hexdigest()
                self.assertNotEqual(hashes[0], unsalted)
                salt = (capture / '_PRIVATE_DO_NOT_SHARE/address_fingerprint_salt.txt').read_text().strip()
                self.assertRegex(salt, r'^[0-9a-f]{64}$')
                self.assertNotIn(salt, all_text)


if __name__ == '__main__':
    unittest.main()
