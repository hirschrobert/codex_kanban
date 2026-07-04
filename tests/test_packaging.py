from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackagingTest(unittest.TestCase):
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
