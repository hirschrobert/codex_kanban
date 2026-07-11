from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parents[1] / "kanban_server" / "static"


class StaticAssetTest(unittest.TestCase):
    def test_dashboard_scripts_load_in_dependency_order(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        scripts = [
            "/static/app/state.js",
            "/static/app/api.js",
            "/static/app/model.js",
            "/static/app/project-settings.js",
            "/static/app/main.js",
        ]
        positions = [html.index(f'src="{script}"') for script in scripts]
        self.assertEqual(positions, sorted(positions))

    def test_ci_javascript_checks_match_dashboard_scripts(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        script_paths = re.findall(r'<script src="(/static/[^"]+\.js)"></script>', html)
        expected_targets = [
            f"kanban_server/static/{script_path.removeprefix('/static/')}"
            for script_path in script_paths
        ]
        ci_targets = re.findall(r"node --check (kanban_server/static/\S+\.js)", ci)

        self.assertEqual(ci_targets, expected_targets)
        for legacy_name in [
            "app.js",
            "app_api.js",
            "app_model.js",
            "app_projects.js",
            "app_state.js",
        ]:
            self.assertFalse((STATIC_DIR / legacy_name).exists(), legacy_name)
            self.assertNotIn(f"kanban_server/static/{legacy_name}", ci)

    def test_card_notice_renderer_is_defined_with_card_renderer(self) -> None:
        app = (STATIC_DIR / "app" / "main.js").read_text(encoding="utf-8")
        self.assertIn("function cardNoticeHtml(card)", app)
        self.assertIn("${cardNoticeHtml(card)}", app)

    def test_card_renderer_exposes_owner_and_assignee_labels(self) -> None:
        app = (STATIC_DIR / "app" / "main.js").read_text(encoding="utf-8")
        model = (STATIC_DIR / "app" / "model.js").read_text(encoding="utf-8")
        self.assertIn("function cardOwnerText(card)", model)
        self.assertIn("function cardCreatorText(card)", model)
        self.assertIn("function intakeKindText(card)", model)
        self.assertIn("function intakeSourceText(card)", model)
        self.assertIn("function ensureSelectOption(select, value, label)", app)
        self.assertIn("ensureSelectOption(cardForm.elements.owner_id", app)
        self.assertIn("Owner: ${escapeHtml(cardOwnerText(card))}", app)
        self.assertIn("Created: ${escapeHtml(cardCreatorText(card))}", app)
        self.assertIn("Assigned: ${escapeHtml(assigneeChipText(card))}", app)
        self.assertIn('${intakeKind ? `<span class="chip">${escapeHtml(intakeKind)}</span>`', app)
        self.assertIn("Affected: ${affectedCount}", app)
        self.assertIn("Ecosystem: ${affectedProjectCount}", app)
        self.assertIn("function affectedProjectChipsHtml(card)", app)
        self.assertIn("affectedProjectPathText(item)", app)
        self.assertIn("Deploy: ${deploymentCount}", app)

    def test_people_renderer_groups_live_instances_under_agent_roles(self) -> None:
        app = (STATIC_DIR / "app" / "main.js").read_text(encoding="utf-8")
        model = (STATIC_DIR / "app" / "model.js").read_text(encoding="utf-8")
        state = (STATIC_DIR / "app" / "state.js").read_text(encoding="utf-8")
        sidebar = (STATIC_DIR / "sidebar.css").read_text(encoding="utf-8")

        self.assertIn("function agentInstanceSummary(instance)", model)
        self.assertIn("normalText(instance?.agent_type)", model)
        self.assertIn("Focused:", app)
        self.assertIn("participant.instances", app)
        self.assertIn('class="participant-instance"', app)
        self.assertIn("event.metadata?.model", app)
        self.assertIn("participant.active_models", app)
        self.assertIn("participant.active_cards", app)
        self.assertIn("Cards: ${escapeHtml(activeCardSummary)}", app)
        self.assertIn(".participant-instances", sidebar)
        self.assertNotIn("participantLimit", state)

    def test_card_form_exposes_optional_intake_fields(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        app = (STATIC_DIR / "app" / "main.js").read_text(encoding="utf-8")

        for field in [
            'name="intake_kind"',
            'name="intake_source"',
            'name="reported_by"',
            'name="impact"',
            'name="affected_paths"',
            'name="deployment_dispositions"',
            'name="evidence"',
        ]:
            self.assertIn(field, html)
        self.assertIn('class="card-description-input"', html)
        self.assertIn('class="advanced-card-fields"', html)
        self.assertIn("cardForm.elements.intake_source.value = card ? card?.intake_source", app)
        self.assertIn("payload.affected_paths = formList(payload.affected_paths);", app)
        self.assertIn(
            "payload.deployment_dispositions = formList(payload.deployment_dispositions);",
            app,
        )

    def test_activity_events_open_related_cards(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        app = (STATIC_DIR / "app" / "main.js").read_text(encoding="utf-8")
        model = (STATIC_DIR / "app" / "model.js").read_text(encoding="utf-8")
        sidebar = (STATIC_DIR / "sidebar.css").read_text(encoding="utf-8")
        dialogs = (STATIC_DIR / "dialogs.css").read_text(encoding="utf-8")

        self.assertIn('id="event-card-picker-dialog"', html)
        self.assertIn('id="event-card-picker-list"', html)
        self.assertIn("function relatedCardsForEvent(event)", model)
        self.assertIn("function relatedCardSummary(cards)", model)
        self.assertIn("function openEventCards(event)", app)
        self.assertIn('row.addEventListener("click", () => openEventCards(event));', app)
        self.assertIn("/api/cards/${encodeURIComponent(reference.id)}", app)
        self.assertIn('class="chip archived-chip">archived</span>', app)
        self.assertIn("button.activity-row-linked", sidebar)
        self.assertIn(".event-card-picker-option", dialogs)

    def test_dashboard_exposes_version_hash_tag(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        app = (STATIC_DIR / "app" / "main.js").read_text(encoding="utf-8")
        styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="version-tag"', html)
        self.assertIn("function renderVersionTag(app)", app)
        self.assertIn("renderVersionTag(snapshot.app);", app)
        self.assertIn(".version-pill", styles)

    def test_activity_panel_uses_internal_scroll_without_row_shrink(self) -> None:
        sidebar = (STATIC_DIR / "sidebar.css").read_text(encoding="utf-8")

        self.assertIn("max-height: calc(100vh - 118px);", sidebar)
        self.assertIn("overflow: hidden;", sidebar)
        self.assertIn("flex: 1 1 auto;", sidebar)
        self.assertIn("max-height: none;", sidebar)
        self.assertIn("flex: 0 0 auto;", sidebar)
        self.assertIn(".activity-row {\n  display: flex;", sidebar)

    def test_archive_action_continues_after_individual_failure(self) -> None:
        app = (STATIC_DIR / "app" / "main.js").read_text(encoding="utf-8")

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

for (const file of ["app/state.js", "app/model.js"]) {{
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

for (const file of [
  "app/state.js",
  "app/api.js",
  "app/model.js",
  "app/project-settings.js",
  "app/main.js"
]) {{
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
