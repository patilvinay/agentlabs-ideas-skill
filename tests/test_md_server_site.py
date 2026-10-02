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
        (mock / "README.md").write_text("# Mockups")
        (mock / "style.css").write_text("body{color:red}")
        (mock / "app.js").write_text("console.log(1)")
        (mock / "img/logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        (cls.session / "00-scratch/clip.mp4").write_bytes(bytes(range(256)) * 4)
        (cls.session / ".secret").write_text("hidden")
        (cls.session / "00-scratch/notes.md").write_text("# Notes")
        (cls.session / "00-scratch/pay.csv").write_text(
            'code,name,acct,amount,note,missing\n'
            'E2,"Doe, Jane",000401234567,1200.50,"a\nb",\n'
            'E1,Ann,000401234568,99.00,=SUM(A1:A2),PAN\n'
            'TOTAL,,,1299.50,,\n')
        clone = cls.session / "code/some-repo"
        (clone / ".git").mkdir(parents=True)
        (clone / "src").mkdir()
        (clone / "src/main.go").write_text("package main")
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

    def sidebar_folder(self, body, folder):
        start = body.index(f'data-folder="{folder}"')
        return body[body.rindex("<details", 0, start):]

    def test_readme_and_index_first_then_files_then_folders(self):
        _, _, body = self.get(f"/s/{SID}")
        tree = self.sidebar_folder(body, "00-scratch/92-mockups")
        order = [tree.index(f">{n}<") for n in ("README.md", "index.html", "app.js", "next.html", "style.css")]
        self.assertEqual(order, sorted(order))
        self.assertLess(order[-1], tree.index('data-folder="00-scratch/92-mockups/img"'))

    def test_asset_only_folder_starts_collapsed(self):
        _, _, body = self.get(f"/s/{SID}")
        self.assertIn('<details data-folder="00-scratch/92-mockups/img">', body)
        self.assertIn('<details open data-folder="00-scratch/92-mockups">', body)

    def test_asset_folder_opens_when_it_holds_the_open_file(self):
        _, _, body = self.get(f"/s/{SID}/view?p={self.mock / 'img/logo.svg'}")
        self.assertIn('<details open data-folder="00-scratch/92-mockups/img">', body)

    def test_page_assets_beside_an_index_are_dimmed(self):
        _, _, body = self.get(f"/s/{SID}")
        self.assertRegex(body, r'<a class="asset" href="[^"]*app\.js">')
        self.assertRegex(body, r'<a class="asset" href="[^"]*style\.css">')
        self.assertRegex(body, r'<a class="" href="[^"]*next\.html">')

    def test_stage_folders_show_their_real_names(self):
        _, _, body = self.get(f"/s/{SID}")
        self.assertIn("<summary>00-scratch</summary>", body)
        for label in (">Draft<", ">Review<", ">Approved<"):
            self.assertNotIn(label, body)

    def test_code_clone_is_listed_but_not_expanded(self):
        _, _, body = self.get(f"/s/{SID}")
        self.assertIn('data-folder="code/some-repo"', body)
        self.assertNotIn("main.go", body)

    def test_scroll_is_restored_only_for_the_same_tree(self):
        _, _, body = self.get(f"/s/{SID}")
        self.assertIn("saved.shape === shape", body)

    def test_file_page_title_names_the_session(self):
        _, _, body = self.get(f"/s/{SID}/view?p={self.session / '00-scratch/notes.md'}")
        self.assertIn("<title>notes.md · mock-ses · md-server</title>", body)

    def test_pages_do_not_follow_other_sessions(self):
        _, _, body = self.get(f"/s/{SID}")
        self.assertNotIn("location.href='/s/'+j.focus", body)

    def csv_page(self, extra=""):
        return self.get(f"/s/{SID}/view?p={self.session / '00-scratch/pay.csv'}{extra}")

    def test_csv_is_a_grid_with_exact_values(self):
        code, _, body = self.csv_page()
        self.assertEqual(code, 200)
        self.assertIn('<table class=grid>', body)
        self.assertIn('<td class="text">Doe, Jane</td>', body)          # quoted comma
        self.assertIn('<td class="id">000401234567</td>', body)         # zeros kept, text
        self.assertIn('<td class="num">1200.50</td>', body)             # right-aligned number
        self.assertIn('<td class="text">=SUM(A1:A2)</td>', body)        # formula is text
        self.assertIn('<td class="text miss">PAN</td>', body)           # missing highlighted
        self.assertIn('<td class="text e"></td>', body)                 # empty marked
        self.assertIn("2 rows · 6 columns", body)

    def test_csv_total_row_is_pinned_in_the_footer(self):
        _, _, body = self.csv_page()
        foot = body[body.index("<tfoot>"):body.index("</tfoot>")]
        self.assertIn("TOTAL", foot)
        self.assertNotIn("TOTAL", body[body.index("<tbody>"):body.index("</tbody>")])

    def test_csv_raw_view_and_download(self):
        _, _, body = self.csv_page("&src=1")
        self.assertNotIn("<table class=grid>", body)
        _, _, body = self.csv_page()
        self.assertIn('download="pay.csv"', body)

    def test_sandboxed_page_cannot_use_the_api_or_raw(self):
        f = self.mock / "style.css"
        for headers in ({"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.get(f"/api/focus?sid=x", headers)[0], 403)
            self.assertEqual(self.get(f"/raw?p={f}", headers)[0], 403)
        # The md-server page itself (same-origin) still can.
        self.assertEqual(self.get(f"/raw?p={f}", {"Sec-Fetch-Site": "same-origin"})[0], 200)


if __name__ == "__main__":
    unittest.main()

    def test_raw_honours_byte_ranges_so_media_can_seek(self):
        f = self.session / "00-scratch/clip.mp4"
        whole = f.read_bytes()
        code, headers, _ = self.get(f"/raw?p={f}")
        self.assertEqual((code, headers["Accept-Ranges"], headers["Content-Type"]), (200, "bytes", "video/mp4"))
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/raw?p={f}", headers={"Range": "bytes=100-199"})
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 206)
            self.assertEqual(r.headers["Content-Range"], f"bytes 100-199/{len(whole)}")
            self.assertEqual(r.read(), whole[100:200])
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/raw?p={f}", headers={"Range": "bytes=-24"})
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual((r.status, r.read()), (206, whole[-24:]))
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/raw?p={f}", headers={"Range": f"bytes={len(whole)}-"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(e.exception.code, 416)

