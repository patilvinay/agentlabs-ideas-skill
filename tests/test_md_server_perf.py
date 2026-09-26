"""md-server must not re-walk a session tree for every polling tab."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load():
    os.environ.setdefault("MD_VENV", str(Path.home() / ".venvs/agentlabs-md"))
    loader = importlib.machinery.SourceFileLoader("md_server", str(ROOT / "bin/md-server"))
    spec = importlib.util.spec_from_loader("md_server", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class TreeCacheTests(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "a.md").write_text("x")
        self.walks = 0
        real = self.m.tree_revision

        def counting(root):
            self.walks += 1
            return real(root)
        self.m.tree_revision = counting

    def test_many_tabs_share_one_walk(self):
        threads = [threading.Thread(target=self.m.tree_revision_cached, args=(self.root,))
                   for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(self.walks, 1)

    def test_walks_again_after_the_ttl(self):
        self.m.TREE_TTL = 0
        first = self.m.tree_revision_cached(self.root)
        (self.root / "b.md").write_text("y")
        self.assertNotEqual(self.m.tree_revision_cached(self.root), first)
        self.assertEqual(self.walks, 2)

    def test_hidden_tabs_do_not_poll(self):
        page = self.m.page("t", "", "", "/x", "/x").decode()
        self.assertIn("if(document.hidden)return;", page)


if __name__ == "__main__":
    unittest.main()
