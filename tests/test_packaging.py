from __future__ import annotations

import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackagingTest(unittest.TestCase):
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

    def test_packaged_agent_profiles_inherit_the_session_model(self) -> None:
        profiles = sorted((ROOT / ".codex" / "agents").glob("*.toml"))

        self.assertTrue(profiles)
        for profile in profiles:
            with self.subTest(profile=profile.name):
                data = tomllib.loads(profile.read_text(encoding="utf-8"))
                self.assertNotIn("model", data)

        skill = (ROOT / ".codex" / "skills" / "codex-kanban" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        compact_skill = " ".join(skill.split())
        self.assertIn("inherit the current model", compact_skill)
        self.assertIn("supported lighter model", compact_skill)
        self.assertIn("actual runtime model", compact_skill)

    def test_skill_requires_exact_custom_agent_selection(self) -> None:
        skill = (ROOT / ".codex" / "skills" / "codex-kanban" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        compact_skill = " ".join(skill.split())
        plain_skill = compact_skill.replace("`", "")

        self.assertIn("exact Codex custom-agent type", plain_skill)
        self.assertIn("task_name does not select that agent", plain_skill)
        self.assertIn("never present a default agent as a named specialist", plain_skill)
        self.assertIn("cannot select the exact custom-agent type", plain_skill)

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
            "kanban_server/static/styles.css",
        ]:
            self.assertIn(asset, names)


if __name__ == "__main__":
    unittest.main()
