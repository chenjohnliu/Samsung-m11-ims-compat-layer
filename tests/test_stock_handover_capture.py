"""Host-only checks for safe helpers in the stock handover collector.

These tests never invoke the capture lifecycle or touch the Android BASE path.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "diagnostics" / "capture_ims_stock_handover_termux.sh"


@unittest.skipUnless(shutil.which("/bin/sh"), "POSIX /bin/sh is required")
class StockHandoverCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.syntax = subprocess.run(
            ["/bin/sh", "-n", str(SCRIPT)], capture_output=True, text=True
        )
        if cls.syntax.returncode:
            raise AssertionError(cls.syntax.stderr or cls.syntax.stdout)

    def run_helpers(self, body, *args):
        shell = (
            'script_path=$1; a1=${2-}; a2=${3-}; a3=${4-}; a4=${5-}; '
            'cat() { /bin/cat "$@"; }; '
            'set -- help; . "$script_path" >/dev/null; PATH=/usr/bin:/bin; unset -f cat; '
            'set -- "$a1" "$a2" "$a3" "$a4"; ' + body
        )
        return subprocess.run(
            ["/bin/sh", "-c", shell, "sh", str(SCRIPT), *map(str, args)],
            capture_output=True,
            text=True,
        )

    def test_shell_syntax(self):
        self.assertEqual(self.syntax.returncode, 0)

    def test_token_and_label_validation(self):
        result = self.run_helpers(
            'valid_token "$1" && valid_label "$2"', "wifi_off-01", "stock_hotspot_2"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        for value in ("bad;id", "x y", "$(id)", "x" * 49):
            with self.subTest(kind="token", value=value):
                result = self.run_helpers('valid_token "$1"', value)
                self.assertNotEqual(result.returncode, 0)

        for value in ("bad;label", "x y", "$(id)", "x" * 41):
            with self.subTest(kind="label", value=value):
                result = self.run_helpers('valid_label "$1"', value)
                self.assertNotEqual(result.returncode, 0)

    def test_proc_identity_helper_uses_live_proc_starttime(self):
        result = self.run_helpers(
            'tick=$(proc_starttime "$$") || exit 1; '
            '[ -n "$tick" ] || exit 2; '
            'proc_starttime 999999999 >/dev/null 2>&1 && exit 3; '
            'proc_starttime 0 >/dev/null 2>&1 && exit 4; exit 0'
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_session_path_rejects_traversal_symlink_and_non_root_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "private"
            session = base / "session_20261010_120000_test"
            session.mkdir(parents=True)
            session.chmod(0o700)
            link = base / "session_20261010_120001_link"
            link.symlink_to(session, target_is_directory=True)

            # Mock stat only for this helper test so it is portable on non-root hosts.
            body = (
                'BASE=${1%/*}; '
                'stat() { case "$*" in "-c %u "*) printf "0\\n" ;; '
                '"-c %a "*) printf "700\\n" ;; *) command stat "$@" ;; esac; }; '
                'safe_session "$1" || exit 1; '
                'safe_session "$2" && exit 2; '
                'safe_session "$3" && exit 3; '
                'safe_session "$4" && exit 4; '
                'stat() { case "$*" in "-c %u "*) printf "1000\\n" ;; '
                '"-c %a "*) printf "700\\n" ;; *) command stat "$@" ;; esac; }; '
                'safe_session "$1" && exit 5; exit 0'
            )
            result = self.run_helpers(
                body,
                str(session),
                str(link),
                str(base / "session_../outside"),
                str(base / "session_bad/name"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_leading_zero_duration_is_rejected_before_filesystem_setup(self):
        body = (
            'need_root() { :; }; root_setup() { printf "ROOT_SETUP_REACHED\\n"; exit 9; }; '
            'start_capture stock_test 0900'
        )
        result = self.run_helpers(body)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("decimal integer without leading zeroes", result.stderr)
        self.assertNotIn("ROOT_SETUP_REACHED", result.stdout)

    def test_collector_has_no_known_state_changing_commands(self):
        source = SCRIPT.read_text(encoding="utf-8")
        forbidden = re.compile(
            r"(?m)^\s*(?:setprop\s|settings\s+put\s|svc\s+(?:wifi|data|usb)\s|"
            r"ip\s+(?:route|rule)\s+(?:add|del|change)\s|tc\s+(?:qdisc|filter)\s+(?:add|del|change)\s)"
        )
        self.assertIsNone(forbidden.search(source))


if __name__ == "__main__":
    unittest.main()
