from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from kanban_server import project, server
from kanban_server.store import KanbanStore


class QuietKanbanHandler(server.KanbanHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


class ProjectCliCase(unittest.TestCase):
    def make_db_path(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return Path(self.tmp.name) / "kanban.sqlite3"

    def make_git_repo(self, name: str = "repo") -> Path:
        repo = Path(self.tmp.name) / name
        repo.mkdir()
        subprocess.run(
            ["git", "init", str(repo)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return repo

    def make_codex_stub(self, exit_code: int = 0) -> Path:
        script = Path(self.tmp.name) / f"codex-stub-{exit_code}"
        script.write_text(
            "#!/usr/bin/env sh\n" f"exit {exit_code}\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def start_server(self, store: KanbanStore) -> server.KanbanHTTPServer:
        httpd = server.KanbanHTTPServer(
            ("127.0.0.1", 0),
            QuietKanbanHandler,
            store=store,
            static_dir=server.STATIC_DIR,
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd

    def capture_project_main(self, args: list[str]) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            project.main(args)
        return output.getvalue()
