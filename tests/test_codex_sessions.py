import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


class CodexSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.run = self.home / "run"
        self.run.mkdir()
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "AGENTLABS_RUN": str(self.run),
            "MD_VENV": os.environ.get("MD_VENV", "/home/vinay/.venvs/agentlabs-md"),
            "TMUX_PANE": "",
        }

    def fake_tmux(self):
        bindir = self.home / "bin"
        bindir.mkdir(exist_ok=True)
        tmux = bindir / "tmux"
        tmux.write_text("#!/bin/sh\nexit 1\n")
        tmux.chmod(0o755)
        self.env["PATH"] = str(bindir) + ":" + self.env["PATH"]

    def test_codex_transcript_creates_codex_scratch_stages(self):
        # Catches session-dir defaulting every agent to ~/.claude/scratch.
        transcript = self.home / ".codex/sessions/2026/09/16/rollout.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({
            "type": "session_meta", "payload": {"id": "codex-session"}
        }) + "\n")
        (self.run / "pane-1.transcript").write_text(str(transcript))
        self.fake_tmux()

        result = subprocess.run(
            ["bash", str(ROOT / "bin/session-dir"), "%1"],
            env=self.env, text=True, capture_output=True,
        )

        expected = self.home / ".codex/scratch/codex-session"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), expected)
        self.assertTrue((expected / "00-scratch").is_dir())
        self.assertTrue((expected / "10-review").is_dir())
        self.assertTrue((expected / "20-approved").is_dir())

    def test_server_lists_codex_draft_with_codex_title(self):
        # Catches either root discovery or session-index title lookup regressing.
        sid = "01a0a62d-3d2f-7143-aa64-c5a03a870dd2"
        draft = self.home / ".codex/scratch" / sid / "00-scratch/proposal.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("# Runtime delivery proposal\n")
        index = self.home / ".codex/session_index.jsonl"
        index.write_text(json.dumps({"id": sid, "thread_name": "vinay-sima-codex"}) + "\n")

        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = subprocess.Popen(
            [str(ROOT / "bin/md-server"), "--port", str(port)],
            env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.addCleanup(server.wait)
        self.addCleanup(server.kill)
        url = f"http://127.0.0.1:{port}/s/{sid}"
        for _ in range(40):
            try:
                page = urllib.request.urlopen(url, timeout=0.2).read().decode()
                break
            except Exception:
                time.sleep(0.05)
        else:
            self.fail("md-server did not start")

        self.assertIn("vinay-sima-codex", page)
        self.assertIn("proposal.md", page)
        self.assertIn(str(self.home / ".codex/scratch" / sid), page)


if __name__ == "__main__":
    unittest.main()
