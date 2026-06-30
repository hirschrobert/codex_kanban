from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "kanban_server" / "static"


class StaticAssetTest(unittest.TestCase):
    def test_dashboard_scripts_load_in_dependency_order(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        scripts = [
            "/static/app_state.js",
            "/static/app_api.js",
            "/static/app_model.js",
            "/static/app.js",
        ]
        positions = [html.index(f'src="{script}"') for script in scripts]
        self.assertEqual(positions, sorted(positions))

    def test_card_notice_renderer_is_defined_with_card_renderer(self) -> None:
        app = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("function cardNoticeHtml(card)", app)
        self.assertIn("${cardNoticeHtml(card)}", app)

    def test_card_renderer_exposes_owner_and_assignee_labels(self) -> None:
        app = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        model = (STATIC_DIR / "app_model.js").read_text(encoding="utf-8")
        self.assertIn("function cardOwnerText(card)", model)
        self.assertIn("function cardCreatorText(card)", model)
        self.assertIn("function ensureSelectOption(select, value, label)", app)
        self.assertIn("ensureSelectOption(cardForm.elements.owner_id", app)
        self.assertIn("Owner: ${escapeHtml(cardOwnerText(card))}", app)
        self.assertIn("Created: ${escapeHtml(cardCreatorText(card))}", app)
        self.assertIn("Assigned: ${escapeHtml(assigneeChipText(card))}", app)

    def test_archive_action_continues_after_individual_failure(self) -> None:
        app = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("const failed = [];", app)
        self.assertIn("failed.push({ card, error });", app)
        self.assertIn('Could not ${archived ? "archive" : "unarchive"}', app)

    @unittest.skipUnless(shutil.which("node"), "node is required for JS runtime checks")
    def test_archive_only_edit_skips_coordination_confirmation(self) -> None:
        script = f"""
const fs = require("node:fs");
const vm = require("node:vm");
const staticDir = {json.dumps(str(STATIC_DIR))};

const storage = {{ getItem() {{ return ""; }}, setItem() {{}} }};
const context = vm.createContext({{
  Date,
  Intl,
  JSON,
  Set,
  localStorage: storage,
  window: {{}}
}});
context.window = context;

for (const file of ["app_state.js", "app_model.js"]) {{
  vm.runInContext(fs.readFileSync(`${{staticDir}}/${{file}}`, "utf8"), context, {{
    filename: file
  }});
}}

const current = {{
  id: 1,
  status: "in_progress",
  target_repo: "/tmp/demo",
  target_branch: "",
  feature_branch: "",
  worktree_path: "",
  files_changed: []
}};
const archived = Object.assign({{}}, current, {{ archived: true }});
const moved = Object.assign({{}}, current, {{ status: "review" }});

if (context.window.Kanban.coordinationConfirmationNeeded(current, archived)) {{
  throw new Error("archive-only edit asked for coordination confirmation");
}}
if (!context.window.Kanban.coordinationConfirmationNeeded(current, moved)) {{
  throw new Error("status move skipped coordination confirmation");
}}
"""
        result = subprocess.run(
            ["node"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    @unittest.skipUnless(shutil.which("node"), "node is required for JS runtime checks")
    def test_dashboard_scripts_evaluate_without_global_redeclarations(self) -> None:
        script = f"""
const fs = require("node:fs");
const vm = require("node:vm");
const staticDir = {json.dumps(str(STATIC_DIR))};

class Element {{
  constructor() {{
    this.children = [];
    this.className = "";
    this.dataset = {{}};
    this.style = {{}};
    this.classList = {{ add() {{}}, remove() {{}}, toggle() {{}} }};
    this.elements = new Proxy({{}}, {{
      get: () => ({{ value: "", checked: false, addEventListener() {{}}, focus() {{}} }})
    }});
  }}
  addEventListener() {{}}
  appendChild(child) {{ this.children.push(child); }}
  close() {{}}
  focus() {{}}
  querySelector() {{ return new Element(); }}
  querySelectorAll() {{ return []; }}
  removeAttribute() {{}}
  replaceChildren(...children) {{ this.children = children; }}
  reset() {{}}
  setAttribute() {{}}
  showModal() {{}}
}}

const storage = {{ getItem() {{ return ""; }}, setItem() {{}} }};
const document = {{
  createElement() {{ return new Element(); }},
  querySelector() {{ return new Element(); }}
}};
const context = vm.createContext({{
  EventSource: function EventSource() {{
    this.addEventListener = () => undefined;
    this.close = () => undefined;
  }},
  Date,
  Intl,
  JSON,
  Map,
  Promise,
  Set,
  URLSearchParams,
  clearTimeout,
  console,
  document,
  fetch: () => Promise.resolve({{
    ok: true,
    json: () => Promise.resolve({{
      board: {{ slug: "codex-kanban", title: "codex_kanban" }},
      cards: [],
      events: [],
      participants: [],
      projects: []
    }})
  }}),
  localStorage: storage,
  setInterval() {{}},
  setTimeout,
  window: {{}}
}});
context.window = context;

for (const file of ["app_state.js", "app_api.js", "app_model.js", "app.js"]) {{
  vm.runInContext(fs.readFileSync(`${{staticDir}}/${{file}}`, "utf8"), context, {{
    filename: file
  }});
}}
"""
        result = subprocess.run(
            ["node"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
