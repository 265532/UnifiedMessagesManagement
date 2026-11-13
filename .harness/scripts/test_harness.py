import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness import Harness


class HarnessTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".harness" / "roles").mkdir(parents=True)
        (self.root / ".harness" / "evidence").mkdir(parents=True)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "req.md").write_text("alpha beta", encoding="utf-8")
        self.write_json(".harness/project.json", {
            "schema_version": 1,
            "project": "UnifiedMessagesManagement",
            "canonical_state": ".harness/feature_list.json",
            "policy": {"secret_scan_exclude": []}
        })
        self.write_json(".harness/roles.json", {
            "schema_version": 1,
            "roles": [{"id": "RA-Agent", "prompt_file": ".harness/roles/RA-Agent.md"}]
        })
        (self.root / ".harness" / "roles" / "RA-Agent.md").write_text("role", encoding="utf-8")
        self.write_json(".harness/gates.json", {
            "schema_version": 1,
            "gates": [{"id": "G1", "phase": 1, "required_features": ["RA-01"], "commands": [], "human_approval_required": False}]
        })
        self.write_json(".harness/execution-plan.json", {
            "schema_version": 1,
            "phases": [{"phase": 1, "gate": "G1"}]
        })
        self.write_feature(self.feature())
        self.harness = Harness(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def feature(self, **updates):
        value = {
            "id": "RA-01",
            "title": "requirement",
            "phase": 1,
            "gate": "G1",
            "owner": "RA-Agent",
            "priority": "Must",
            "due": "2026-11-13",
            "human_required": False,
            "depends_on": [],
            "passes": False,
            "dod": ["document exists"],
            "verification": {
                "ready": True,
                "manual": False,
                "files": [{"path": "docs/req.md", "contains": ["alpha"]}],
                "commands": []
            },
            "last_verification": None
        }
        value.update(updates)
        return value

    def write_feature(self, feature):
        self.write_json(".harness/feature_list.json", {
            "schema_version": 1,
            "project": "UnifiedMessagesManagement",
            "status_policy": "test",
            "features": [feature]
        })

    def test_valid_repository(self):
        self.assertEqual([], self.harness.validate())

    def test_duplicate_feature_id_is_rejected(self):
        self.write_json(".harness/feature_list.json", {
            "schema_version": 1, "project": "UnifiedMessagesManagement", "status_policy": "test",
            "features": [self.feature(), self.feature()]
        })
        self.assertTrue(any("重复" in error for error in self.harness.validate()))

    def test_unknown_dependency_is_rejected(self):
        self.write_feature(self.feature(depends_on=["NOPE-99"]))
        self.assertTrue(any("未知依赖" in error for error in self.harness.validate()))

    def test_non_boolean_passes_is_rejected(self):
        self.write_feature(self.feature(passes="true"))
        self.assertTrue(any("passes 必须是布尔值" in error for error in self.harness.validate()))

    def test_verification_must_be_defined_before_work(self):
        feature = self.feature()
        feature["verification"]["ready"] = False
        self.write_feature(feature)
        ok, messages = self.harness.verify("RA-01")
        self.assertFalse(ok)
        self.assertTrue(any("验证规则尚未定义" in message for message in messages))
        self.assertFalse(self.harness.features()["features"][0]["passes"])

    def test_verify_writes_evidence_and_file_change_invalidates_it(self):
        ok, messages = self.harness.verify("RA-01")
        self.assertTrue(ok, messages)
        self.assertTrue(self.harness.features()["features"][0]["passes"])
        (self.root / "docs" / "req.md").write_text("alpha changed", encoding="utf-8")
        self.assertTrue(any("哈希" in error for error in self.harness.validate()))

    def test_human_task_requires_real_approval(self):
        self.write_feature(self.feature(human_required=True))
        ok, messages = self.harness.verify("RA-01")
        self.assertFalse(ok)
        self.assertTrue(any("人工批准" in message for message in messages))
        ok, messages = self.harness.verify("RA-01", human_approved_by="张三")
        self.assertTrue(ok, messages)

    def test_passed_task_is_invalid_when_dependency_regresses(self):
        dependency = self.feature(id="RA-00")
        dependent = self.feature(depends_on=["RA-00"])
        self.write_json(".harness/feature_list.json", {
            "schema_version": 1, "project": "UnifiedMessagesManagement", "status_policy": "test",
            "features": [dependency, dependent],
        })
        self.write_json(".harness/gates.json", {
            "schema_version": 1,
            "gates": [{"id": "G1", "phase": 1, "required_features": ["RA-00", "RA-01"], "commands": [], "human_approval_required": False}],
        })
        self.assertTrue(self.harness.verify("RA-00")[0])
        self.assertTrue(self.harness.verify("RA-01")[0])
        data = self.harness.features()
        data["features"][0]["passes"] = False
        data["features"][0]["last_verification"] = None
        self.write_json(".harness/feature_list.json", data)
        self.assertTrue(any("依赖尚未通过" in error for error in self.harness.validate()))
        ok, messages = self.harness.verify("RA-01")
        self.assertFalse(ok)
        self.assertFalse(self.harness.features()["features"][1]["passes"])
        self.assertIsNone(self.harness.features()["features"][1]["last_verification"])

    def test_failed_dependency_verification_cascades_to_all_passed_dependents(self):
        (self.root / "docs" / "a.md").write_text("alpha", encoding="utf-8")
        (self.root / "docs" / "b.md").write_text("beta", encoding="utf-8")
        dependency = self.feature(id="RA-00", verification={
            "ready": True, "manual": False,
            "files": [{"path": "docs/a.md", "contains": ["alpha"]}], "commands": [],
        })
        dependent = self.feature(depends_on=["RA-00"], verification={
            "ready": True, "manual": False,
            "files": [{"path": "docs/b.md", "contains": ["beta"]}], "commands": [],
        })
        self.write_json(".harness/feature_list.json", {
            "schema_version": 1, "project": "UnifiedMessagesManagement", "status_policy": "test",
            "features": [dependency, dependent],
        })
        self.write_json(".harness/gates.json", {
            "schema_version": 1,
            "gates": [{"id": "G1", "phase": 1, "required_features": ["RA-00", "RA-01"], "commands": [], "human_approval_required": False}],
        })
        self.assertTrue(self.harness.verify("RA-00")[0])
        self.assertTrue(self.harness.verify("RA-01")[0])
        (self.root / "docs" / "a.md").write_text("changed", encoding="utf-8")
        ok, messages = self.harness.verify("RA-00")
        self.assertFalse(ok)
        features = self.harness.features()["features"]
        self.assertFalse(features[0]["passes"])
        self.assertFalse(features[1]["passes"])
        self.assertIsNone(features[1]["last_verification"])
        (self.root / "docs" / "a.md").write_text("alpha", encoding="utf-8")
        self.assertTrue(self.harness.verify("RA-00")[0])
        self.assertFalse(self.harness.features()["features"][1]["passes"])
        self.assertTrue(self.harness.verify("RA-01")[0])

    def test_verify_writes_independent_record_and_validate_detects_tampering(self):
        ok, messages = self.harness.verify("RA-01")
        self.assertTrue(ok, messages)
        feature = self.harness.features()["features"][0]
        record_path = self.root / feature["last_verification"]["record_path"]
        self.assertTrue(record_path.is_file())
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["passed"] = False
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertTrue(any("任务验证归档" in error for error in self.harness.validate()))

    def test_human_gate_persists_approval_and_command_evidence(self):
        self.write_json(".harness/gates.json", {
            "schema_version": 1,
            "gates": [{
                "id": "G1", "phase": 1, "required_features": ["RA-01"],
                "commands": ["python -c \"print('gate-ok')\""], "human_approval_required": True,
            }],
        })
        ok, messages = self.harness.verify("RA-01")
        self.assertTrue(ok, messages)
        ok, messages = self.harness.gate("G1", human_approved_by="李四")
        self.assertTrue(ok, messages)
        record_path = self.root / ".harness" / "evidence" / "G1" / "result.json"
        self.assertTrue(record_path.is_file())
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual("李四", record["human_approved_by"])
        self.assertEqual(0, record["commands"][0]["exit_code"])
        self.assertEqual(["RA-01"], record["required_features"])
        pointer = self.harness.load(".harness/gate_state.json")["gates"]["G1"]
        self.assertEqual(self.harness.sha256(record_path), pointer["record_sha256"])
        self.assertTrue(pointer["passed"])

    def test_gate_rechecks_task_evidence_hashes_and_independent_records(self):
        ok, messages = self.harness.verify("RA-01")
        self.assertTrue(ok, messages)
        (self.root / "docs" / "req.md").write_text("alpha changed", encoding="utf-8")
        ok, messages = self.harness.gate("G1")
        self.assertFalse(ok)
        self.assertTrue(any("文件哈希已变化" in message for message in messages))
        (self.root / "docs" / "req.md").write_text("alpha beta", encoding="utf-8")
        ok, messages = self.harness.gate("G1")
        self.assertTrue(ok, messages)
        (self.root / ".harness" / "evidence" / "RA-01" / "result.json").unlink()
        ok, messages = self.harness.gate("G1")
        self.assertFalse(ok)
        self.assertTrue(any("任务验证归档缺失" in message for message in messages))

    def test_failed_gate_persists_failure_record(self):
        ok, messages = self.harness.gate("G1")
        self.assertFalse(ok)
        record_path = self.root / ".harness" / "evidence" / "G1" / "result.json"
        self.assertTrue(record_path.is_file())
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertFalse(record["passed"])
        self.assertTrue(record["errors"])
        self.assertEqual(["RA-01"], record["required_features"])
        self.assertTrue(any("失败记录已归档" in message for message in messages))
        pointer = self.harness.load(".harness/gate_state.json")["gates"]["G1"]
        self.assertFalse(pointer["passed"])
        self.assertEqual(self.harness.sha256(record_path), pointer["record_sha256"])

    def test_empty_gate_definition_cannot_be_washed_into_success(self):
        self.write_json(".harness/gates.json", {
            "schema_version": 1,
            "gates": [{"id": "G1", "phase": 1, "required_features": [], "commands": [], "human_approval_required": False}],
        })
        self.assertTrue(any("必需任务" in error for error in self.harness.validate()))
        self.assertFalse(self.harness.gate("G1")[0])
        self.assertFalse(self.harness.gate("G1")[0])
        record = self.harness.load(".harness/evidence/G1/result.json")
        self.assertFalse(record["passed"])

    def test_forged_passed_gate_record_is_rejected(self):
        record_path = self.root / ".harness" / "evidence" / "G1" / "result.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps({
            "schema_version": 1, "gate": "G1", "verified_at": "2026-11-13T00:00:00+00:00",
            "passed": True, "human_approved_by": None, "required_features": ["RA-01"],
            "commands": [], "errors": [],
        }, ensure_ascii=False), encoding="utf-8")
        errors = self.harness.validate()
        self.assertTrue(any("门禁归档" in error for error in errors))

    def test_non_completed_stop_reason_cannot_claim_completion(self):
        report = {
            "schema_version": 1, "task_id": "RA-01", "agent": "RA-Agent",
            "stop_reason": "max-tokens", "status": "completed", "summary": "partial",
            "artifacts": [], "dod_checks": [], "commands": [], "blockers": [],
            "next_action": "continue", "retry_count": 0,
            "human_approval": {"required": False, "approved_by": None}
        }
        path = self.root / "report.json"
        self.write_json("report.json", report)
        self.assertTrue(any("stop_reason" in error for error in self.harness.report(path)))

    def test_secret_scan_detects_key_but_ignores_placeholder(self):
        (self.root / "docs" / "secret.txt").write_text("key=sk-" + "abcdefghijklmnopqrstuvwxyz123456", encoding="utf-8")
        (self.root / "docs" / "github.txt").write_text("token=ghp_" + "a" * 36, encoding="utf-8")
        (self.root / "docs" / "safe.txt").write_text("key=replace-me", encoding="utf-8")
        errors = self.harness.scan_secrets()
        self.assertTrue(any("secret.txt" in error for error in errors))
        self.assertTrue(any("github.txt" in error for error in errors))
        self.assertFalse(any("safe.txt" in error for error in errors))

    def test_secret_scan_exclude_supports_glob(self):
        self.write_json(".harness/project.json", {
            "schema_version": 1, "project": "UnifiedMessagesManagement", "canonical_state": ".harness/feature_list.json",
            "policy": {"secret_scan_exclude": ["docs/generated/*"]},
        })
        (self.root / "docs" / "generated").mkdir()
        (self.root / "docs" / "generated" / "fixture.txt").write_text(
            "key=sk-" + "abcdefghijklmnopqrstuvwxyz123456", encoding="utf-8"
        )
        self.assertFalse(any("fixture.txt" in error for error in self.harness.scan_secrets()))

    def test_secret_scan_includes_untracked_files_in_git_repository(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "docs/req.md"], cwd=self.root, check=True)
        (self.root / "docs" / "untracked-secret.txt").write_text(
            "key=sk-" + "abcdefghijklmnopqrstuvwxyz123456", encoding="utf-8"
        )
        errors = self.harness.scan_secrets()
        self.assertTrue(any("untracked-secret.txt" in error for error in errors))

    def test_gate_fails_before_verify_and_passes_after_verify(self):
        ok, messages = self.harness.gate("G1")
        self.assertFalse(ok)
        self.assertTrue(any("RA-01" in message for message in messages))
        ok, messages = self.harness.verify("RA-01")
        self.assertTrue(ok, messages)
        ok, messages = self.harness.gate("G1")
        self.assertTrue(ok, messages)

    def test_openapi_requires_paths(self):
        path = self.root / "openapi.json"
        self.write_json("openapi.json", {"openapi": "3.0.3", "info": {"title": "x", "version": "1"}, "paths": {}})
        self.assertTrue(self.harness.openapi(path))
        self.write_json("openapi.json", {
            "openapi": "3.0.3", "info": {"title": "x", "version": "1"},
            "paths": {"/messages": {"get": {"responses": {"200": {"description": "ok"}}}}}
        })
        self.assertEqual([], self.harness.openapi(path))

    def test_connectivity_requires_real_artifacts_and_stable_hashes(self):
        (self.root / "receive.png").write_bytes(b"image")
        (self.root / "send.png").write_bytes(b"image")
        manifest = {
            "schema_version": 1, "confirmed_by": "张三", "confirmed_at": "2026-11-13T00:00:00+08:00",
            "platforms": [{
                "platform": "feishu", "receive_file": "receive.png", "send_file": "send.png",
                "receive_sha256": self.harness.sha256(self.root / "receive.png"),
                "send_sha256": self.harness.sha256(self.root / "send.png"),
            }]
        }
        self.write_json(".harness/evidence/PREP-03/manifest.json", manifest)
        self.assertEqual([], self.harness.connectivity())
        (self.root / "receive.png").write_bytes(b"changed")
        self.assertTrue(any("哈希" in error for error in self.harness.connectivity()))

    def test_history_requires_task_evidence_bound_to_parent_commit(self):
        git = ["git", "-c", "user.name=Harness Test", "-c", "user.email=test@example.invalid"]
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=self.root, check=True)
        subprocess.run(git + ["add", "-A"], cwd=self.root, check=True)
        subprocess.run(git + ["commit", "-qm", "base"], cwd=self.root, check=True)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout.strip()
        item = self.feature(passes=True)
        evidence = {"files": [{"path": "docs/req.md", "sha256": self.harness.sha256(self.root / "docs/req.md")}], "commands": []}
        record_path, record_hash = self.harness.write_task_result(
            item, True, evidence, [], None, "2026-11-13T00:00:00+00:00"
        )
        item["last_verification"] = {
            "verified_at": "2026-11-13T00:00:00+00:00", "human_approved_by": None,
            "record_path": self.harness.relative(record_path), "record_sha256": record_hash,
            **evidence,
        }
        self.write_feature(item)
        subprocess.run(git + ["add", "-A"], cwd=self.root, check=True)
        subprocess.run(git + ["commit", "-qm", "verified"], cwd=self.root, check=True)
        self.assertEqual([], self.harness.history(base, "HEAD"))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["git_head"] = "0" * 40
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        item["last_verification"]["record_sha256"] = self.harness.sha256(record_path)
        self.write_feature(item)
        subprocess.run(git + ["add", "-A"], cwd=self.root, check=True)
        subprocess.run(git + ["commit", "-qm", "tampered"], cwd=self.root, check=True)
        self.assertTrue(any("git_head" in error for error in self.harness.history(base, "HEAD")))

    def test_doctor_treats_missing_docker_as_optional(self):
        from unittest.mock import patch
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if command[:1] == ["docker"]:
                raise FileNotFoundError("docker")
            return real_run(command, *args, **kwargs)

        with patch("subprocess.run", side_effect=fake_run):
            ok, messages = self.harness.doctor()
        self.assertTrue(ok, messages)
        self.assertTrue(any("Docker: 未安装" in message for message in messages))

    def test_python_verification_command_uses_current_interpreter(self):
        from unittest.mock import patch
        completed = subprocess.CompletedProcess(["python"], 0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=completed) as mocked:
            result = self.harness.run("python -V")
        command = mocked.call_args.args[0]
        self.assertTrue(command.startswith(f'"{sys.executable}"'), command)
        self.assertEqual(0, result["exit_code"])

    def test_non_git_export_checks_env_against_gitignore_text(self):
        (self.root / ".gitignore").write_text(".env\n", encoding="utf-8")
        (self.root / ".env").write_text("APP_KEY=replace-me", encoding="utf-8")
        self.assertFalse(any("未被 .gitignore" in error for error in self.harness.scan_secrets()))


if __name__ == "__main__":
    unittest.main()
