from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_codex_assets.py"
SOURCE_SKILL = ROOT / ".codex" / "skills" / "codex-kanban"
SOURCE_AGENTS = ROOT / ".codex" / "agents"


class CodexAssetInstallTest(unittest.TestCase):
    def run_installer(self, codex_home: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(INSTALLER), *arguments],
            cwd=ROOT,
            env={**os.environ, "CODEX_HOME": str(codex_home)},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_installer_replaces_skill_and_preserves_unrelated_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            installed_skill = codex_home / "skills" / "codex-kanban"
            installed_skill.mkdir(parents=True)
            (installed_skill / "stale.txt").write_text("stale", encoding="utf-8")

            installed_agents = codex_home / "agents"
            installed_agents.mkdir(parents=True)
            unrelated_agent = installed_agents / "personal-helper.toml"
            unrelated_agent.write_text('name = "personal-helper"\n', encoding="utf-8")
            managed_agent = installed_agents / "security-remediator.toml"
            managed_agent.write_text('name = "old-remediator"\n', encoding="utf-8")
            user_config = codex_home / "config.toml"
            original_config = 'model = "user-choice"\n[agents]\nmax_threads = 3\n'
            user_config.write_text(original_config, encoding="utf-8")

            result = self.run_installer(codex_home)

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertFalse((installed_skill / "stale.txt").exists())
            self.assertTrue((installed_skill / "docs" / "codex-kanban.md").is_file())
            self.assertTrue((installed_skill / "docs" / "deployment.md").is_file())
            self.assertTrue((installed_skill / "assets" / "codex-kanban.service").is_file())
            self.assertEqual(
                (installed_skill / "SKILL.md").read_bytes(),
                (SOURCE_SKILL / "SKILL.md").read_bytes(),
            )
            for source_agent in SOURCE_AGENTS.glob("*.toml"):
                self.assertEqual(
                    (installed_agents / source_agent.name).read_bytes(), source_agent.read_bytes()
                )
            self.assertEqual(
                unrelated_agent.read_text(encoding="utf-8"), 'name = "personal-helper"\n'
            )
            backups = list((codex_home / "backups").glob("codex-kanban-*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "skills" / "codex-kanban" / "stale.txt").is_file())
            self.assertEqual(
                (backups[0] / "agents" / "security-remediator.toml").read_text(encoding="utf-8"),
                'name = "old-remediator"\n',
            )
            self.assertEqual(user_config.read_text(encoding="utf-8"), original_config)

    def test_dry_run_validates_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"

            result = self.run_installer(codex_home, "--dry-run")

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertIn("Validated skill source", result.stdout)
            self.assertFalse(codex_home.exists())


if __name__ == "__main__":
    unittest.main()
