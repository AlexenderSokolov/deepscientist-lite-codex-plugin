from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"

EXPECTED = {
    "deepscientist-lite-core": {
        "name": "deepscientist-lite",
        "version": "0.8.1-beta.1",
        "skills": {
            "ds-lite",
            "ds-lite-analysis-write",
            "ds-lite-coordinate",
            "ds-lite-experiment",
            "ds-lite-idea",
            "ds-lite-intake",
            "ds-lite-iterate",
            "ds-lite-review",
            "ds-lite-scout",
        },
    },
    "deepscientist-lite-academic": {
        "name": "deepscientist-lite-academic",
        "version": "0.8.1-beta.1",
        "skill_count": 17,
    },
    "deepscientist-lite-web": {
        "name": "deepscientist-lite-web",
        "version": "0.2.0-alpha.1",
        "skills": {"ds-lite-web"},
    },
    "deepscientist-lite-knowledge": {
        "name": "deepscientist-lite-knowledge",
        "version": "0.2.0-alpha.1",
        "skills": {"ds-lite-knowledge"},
    },
    "deepscientist-lite-empirical": {
        "name": "deepscientist-lite-empirical",
        "version": "0.2.0-alpha.1",
        "skills": {"ds-lite-empirical"},
    },
    "deepscientist-lite-engineering": {
        "name": "deepscientist-lite-engineering",
        "version": "0.2.0-alpha.1",
        "skills": {"ds-lite-engineering"},
    },
}


def discovered_skills(plugin: Path) -> set[str]:
    return {
        path.name
        for path in (plugin / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }


class PluginPackageTests(unittest.TestCase):
    def test_core_gateway_requires_complete_terminal_end_report(self) -> None:
        gateway = (
            PLUGINS / "deepscientist-lite-core" / "skills" / "ds-lite" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("every terminal state", gateway)
        self.assertIn("exact End report labels", gateway)
        self.assertIn("repository-relative artifact refs", gateway)
        self.assertIn("never quote raw stderr or absolute private paths", gateway.lower())

    def test_domain_validation_wrappers_exist_for_bash_and_powershell(self) -> None:
        for pack in ("empirical", "engineering"):
            with self.subTest(pack=pack):
                bash = ROOT / f"run_validate_{pack}.sh"
                powershell = ROOT / f"run_validate_{pack}.ps1"
                self.assertTrue(bash.is_file())
                self.assertTrue(powershell.is_file())
                self.assertIn(f"--package {pack}", bash.read_text(encoding="utf-8"))
                self.assertIn(f'"--package", "{pack}"', powershell.read_text(encoding="utf-8"))

    def test_formal_release_wrapper_defaults_to_gate_v2(self) -> None:
        powershell = (ROOT / "run_accept_formal_host.ps1").read_text(encoding="utf-8")
        bash = (ROOT / "run_accept_formal_host.sh").read_text(encoding="utf-8")
        self.assertIn("ds-lite.formal-release-gate.v2", powershell)
        self.assertIn("ds-lite.formal-release-gate.v2", bash)

    def test_marketplace_exposes_six_independent_packages(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        entries = {item["name"]: item for item in marketplace["plugins"]}
        self.assertEqual(
            set(entries),
            {
                "deepscientist-lite",
                "deepscientist-lite-academic",
                "deepscientist-lite-web",
                "deepscientist-lite-knowledge",
                "deepscientist-lite-empirical",
                "deepscientist-lite-engineering",
            },
        )
        self.assertEqual(entries["deepscientist-lite"]["source"]["path"], "./plugins/deepscientist-lite-core")
        self.assertEqual(
            entries["deepscientist-lite-academic"]["source"]["path"],
            "./plugins/deepscientist-lite-academic",
        )

    def test_package_manifests_and_skill_boundaries(self) -> None:
        for directory, expected in EXPECTED.items():
            with self.subTest(package=directory):
                plugin = PLUGINS / directory
                manifest = json.loads(
                    (plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["name"], expected["name"])
                self.assertEqual(manifest["version"], expected["version"])
                self.assertEqual(manifest["skills"], "./skills/")
                skills = discovered_skills(plugin)
                if "skills" in expected:
                    self.assertEqual(skills, expected["skills"])
                else:
                    self.assertEqual(len(skills), expected["skill_count"])
                    self.assertTrue(all(name.startswith("nature-") for name in skills))

    def test_core_hook_source_declares_the_observed_four_event_config(self) -> None:
        core = PLUGINS / "deepscientist-lite-core"
        manifest = json.loads(
            (core / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")
        hooks = json.loads((core / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(hooks["hooks"]),
            {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"},
        )

    def test_academic_agent_metadata_matches_stable_plugin_validator_contract(self) -> None:
        academic = PLUGINS / "deepscientist-lite-academic"
        skills_root = academic / "skills"
        self.assertTrue((skills_root / ".nature-shared").is_dir())
        self.assertFalse((skills_root / ".nature-shared" / "SKILL.md").exists())
        for path in skills_root.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                self.assertTrue((path / "SKILL.md").is_file(), path.name)
        for skill in discovered_skills(academic):
            with self.subTest(skill=skill):
                text = (skills_root / skill / "agents" / "openai.yaml").read_text(
                    encoding="utf-8"
                )
                self.assertIn("interface:\n", text)
                self.assertIn("  display_name:", text)
                self.assertIn("  short_description:", text)
                self.assertIn("policy:\n  allow_implicit_invocation: true", text)
                self.assertNotIn("\nname:", "\n" + text)
                self.assertNotIn("\ndescription:", "\n" + text)
                self.assertNotIn("execution:", text)
                self.assertNotIn("external_effects:", text)

    def test_core_is_small_and_contains_no_optional_runtime(self) -> None:
        core = PLUGINS / "deepscientist-lite-core"
        files = [path for path in core.rglob("*") if path.is_file()]
        total_bytes = sum(path.stat().st_size for path in files)
        # The pinned Codex app-server schema is a generated protocol witness,
        # not an optional runtime or vendored dependency.
        self.assertLessEqual(len(files), 600)
        self.assertLessEqual(total_bytes, 10 * 1024 * 1024)
        self.assertFalse((core / "vendor").exists())
        self.assertFalse(any(path.name.startswith("nature-") for path in (core / "skills").iterdir()))

    def test_domain_packs_remain_single_skill_and_under_alpha_budgets(self) -> None:
        for directory in ("deepscientist-lite-empirical", "deepscientist-lite-engineering"):
            with self.subTest(package=directory):
                root = PLUGINS / directory
                files = [path for path in root.rglob("*") if path.is_file()]
                self.assertLessEqual(len(files), 150)
                self.assertLessEqual(sum(path.stat().st_size for path in files), 5 * 1024 * 1024)
                self.assertEqual(len(discovered_skills(root)), 1)

    def test_optional_packages_publish_core_compatibility(self) -> None:
        for directory in (
            "deepscientist-lite-academic",
            "deepscientist-lite-web",
            "deepscientist-lite-knowledge",
            "deepscientist-lite-empirical",
            "deepscientist-lite-engineering",
        ):
            with self.subTest(package=directory):
                compatibility = json.loads(
                    (PLUGINS / directory / "compatibility.json").read_text(encoding="utf-8")
                )
                self.assertEqual(compatibility["schema_version"], "ds-lite.pack-compatibility.v1")
                self.assertEqual(compatibility["requires"]["plugin"], "deepscientist-lite")
                self.assertEqual(compatibility["requires"]["version"], "0.8.1-beta.1")
                self.assertEqual(compatibility["missing_core"], "blocked")

    def test_all_optional_pack_doctors_fail_closed_then_accept_matching_core(self) -> None:
        scripts = {
            "academic": PLUGINS / "deepscientist-lite-academic" / "scripts" / "ds_lite_pack_doctor.py",
            "web": PLUGINS / "deepscientist-lite-web" / "scripts" / "ds_lite_extensions.py",
            "knowledge": PLUGINS / "deepscientist-lite-knowledge" / "scripts" / "ds_lite_pack_doctor.py",
            "empirical": PLUGINS / "deepscientist-lite-empirical" / "scripts" / "ds_lite_empirical.py",
            "engineering": PLUGINS / "deepscientist-lite-engineering" / "scripts" / "ds_lite_engineering.py",
        }
        for name, script in scripts.items():
            with self.subTest(package=name):
                missing_args = [sys.executable, str(script)]
                if name in {"web", "empirical", "engineering"}:
                    missing_args.append("doctor")
                missing = subprocess.run(missing_args, text=True, encoding="utf-8", capture_output=True)
                self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)
                self.assertEqual(json.loads(missing.stdout)["status"], "blocked")

                passed_args = [sys.executable, str(script)]
                if name in {"web", "empirical", "engineering"}:
                    passed_args.append("doctor")
                passed_args.extend(["--core-root", str(PLUGINS / "deepscientist-lite-core")])
                passed = subprocess.run(passed_args, text=True, encoding="utf-8", capture_output=True)
                self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
                self.assertEqual(json.loads(passed.stdout)["status"], "passed")

    def test_optional_pack_doctor_rejects_incompatible_core_version(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="ds-lite-incompatible-core-"))
        manifest = root / ".codex-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"name": "deepscientist-lite", "version": "0.6.0-beta.1"}),
            encoding="utf-8",
        )
        script = PLUGINS / "deepscientist-lite-academic" / "scripts" / "ds_lite_pack_doctor.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--core-root", str(root)],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["reason"], "incompatible-core")

    def test_repository_package_validator_checks_all_matrices(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "validation" / "validate_packages.py"),
                "--repo-root",
                str(ROOT),
                "--package",
                "all",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual({item["matrix"] for item in receipt["installation_matrices"]}, {
            "core-only", "core+academic", "core+empirical", "core+engineering",
            "core+web", "core+knowledge", "core+web+knowledge", "all-six",
        })
        self.assertTrue(all(item["status"] == "passed" for item in receipt["installation_matrices"]))
        self.assertTrue(all(status == "not-verified" for status in receipt["real_host_gates"].values()))

    def test_formal_release_gate_requires_each_independent_receipt(self) -> None:
        gate_script = ROOT / "tools" / "validation" / "formal_release_gate.py"
        root = Path(tempfile.mkdtemp(prefix="ds-lite-formal-gate-"))
        blocked_output = root / "blocked.json"
        blocked = subprocess.run(
            [sys.executable, str(gate_script), "--output", str(blocked_output)],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertFalse(json.loads(blocked_output.read_text(encoding="utf-8"))["release_allowed"])

        evidence_args: list[str] = []
        for gate in (
            "source", "offline", "cli", "hook", "delegation", "matched_effect",
            "formal_cache", "fresh_desktop", "docs",
        ):
            receipt = root / f"{gate}.json"
            receipt.write_text(
                json.dumps({"schema_version": f"fixture.{gate}.v1", "status": "passed"}),
                encoding="utf-8",
            )
            evidence_args.extend(["--evidence", f"{gate}={receipt}"])
        passed_output = root / "passed.json"
        passed = subprocess.run(
            [sys.executable, str(gate_script), "--output", str(passed_output), *evidence_args],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        result = json.loads(passed_output.read_text(encoding="utf-8"))
        self.assertTrue(result["release_allowed"])
        self.assertFalse(result["adjacent_evidence_inference"])

    def test_formal_release_gate_accepts_utf8_bom_receipts(self) -> None:
        gate_script = ROOT / "tools" / "validation" / "formal_release_gate.py"
        root = Path(tempfile.mkdtemp(prefix="ds-lite-bom-gate-"))
        receipt = root / "source.json"
        receipt.write_bytes(b"\xef\xbb\xbf{\"schema_version\":\"fixture.v1\",\"status\":\"passed\"}")
        output = root / "gate.json"
        completed = subprocess.run(
            [sys.executable, str(gate_script), "--schema-version", "ds-lite.formal-release-gate.v2",
             "--output", str(output), "--evidence", f"source={receipt}"],
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(completed.returncode, 2)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["gates"]["source"]["status"], "passed")
        self.assertFalse(result["release_allowed"])

    def test_complete_v2_profile_requires_session_web_and_wsl_receipts(self) -> None:
        gate_script = ROOT / "tools" / "validation" / "formal_release_gate.py"
        root = Path(tempfile.mkdtemp(prefix="ds-lite-complete-gate-"))
        evidence_args: list[str] = []
        gates = (
            "source", "offline", "cli", "hook", "delegation", "matched_effect",
            "formal_cache", "fresh_desktop", "docs", "provider", "openscience",
            "hook_in_turn_repair", "session_control", "web", "wsl",
        )
        schemas = {
            "source": "ds-lite.upstream-audit.v1",
            "offline": "ds-lite.offline-protocol-acceptance.v1",
            "cli": "ds-lite.cli-acceptance.v1",
            "hook": "ds-lite.trusted-hook-acceptance.v1",
            "delegation": "ds-lite.real-delegation-acceptance.v1",
            "matched_effect": "ds-lite.matched-effect-acceptance.v1",
            "formal_cache": "ds-lite.formal-cache-acceptance.v1",
            "fresh_desktop": "ds-lite.fresh-desktop-acceptance.v1",
            "docs": "ds-lite.docs-acceptance.v1",
            "provider": "ds-lite.academic-provider-acceptance.v1",
            "openscience": "ds-lite.openscience-acceptance.v1",
            "hook_in_turn_repair": "ds-lite.hook-in-turn-repair.v1",
            "session_control": "ds-lite.app-server-conversation-control.v1",
            "web": "ds-lite.web-benchmark-acceptance.v1",
            "wsl": "ds-lite.wsl-tmux-acceptance.v1",
        }
        for gate in gates:
            receipt = root / f"{gate}.json"
            payload = {"schema_version": schemas[gate], "status": "passed"}
            if gate == "hook_in_turn_repair":
                payload.update({
                    "deterministic_verifier": True,
                    "release_evidence": True,
                    "verified_turn_id": "fixture-turn",
                })
            receipt.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            evidence_args.extend(["--evidence", f"{gate}={receipt}"])
        output = root / "complete.json"
        completed = subprocess.run(
            [sys.executable, str(gate_script), "--schema-version", "ds-lite.formal-release-gate.v2",
             "--profile", "ds-lite-0.8.1-complete", "--output", str(output), *evidence_args],
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(result["release_allowed"])
        self.assertIn("hook_in_turn_repair", result["required_gates"])

    def test_complete_v2_profile_rejects_wrong_gate_schema(self) -> None:
        gate_script = ROOT / "tools" / "validation" / "formal_release_gate.py"
        root = Path(tempfile.mkdtemp(prefix="ds-lite-complete-schema-"))
        receipt = root / "cli.json"
        receipt.write_text(
            json.dumps({"schema_version": "ds-lite.rust-transport-probe.v1", "status": "passed"}),
            encoding="utf-8",
        )
        output = root / "complete.json"
        completed = subprocess.run(
            [sys.executable, str(gate_script), "--schema-version", "ds-lite.formal-release-gate.v2",
             "--profile", "ds-lite-0.8.1-complete", "--output", str(output),
             "--evidence", f"cli={receipt}"],
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(completed.returncode, 2)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["gates"]["cli"]["status"], "not-verified")
        self.assertEqual(result["invalid_schema_gates"], ["cli"])

    def test_complete_profile_rejects_unverified_hook_repair_claim(self) -> None:
        gate_script = ROOT / "tools" / "validation" / "formal_release_gate.py"
        root = Path(tempfile.mkdtemp(prefix="ds-lite-unverified-hook-repair-"))
        schemas = {
            "source": "ds-lite.upstream-audit.v1", "offline": "ds-lite.offline-protocol-acceptance.v1",
            "cli": "ds-lite.cli-acceptance.v1", "hook": "ds-lite.trusted-hook-acceptance.v1",
            "delegation": "ds-lite.real-delegation-acceptance.v1", "matched_effect": "ds-lite.matched-effect-acceptance.v1",
            "formal_cache": "ds-lite.formal-cache-acceptance.v1", "fresh_desktop": "ds-lite.fresh-desktop-acceptance.v1",
            "docs": "ds-lite.docs-acceptance.v1", "provider": "ds-lite.academic-provider-acceptance.v1",
            "openscience": "ds-lite.openscience-acceptance.v1", "hook_in_turn_repair": "ds-lite.hook-in-turn-repair.v1",
            "session_control": "ds-lite.app-server-conversation-control.v1", "web": "ds-lite.web-benchmark-acceptance.v1",
            "wsl": "ds-lite.wsl-tmux-acceptance.v1",
        }
        evidence_args: list[str] = []
        for gate, schema in schemas.items():
            receipt = root / f"{gate}.json"
            receipt.write_text(json.dumps({"schema_version": schema, "status": "passed"}), encoding="utf-8")
            evidence_args.extend(["--evidence", f"{gate}={receipt}"])
        output = root / "complete.json"
        completed = subprocess.run(
            [sys.executable, str(gate_script), "--schema-version", "ds-lite.formal-release-gate.v2",
             "--profile", "ds-lite-0.8.1-complete", "--output", str(output), *evidence_args],
            text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertFalse(result["release_allowed"])
        self.assertEqual(result["gates"]["hook_in_turn_repair"]["status"], "not-verified")


if __name__ == "__main__":
    unittest.main()
