"""md-server serving session HTML mockups: runs them, and keeps them contained."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SID = "mock-session"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        home = Path(cls.tmp.name)
        scratch = home / ".claude/scratch"
        cls.session = scratch / SID
        mock = cls.session / "00-scratch/92-mockups"
        (mock / "img").mkdir(parents=True)
        (mock / "index.html").write_text('<link rel="stylesheet" href="style.css"><a href="next.html">next</a>')
        (mock / "next.html").write_text("<h1>next</h1>")
        (mock / "style.css").write_text("body{color:red}")
        (mock / "app.js").write_text("console.log(1)")
        (mock / "img/logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        (cls.session / ".secret").write_text("hidden")
        (cls.session / "00-scratch/notes.md").write_text("# Notes")
        # Outside every session: must never be reachable.
        (home / "private.txt").write_text("private")
        (mock / "escape.html").symlink_to(home / "private.txt")
        (scratch / "other").mkdir()
        (scratch / "other/page.html").write_text("<p>other session</p>")

        cls.port = free_port()
        env = {**os.environ, "HOME": str(home),
               "MD_VENV": os.environ.get("MD_VENV", str(Path.home() / ".venvs/agentlabs-md"))}
        env.pop("AGENTLABS_SESSIONS", None)
        cls.server = subprocess.Popen([str(ROOT / "bin/md-server"), "--port", str(cls.port)],
                                      env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        cls.mock = mock

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait()
        cls.server.stderr.close()
        cls.tmp.cleanup()

    def get(self, path, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.headers, r.read().decode(errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode(errors="replace")

    def site(self, rel):
        return self.get(f"/s/{SID}/site/00-scratch/92-mockups/{rel}")

    def test_html_is_served_as_a_sandboxed_page(self):
        code, headers, body = self.site("index.html")
        self.assertEqual(code, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", headers["Content-Security-Policy"])
        self.assertIn('href="next.html"', body)

    def test_relative_assets_have_their_types(self):
        for rel, ctype in (("style.css", "text/css"), ("app.js", "text/javascript"),
                           ("img/logo.svg", "image/svg+xml"), ("next.html", "text/html")):
            code, headers, _ = self.site(rel)
            self.assertEqual(code, 200, rel)
            self.assertTrue(headers["Content-Type"].startswith(ctype), rel)

    def test_traversal_is_refused(self):
        for rel in ("../../../private.txt", "..%2F..%2F..%2Fprivate.txt",
                    "%2e%2e/%2e%2e/%2e%2e/private.txt", "../../../other/page.html"):
            self.assertEqual(self.site(rel)[0], 404, rel)

    def test_symlink_out_of_the_session_is_refused(self):
        self.assertEqual(self.site("escape.html")[0], 404)

    def test_no_directory_listing_or_hidden_files(self):
        self.assertEqual(self.site("")[0], 404)
        self.assertEqual(self.site("img")[0], 404)
        self.assertEqual(self.get(f"/s/{SID}/site/.secret")[0], 404)

    def test_view_frames_the_page_and_keeps_source(self):
        p = self.mock / "index.html"
        code, _, body = self.get(f"/s/{SID}/view?p={p}")
        self.assertEqual(code, 200)
        self.assertIn(f'<iframe src="/s/{SID}/site/00-scratch/92-mockups/index.html"', body)
        self.assertIn('sandbox="allow-scripts', body)
        code, _, body = self.get(f"/s/{SID}/view?p={p}&view=source")
        self.assertEqual(code, 200)
        self.assertNotIn("<iframe", body)
        self.assertIn("next.html", body)

    def test_mockup_view_is_full_width_with_controls(self):
        code, _, body = self.get(f"/s/{SID}/view?p={self.mock / 'index.html'}")
        self.assertEqual(code, 200)
        self.assertIn("<main class=wide>", body)
        for control in ('data-w="fit"', 'data-w="1440"', 'data-w="1920"', "id=sb", "New tab", "Source"):
            self.assertIn(control, body)

    def test_markdown_keeps_its_reading_width(self):
        code, _, body = self.get(f"/s/{SID}/view?p={self.session / '00-scratch/notes.md'}")
        self.assertEqual(code, 200)
        self.assertIn("<main>", body)
        self.assertNotIn("class=wide", body)

    def test_every_html_file_is_in_the_sidebar(self):
        _, _, body = self.get(f"/s/{SID}")
        for name in ("index.html", "next.html"):
            self.assertIn(f">{name}<", body)

    def test_sandboxed_page_cannot_use_the_api_or_raw(self):
        f = self.mock / "style.css"
        for headers in ({"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.get(f"/api/focus?sid=x", headers)[0], 403)
            self.assertEqual(self.get(f"/raw?p={f}", headers)[0], 403)
        # The md-server page itself (same-origin) still can.
        self.assertEqual(self.get(f"/raw?p={f}", {"Sec-Fetch-Site": "same-origin"})[0], 200)


if __name__ == "__main__":
    unittest.main()
