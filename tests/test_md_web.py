"""md-web raises only this session's md-server window, and only on this workspace."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = """\
0x01  7 host hrms-dev · md-server - Google Chrome
0x02  2 host 50-hrms-features.md · hrms-dev · md-server - Google Chrome
0x03  2 host auth · md-server - Google Chrome
0x04  2 host YouTube - Google Chrome
0x05 -1 host notes.md · pinned · md-server - Google Chrome
"""


class HereWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bindir = Path(self.tmp.name)
        wmctrl = bindir / "wmctrl"
        wmctrl.write_text('#!/bin/sh\ncase "$1" in\n'
                          '  -d) printf "0  - DG\\n2  * DG\\n7  - DG\\n";;\n'
                          f'  -l) cat <<\'W\'\n{WINDOWS}W\n;;\nesac\n')
        wmctrl.chmod(0o755)
        self.path = f"{bindir}:/usr/bin:/bin"
        src = (ROOT / "bin/md-web").read_text()
        self.fn = re.search(r"^here_window\(\) \{.*?^\}", src, re.S | re.M).group(0)

    def here(self, title):
        r = subprocess.run(["bash", "-c", self.fn + '\nhere_window "$1"', "t", title],
                           env={"PATH": self.path}, text=True, capture_output=True)
        return r.stdout.strip() if r.returncode == 0 else None

    def test_own_file_page_on_this_workspace(self):
        self.assertEqual(self.here("hrms-dev"), "0x02")  # not 0x01, on workspace 7

    def test_own_overview_page(self):
        self.assertEqual(self.here("auth"), "0x03")

    def test_another_sessions_window_is_never_raised(self):
        self.assertIsNone(self.here("workspace-b0"))

    def test_prefix_of_a_title_does_not_match(self):
        self.assertIsNone(self.here("hrms"))

    def test_window_on_all_workspaces_counts(self):
        self.assertEqual(self.here("pinned"), "0x05")


if __name__ == "__main__":
    unittest.main()
