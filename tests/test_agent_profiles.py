from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from kanban_server.store.support import GENERIC_AGENT_PROFILES, discover_agent_profiles_from_dirs

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".codex" / "agents"
SKILL = ROOT / ".codex" / "skills" / "codex-kanban"


class AgentProfileContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profiles = {}
        for path in sorted(AGENTS.glob("*.toml")):
            profile = tomllib.loads(path.read_text(encoding="utf-8"))
            name = profile["name"]
            self.assertNotIn(name, self.profiles, f"Duplicate custom-agent name in {path}")
            self.profiles[name] = profile

    def test_packaged_roles_are_discoverable_and_have_bounded_permissions(self) -> None:
        self.assertEqual(set(self.profiles), set(GENERIC_AGENT_PROFILES))
        self.assertEqual(set(discover_agent_profiles_from_dirs([AGENTS])), set(self.profiles))
        for name, profile in self.profiles.items():
            with self.subTest(role=name):
                self.assertTrue(profile["description"].strip())
                self.assertTrue(profile["developer_instructions"].strip())
                expected = "workspace-write" if name == "project_implementer" else "read-only"
                self.assertEqual(profile["sandbox_mode"], expected)

    def test_subagent_defaults_control_cost_without_changing_the_main_model(self) -> None:
        config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertNotIn("model", config)
        self.assertNotIn("model_reasoning_effort", config)
        self.assertEqual(config["agents"]["default_subagent_model"], "gpt-5.6-sol")
        self.assertEqual(config["agents"]["default_subagent_reasoning_effort"], "high")
        self.assertEqual(config["service_tier"], "default")

    def test_general_roles_allow_explicit_model_and_effort_escalation(self) -> None:
        for name, profile in self.profiles.items():
            if name == "security_reviewer":
                continue
            with self.subTest(role=name):
                # A custom-file pin wins over spawn arguments in Codex. Both must
                # stay open so the parent can request Terra or escalate to Astra.
                self.assertNotIn("model", profile)
                self.assertNotIn("model_reasoning_effort", profile)

    def test_all_roles_override_an_inherited_fast_tier(self) -> None:
        for name, profile in self.profiles.items():
            with self.subTest(role=name):
                self.assertEqual(profile["service_tier"], "default")

    def test_security_specialist_pins_the_verified_defensive_model(self) -> None:
        profile = self.profiles["security_reviewer"]
        self.assertEqual(profile["model"], "gpt-daybreak-blue-latest")
        self.assertEqual(profile["model_reasoning_effort"], "xhigh")

    def test_routing_guide_covers_every_packaged_role(self) -> None:
        guide = (SKILL / "model-routing.md").read_text(encoding="utf-8")
        rows = [
            line.split("|")[1].strip(" `") for line in guide.splitlines() if line.startswith("| `")
        ]
        self.assertCountEqual(rows, self.profiles)
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("[model-routing.md](model-routing.md)", skill)


if __name__ == "__main__":
    unittest.main()
