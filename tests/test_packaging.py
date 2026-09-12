from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class PackagingTest(unittest.TestCase):
    def test_skill_bundle_contains_every_local_markdown_target(self) -> None:
        skill_root = ROOT / ".codex" / "skills" / "codex-kanban"
        resolved_root = skill_root.resolve()
        link_pattern = re.compile(r"\[[^]]*\]\(([^)]+)\)")

        for document in sorted(skill_root.rglob("*.md")):
            for raw_target in link_pattern.findall(document.read_text(encoding="utf-8")):
                target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                path = Path(unquote(parsed.path))
                if path.is_absolute():
                    continue
                resolved = (document.parent / path).resolve()
                self.assertTrue(
                    resolved.is_relative_to(resolved_root),
                    f"Skill-local target escapes bundle: {document} -> {target}",
                )
                self.assertTrue(
                    resolved.exists(),
                    f"Missing skill-local target: {document} -> {target}",
                )

    def test_skill_bundle_contains_deployment_runbook_and_service_template(self) -> None:
        skill_root = ROOT / ".codex" / "skills" / "codex-kanban"

        self.assertTrue((skill_root / "docs" / "codex-kanban.md").is_file())
        self.assertTrue((skill_root / "docs" / "deployment.md").is_file())
        self.assertTrue((skill_root / "assets" / "codex-kanban.service").is_file())

    def test_release_instructions_require_exact_ai_disclosure_evidence(self) -> None:
        instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        skill = (ROOT / ".codex" / "skills" / "codex-kanban" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        for document in (instructions, skill):
            self.assertIn("exact", document)
            self.assertIn("versioned model slug", document)
            self.assertIn("short, unambiguous commit SHA", document)
            self.assertIn("gpt-5", document)

    def test_skill_keeps_profiles_optional_and_exact_when_selected(self) -> None:
        skill = (ROOT / ".codex" / "skills" / "codex-kanban" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        compact_skill = " ".join(skill.split())
        plain_skill = compact_skill.replace("`", "")

        self.assertIn("exact Codex custom-agent type", plain_skill)
        self.assertIn("task_name does not select that agent", plain_skill)
        self.assertIn("never present a default agent as a named specialist", plain_skill)
        self.assertIn("optional catalog", plain_skill)
        self.assertIn("does not force delegation", plain_skill)

    def test_skill_keeps_worktrees_on_origin_board_and_cleans_them(self) -> None:
        skill = (ROOT / ".codex" / "skills" / "codex-kanban" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        compact_skill = " ".join(skill.split()).replace("`", "")

        self.assertIn("worktrees belong to the project registered", compact_skill)
        self.assertIn("target_repo", compact_skill)
        self.assertIn("worktree_path", compact_skill)
        self.assertIn("worktree-cleanup", compact_skill)
        self.assertIn("refuses active cards", compact_skill)

    @unittest.skipUnless(shutil.which("uv"), "uv is required for package build checks")
    def test_wheel_includes_dashboard_static_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["uv", "build", "--wheel", "--out-dir", tmp],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            wheels = sorted(Path(tmp).glob("*.whl"))
            self.assertEqual(len(wheels), 1, [wheel.name for wheel in wheels])

            with zipfile.ZipFile(wheels[0]) as wheel:
                names = set(wheel.namelist())

        for asset in [
            "kanban_server/static/index.html",
            "kanban_server/static/app/main.js",
            "kanban_server/static/app/project-settings.js",
            "kanban_server/static/app/archive-old.js",
            "kanban_server/static/styles.css",
        ]:
            self.assertIn(asset, names)


if __name__ == "__main__":
    unittest.main()
