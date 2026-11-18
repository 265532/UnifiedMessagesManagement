#!/usr/bin/env python3
"""Tool-independent Harness CLI. Python standard library only."""

import argparse
import fnmatch
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys


REQUIRED_CONFIGS = (
    ".harness/project.json",
    ".harness/feature_list.json",
    ".harness/roles.json",
    ".harness/gates.json",
    ".harness/execution-plan.json",
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|app[_-]?secret|access[_-]?token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_-]{20,}"),
)
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".exe", ".dll", ".ico", ".mp4"}
PLACEHOLDER_MARKERS = ("替换", "TODO", "REPLACE", "<待")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class Harness:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, value):
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"路径必须位于仓库内: {value}") from exc
        return candidate

    def relative(self, path):
        return path.resolve().relative_to(self.root).as_posix()

    def load(self, relative):
        return json.loads(self.path(relative).read_text(encoding="utf-8"))

    def features(self):
        return self.load(".harness/feature_list.json")

    def save_features(self, data):
        self.path(".harness/feature_list.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def feature(self, task_id):
        for item in self.features()["features"]:
            if item["id"] == task_id:
                return item
        raise ValueError(f"未知任务: {task_id}")

    def passed_feature_record_errors(self, item):
        """Cross-check the independent evidence record for a passed feature."""
        errors = []
        task_id = item["id"]
        evidence = item.get("last_verification")
        if not isinstance(evidence, dict):
            return [f"{task_id}: 通过状态缺少 last_verification"]
        record_relative = evidence.get("record_path")
        record_hash = evidence.get("record_sha256")
        record_path = None
        if not record_relative or not record_hash:
            errors.append(f"{task_id}: 通过状态缺少任务验证归档指针")
        else:
            try:
                record_path = self.path(record_relative)
                if not record_path.is_file():
                    errors.append(f"{task_id}: 任务验证归档缺失 {record_relative}")
                elif self.sha256(record_path) != record_hash:
                    errors.append(f"{task_id}: 任务验证归档哈希不一致 {record_relative}")
            except ValueError as exc:
                errors.append(f"{task_id}: 任务验证归档路径无效: {exc}")
        if record_path and record_path.is_file() and self.sha256(record_path) == record_hash:
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{task_id}: 任务验证归档不可解析: {exc}")
            else:
                if record.get("task_id") != task_id or record.get("passed") is not True:
                    errors.append(f"{task_id}: 任务验证归档不是该任务的有效通过记录")
                if record.get("verified_at") != evidence.get("verified_at"):
                    errors.append(f"{task_id}: 任务验证归档时间不一致")
                if record.get("human_approved_by") != evidence.get("human_approved_by"):
                    errors.append(f"{task_id}: 任务验证归档批准人不一致")
                if record.get("files") != evidence.get("files"):
                    errors.append(f"{task_id}: 任务验证归档文件证据不一致")
                record_commands = [
                    {"command": entry.get("command"), "exit_code": entry.get("exit_code")}
                    for entry in record.get("commands", [])
                ]
                if record_commands != evidence.get("commands"):
                    errors.append(f"{task_id}: 任务验证归档命令证据不一致")
        stored = {entry.get("path"): entry.get("sha256") for entry in evidence.get("files", [])}
        for rule in item.get("verification", {}).get("files", []):
            relative = rule.get("path")
            path = self.path(relative)
            if not path.is_file():
                errors.append(f"{task_id}: 通过证据文件缺失 {relative}")
            elif stored.get(relative) != self.sha256(path):
                errors.append(f"{task_id}: 文件哈希已变化，需重新 verify: {relative}")
        return errors

    def bytes_sha256(self, data, suffix=""):
        """Canonicalize text evidence to LF so Git EOL conversion cannot invalidate hashes."""
        if suffix.lower() not in BINARY_SUFFIXES and b"\0" not in data:
            data = data.replace(b"\r\n", b"\n")
        return hashlib.sha256(data).hexdigest()

    def sha256(self, path):
        if path.suffix.lower() in BINARY_SUFFIXES:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        return self.bytes_sha256(path.read_bytes(), path.suffix)

    def git_head(self):
        if not (self.root / ".git").exists():
            return "ungitted"
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "ungitted"

    def write_task_result(self, item, passed, evidence, errors, human_approved_by, verified_at):
        record = {
            "schema_version": 1,
            "task_id": item["id"],
            "verified_at": verified_at,
            "git_head": self.git_head(),
            "passed": passed,
            "human_approved_by": human_approved_by,
            "files": evidence.get("files", []),
            "commands": evidence.get("commands", []),
            "errors": errors,
        }
        record_path = self.path(f".harness/evidence/{item['id']}/result.json")
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return record_path, self.sha256(record_path)

    def invalidate_dependents(self, data, source_ids):
        invalidated = []
        queue = list(source_ids)
        while queue:
            source = queue.pop(0)
            for item in data["features"]:
                if source not in item.get("depends_on", []) or not item.get("passes"):
                    continue
                item["passes"] = False
                item["last_verification"] = None
                self.write_task_result(
                    item,
                    False,
                    {"files": [], "commands": []},
                    [f"上游依赖 {source} 失效，需重新验证"],
                    None,
                    datetime.now(timezone.utc).isoformat(),
                )
                invalidated.append(item["id"])
                queue.append(item["id"])
        return invalidated

    def portable_command(self, command):
        """Resolve a leading `python` to the interpreter running this CLI."""
        if command == "python" or command.startswith("python "):
            quoted = '"' + sys.executable.replace('"', '\\"') + '"'
            return quoted + command[len("python"):]
        return command

    def run(self, command):
        command = self.portable_command(command)
        try:
            result = subprocess.run(
                command,
                cwd=self.root,
                shell=True,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=180,
                env=os.environ.copy(),
            )
            output = (result.stdout + result.stderr).strip()
            return {
                "command": command,
                "exit_code": result.returncode,
                "output_tail": output[-1500:],
            }
        except subprocess.TimeoutExpired:
            return {"command": command, "exit_code": 124, "output_tail": "命令超过 180 秒，已终止"}

    def validate(self):
        errors = []
        configs = {}
        for relative in REQUIRED_CONFIGS:
            try:
                configs[relative] = self.load(relative)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"配置不可读 {relative}: {exc}")
        if errors:
            return errors

        role_data = configs[".harness/roles.json"]
        roles = {item.get("id"): item for item in role_data.get("roles", [])}
        for role_id, role in roles.items():
            prompt = role.get("prompt_file")
            if not prompt or not self.path(prompt).is_file():
                errors.append(f"角色 {role_id} 缺少 persona 文件: {prompt}")

        feature_data = configs[".harness/feature_list.json"]
        features = feature_data.get("features", [])
        ids = [item.get("id") for item in features]
        if len(ids) != len(set(ids)):
            errors.append("任务 ID 重复")
        by_id = {item.get("id"): item for item in features}

        for item in features:
            task_id = item.get("id", "<missing>")
            if item.get("owner") not in roles:
                errors.append(f"{task_id}: 未知负责人 {item.get('owner')}")
            if not isinstance(item.get("passes"), bool):
                errors.append(f"{task_id}: passes 必须是布尔值")
            if not item.get("dod"):
                errors.append(f"{task_id}: DoD 不能为空")
            verification = item.get("verification", {})
            if not isinstance(verification.get("ready"), bool):
                errors.append(f"{task_id}: verification.ready 必须是布尔值")
            if verification.get("ready") and not verification.get("files") and not verification.get("commands"):
                errors.append(f"{task_id}: ready 的验证规则至少需要一个文件或命令")
            if item.get("passes") is True:
                failed_dependencies = [
                    dependency for dependency in item.get("depends_on", [])
                    if dependency in by_id and not by_id[dependency].get("passes")
                ]
                if failed_dependencies:
                    errors.append(f"{task_id}: 依赖尚未通过: {', '.join(failed_dependencies)}")
                if not verification.get("ready"):
                    errors.append(f"{task_id}: 未定义验证规则却标记通过")
                errors.extend(self.passed_feature_record_errors(item))
            for dependency in item.get("depends_on", []):
                if dependency not in by_id:
                    errors.append(f"{task_id}: 未知依赖 {dependency}")
                elif dependency == task_id:
                    errors.append(f"{task_id}: 不能依赖自身")

        visiting, visited = set(), set()

        def visit(task_id):
            if task_id in visiting:
                errors.append(f"依赖存在循环: {task_id}")
                return
            if task_id in visited or task_id not in by_id:
                return
            visiting.add(task_id)
            for dependency in by_id[task_id].get("depends_on", []):
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in by_id:
            visit(task_id)

        gate_data = configs[".harness/gates.json"]
        gates = {item.get("id"): item for item in gate_data.get("gates", [])}
        for gate_id, gate in gates.items():
            required = gate.get("required_features", [])
            if not isinstance(required, list) or not required:
                errors.append(f"{gate_id}: 必需任务不能为空")
                required = []
            must_tasks = {
                item.get("id") for item in features
                if item.get("gate") == gate_id and item.get("priority") == "Must"
            }
            missing_must = must_tasks - set(required)
            if missing_must:
                errors.append(f"{gate_id}: Must 任务未纳入门禁: {', '.join(sorted(missing_must))}")
            for task_id in required:
                if task_id not in by_id:
                    errors.append(f"{gate_id}: 未知任务 {task_id}")
                elif by_id[task_id].get("gate") != gate_id:
                    errors.append(f"{gate_id}: {task_id} 的 gate 字段不一致")
        for item in features:
            gate = gates.get(item.get("gate"))
            if not gate:
                errors.append(f"{item.get('id')}: 未知质量门 {item.get('gate')}")
            elif gate.get("phase") != item.get("phase"):
                errors.append(f"{item.get('id')}: phase 与质量门不一致")

        phases = configs[".harness/execution-plan.json"].get("phases", [])
        for phase in phases:
            gate = gates.get(phase.get("gate"))
            if not gate or gate.get("phase") != phase.get("phase"):
                errors.append(f"执行计划 phase/gate 不一致: {phase}")

        evidence_root = self.path(".harness/evidence")
        gate_state_path = self.path(".harness/gate_state.json")
        gate_state = {"gates": {}}
        if gate_state_path.is_file():
            try:
                loaded_state = json.loads(gate_state_path.read_text(encoding="utf-8"))
                if not isinstance(loaded_state, dict) or not isinstance(loaded_state.get("gates"), dict):
                    raise ValueError("顶层必须是包含 gates 对象的对象")
                gate_state = loaded_state
            except (json.JSONDecodeError, ValueError) as exc:
                errors.append(f"gate_state.json 不可解析: {exc}")
        if evidence_root.is_dir():
            for record_path in sorted(evidence_root.glob("G[0-6]/result.json")):
                relative = self.relative(record_path)
                try:
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(f"门禁归档不可解析 {relative}: {exc}")
                    continue
                gate_id = record.get("gate")
                gate = gates.get(gate_id)
                prefix = f"门禁归档 {relative}"
                if not gate or record_path.parent.name != gate_id:
                    errors.append(f"{prefix}: gate 与目录不匹配")
                    continue
                pointer = gate_state.get("gates", {}).get(gate_id)
                if not isinstance(pointer, dict):
                    errors.append(f"{prefix}: gate_state.json 缺少该门禁的归档指针")
                else:
                    if pointer.get("record_path") != relative:
                        errors.append(f"{prefix}: gate_state.json 记录路径不一致")
                    if pointer.get("record_sha256") != self.sha256(record_path):
                        errors.append(f"{prefix}: gate_state.json 记录哈希不一致")
                    if pointer.get("verified_at") != record.get("verified_at"):
                        errors.append(f"{prefix}: gate_state.json 记录时间不一致")
                    if pointer.get("passed") != record.get("passed"):
                        errors.append(f"{prefix}: gate_state.json 结论不一致")
                if record.get("schema_version") != 1 or not record.get("verified_at"):
                    errors.append(f"{prefix}: schema_version/verified_at 缺失")
                if record.get("required_features") != gate.get("required_features"):
                    errors.append(f"{prefix}: required_features 与 gates.json 不一致")
                if not isinstance(record.get("passed"), bool):
                    errors.append(f"{prefix}: passed 必须是布尔值")
                elif record["passed"]:
                    if record.get("errors"):
                        errors.append(f"{prefix}: 通过记录仍包含错误")
                    if any(command.get("exit_code") != 0 for command in record.get("commands", [])):
                        errors.append(f"{prefix}: 通过记录包含失败命令")
                    if gate.get("human_approval_required") and not record.get("human_approved_by"):
                        errors.append(f"{prefix}: 人工门禁缺少批准人")
                    for task_id in gate.get("required_features", []):
                        if task_id in by_id and not by_id[task_id].get("passes"):
                            errors.append(f"{prefix}: {task_id} 当前未通过，归档不能作为通过凭据")
                elif not record.get("errors"):
                    errors.append(f"{prefix}: 失败记录缺少错误原因")
        return errors

    def check_feature(self, item, human_approved_by=None, use_stored_approval=False):
        errors = []
        verification = item.get("verification", {})
        if not verification.get("ready"):
            return {"files": [], "commands": []}, ["验证规则尚未定义，先由 Arch/Super 补齐 verification"]
        approval = human_approved_by
        if use_stored_approval and not approval:
            approval = (item.get("last_verification") or {}).get("human_approved_by")
        if (item.get("human_required") or verification.get("manual")) and not approval:
            errors.append(f"{item['id']}: 需要真实人工批准，使用 --human-approved-by")

        file_evidence = []
        for rule in verification.get("files", []):
            relative = rule["path"]
            path = self.path(relative)
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"证据文件缺失或为空: {relative}")
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for expected in rule.get("contains", []):
                if expected not in text:
                    errors.append(f"{relative} 缺少必需内容: {expected}")
            file_evidence.append({"path": relative, "sha256": self.sha256(path)})

        command_evidence = []
        for command in verification.get("commands", []):
            result = self.run(command)
            command_evidence.append(result)
            if result["exit_code"] != 0:
                errors.append(f"验证命令失败 ({result['exit_code']}): {command}; {result['output_tail']}")
        return {"files": file_evidence, "commands": command_evidence}, errors

    def verify(self, task_id, human_approved_by=None):
        data = self.features()
        item = next((entry for entry in data["features"] if entry["id"] == task_id), None)
        if not item:
            return False, [f"未知任务: {task_id}"]
        verified_at = datetime.now(timezone.utc).isoformat()
        dependency_errors = []
        failed_dependencies = []
        for dependency in item.get("depends_on", []):
            dependency_item = self.feature(dependency)
            if not dependency_item.get("passes"):
                failed_dependencies.append(dependency)
                continue
            dependency_errors.extend(self.passed_feature_record_errors(dependency_item))
            _, runtime_errors = self.check_feature(dependency_item, use_stored_approval=True)
            dependency_errors.extend(f"{dependency}: {error}" for error in runtime_errors)
        if failed_dependencies or dependency_errors:
            errors = []
            if failed_dependencies:
                errors.append(f"依赖尚未通过: {', '.join(failed_dependencies)}")
            errors.extend(f"依赖证据失效: {error}" for error in dependency_errors)
            record_path, _ = self.write_task_result(item, False, {"files": [], "commands": []}, errors, human_approved_by, verified_at)
            if item.get("passes") is True:
                item["passes"] = False
                item["last_verification"] = None
                invalidated = self.invalidate_dependents(data, [task_id])
                self.save_features(data)
                if invalidated:
                    errors.append(f"级联失效: {', '.join(invalidated)}")
            return False, errors + [f"失败记录已归档: {self.relative(record_path)}"]
        evidence, errors = self.check_feature(item, human_approved_by=human_approved_by)
        record_path, record_hash = self.write_task_result(item, not errors, evidence, errors, human_approved_by, verified_at)
        if errors:
            if item.get("passes") is True:
                item["passes"] = False
                item["last_verification"] = None
                invalidated = self.invalidate_dependents(data, [task_id])
                self.save_features(data)
                if invalidated:
                    errors.append(f"级联失效: {', '.join(invalidated)}")
            return False, errors + [f"失败记录已归档: {self.relative(record_path)}"]
        item["passes"] = True
        item["last_verification"] = {
            "verified_at": verified_at,
            "human_approved_by": human_approved_by,
            "record_path": self.relative(record_path),
            "record_sha256": record_hash,
            "files": evidence["files"],
            "commands": [
                {"command": entry["command"], "exit_code": entry["exit_code"]}
                for entry in evidence["commands"]
            ],
        }
        self.save_features(data)
        return True, [f"{task_id} 验证通过，独立证据已归档: {self.relative(record_path)}"]

    def gate(self, gate_id, human_approved_by=None):
        gates = self.load(".harness/gates.json")["gates"]
        gate = next((item for item in gates if item["id"] == gate_id), None)
        if not gate:
            return False, [f"未知质量门: {gate_id}"]
        errors = [f"仓库结构校验失败: {error}" for error in self.validate()]
        if gate.get("human_approval_required") and not human_approved_by:
            errors.append(f"{gate_id} 需要人工批准，使用 --human-approved-by")
        for task_id in gate.get("required_features", []):
            item = self.feature(task_id)
            if not item.get("passes"):
                errors.append(f"{task_id} 尚未通过")
                continue
            errors.extend(f"{task_id}: {error}" for error in self.passed_feature_record_errors(item))
            _, feature_errors = self.check_feature(item, use_stored_approval=True)
            errors.extend(f"{task_id}: {error}" for error in feature_errors)
        command_evidence = []
        for command in gate.get("commands", []):
            result = self.run(command)
            command_evidence.append(result)
            if result["exit_code"] != 0:
                errors.append(f"门禁命令失败: {command}; {result['output_tail']}")
        record = {
            "schema_version": 1,
            "gate": gate_id,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "passed": not errors,
            "human_approved_by": human_approved_by,
            "required_features": gate.get("required_features", []),
            "commands": command_evidence,
            "errors": errors,
        }
        record_path = self.path(f".harness/evidence/{gate_id}/result.json")
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state_path = self.path(".harness/gate_state.json")
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or not isinstance(state.get("gates"), dict):
                raise ValueError("顶层必须是包含 gates 对象的对象")
        except (OSError, json.JSONDecodeError, ValueError):
            state = {"schema_version": 1, "project": self.load(".harness/project.json")["project"], "gates": {}}
        state["gates"][gate_id] = {
            "record_path": self.relative(record_path),
            "record_sha256": self.sha256(record_path),
            "passed": record["passed"],
            "verified_at": record["verified_at"],
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if errors:
            return False, errors + [f"失败记录已归档: {self.relative(record_path)}"]
        suffix = f"，人工批准人 {human_approved_by}" if human_approved_by else ""
        return True, [f"{gate_id} 通过{suffix}，证据已归档: {self.relative(record_path)}"]

    def report(self, report_path):
        errors = []
        try:
            report = json.loads(self.path(report_path).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return [f"报告不可读: {exc}"]
        required = (
            "schema_version", "task_id", "agent", "stop_reason", "status", "summary",
            "artifacts", "dod_checks", "commands", "blockers", "next_action", "retry_count", "human_approval",
        )
        for field in required:
            if field not in report:
                errors.append(f"报告缺少字段: {field}")
        if errors:
            return errors
        try:
            item = self.feature(report["task_id"])
        except ValueError as exc:
            return [str(exc)]
        if report["agent"] not in {item["owner"], "Super-Agent"}:
            errors.append(f"报告角色 {report['agent']} 与任务负责人 {item['owner']} 不一致")
        if report["stop_reason"] != "completed" and report["status"] == "completed":
            errors.append("stop_reason 非 completed 时不得声称 completed")
        if report["stop_reason"] == "completed" and report["status"] != "completed":
            errors.append("stop_reason=completed 时 status 必须为 completed")
        if report["status"] == "completed":
            if not report["dod_checks"] or not all(check.get("passed") is True for check in report["dod_checks"]):
                errors.append("完成报告必须包含全部通过的 DoD 检查")
            if not report["artifacts"] and not report["commands"]:
                errors.append("完成报告必须至少包含产物或可重跑命令")
            if any(command.get("exit_code") != 0 for command in report["commands"]):
                errors.append("完成报告包含失败命令")
            approval = report.get("human_approval", {})
            if item.get("human_required") and not approval.get("approved_by"):
                errors.append("人工任务的完成报告缺少 approved_by")
        for artifact in report.get("artifacts", []):
            try:
                path = self.path(artifact["path"])
                if not path.is_file():
                    errors.append(f"报告产物不存在: {artifact['path']}")
                elif artifact.get("sha256") and artifact["sha256"] != self.sha256(path):
                    errors.append(f"报告产物哈希不一致: {artifact['path']}")
            except (KeyError, ValueError) as exc:
                errors.append(f"报告产物无效: {exc}")
        if report.get("retry_count", 0) > 2:
            errors.append("自动重试次数超过 2 次")
        return errors

    def scan_secrets(self):
        errors = []
        exclude = set(self.load(".harness/project.json").get("policy", {}).get("secret_scan_exclude", []))
        files = []
        if (self.root / ".git").exists():
            result = subprocess.run(
                ["git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if result.returncode == 0:
                files = [self.root / line for line in result.stdout.splitlines() if line]
        if not files:
            files = [path for path in self.root.rglob("*") if path.is_file() and ".git" not in path.parts]
        for path in files:
            relative = self.relative(path)
            excluded = any(fnmatch.fnmatch(relative, pattern) for pattern in exclude)
            if excluded or path.suffix.lower() in BINARY_SUFFIXES or path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    errors.append(f"疑似密钥: {relative} 匹配 {pattern.pattern}")
                    break
        if (self.root / ".env").exists():
            if (self.root / ".git").exists():
                result = subprocess.run(["git", "check-ignore", ".env"], cwd=self.root, capture_output=True)
                if result.returncode != 0:
                    errors.append(".env 存在但未被 .gitignore 排除")
            else:
                gitignore = self.root / ".gitignore"
                patterns = []
                if gitignore.is_file():
                    patterns = [
                        line.strip() for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
                        if line.strip() and not line.lstrip().startswith("#") and not line.startswith("!")
                    ]
                if not any(fnmatch.fnmatch(".env", pattern) for pattern in patterns):
                    errors.append(".env 存在但未被 .gitignore 排除")
        return errors

    def connectivity(self):
        relative = ".harness/evidence/PREP-03/manifest.json"
        try:
            manifest = self.load(relative)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return [f"连通证据 manifest 不可读: {exc}"]
        errors = []
        confirmed_by = manifest.get("confirmed_by", "")
        if not confirmed_by or any(marker in confirmed_by for marker in PLACEHOLDER_MARKERS):
            errors.append("连通证据缺少真实 confirmed_by")
        confirmed_at = manifest.get("confirmed_at", "")
        if not confirmed_at or any(marker in confirmed_at for marker in PLACEHOLDER_MARKERS):
            errors.append("连通证据缺少真实 confirmed_at")
        platforms = manifest.get("platforms", [])
        connected = []
        for platform in platforms:
            name = platform.get("platform", "<unknown>")
            receive = platform.get("receive_file")
            send = platform.get("send_file")
            if not receive and not send:
                continue
            if not receive or not send:
                errors.append(f"{name}: 接收与发送证据必须成对")
                continue
            receive_path, send_path = self.path(receive), self.path(send)
            if not receive_path.is_file() or receive_path.stat().st_size == 0:
                errors.append(f"{name}: 接收证据缺失 {receive}")
            if not send_path.is_file() or send_path.stat().st_size == 0:
                errors.append(f"{name}: 发送证据缺失 {send}")
            for label, path, expected_hash in (
                ("接收", receive_path, platform.get("receive_sha256")),
                ("发送", send_path, platform.get("send_sha256")),
            ):
                if not expected_hash or any(marker in expected_hash for marker in PLACEHOLDER_MARKERS):
                    errors.append(f"{name}: {label}证据缺少 SHA-256")
                elif not SHA256_PATTERN.fullmatch(expected_hash):
                    errors.append(f"{name}: {label}证据 SHA-256 格式无效")
                elif path.is_file() and expected_hash != self.sha256(path):
                    errors.append(f"{name}: {label}证据哈希已变化")
            if (
                receive_path.is_file() and send_path.is_file()
                and receive_path.stat().st_size > 0 and send_path.stat().st_size > 0
                and platform.get("receive_sha256") == self.sha256(receive_path)
                and platform.get("send_sha256") == self.sha256(send_path)
            ):
                connected.append(name)
        if not connected:
            errors.append("至少一个平台必须同时具备真实接收与发送证据")
        return errors

    def openapi(self, value):
        try:
            document = json.loads(self.path(value).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return [f"OpenAPI 不可解析: {exc}"]
        errors = []
        if not str(document.get("openapi", "")).startswith("3."):
            errors.append("OpenAPI 版本必须为 3.x")
        info = document.get("info", {})
        if not info.get("title") or not info.get("version"):
            errors.append("OpenAPI info.title/version 缺失")
        paths = document.get("paths")
        if not isinstance(paths, dict) or not paths:
            errors.append("OpenAPI paths 不能为空")
            return errors
        for route, path_item in paths.items():
            if not isinstance(path_item, dict):
                errors.append(f"{route}: path item 必须为对象")
                continue
            for method, operation in path_item.items():
                if method.lower() in {"get", "post", "put", "patch", "delete"}:
                    if not isinstance(operation, dict) or not operation.get("responses"):
                        errors.append(f"{route} {method}: responses 缺失")
        return errors

    def page_budget(self, value, maximum):
        try:
            text = self.path(value).read_text(encoding="utf-8")
        except OSError as exc:
            return [f"文档不可读: {exc}"]
        match = re.search(r"(?i)(?:页数|pages?)\s*[:：]\s*(\d+)", text)
        if not match:
            return ["文档必须明确写出实测/复核页数，例如“页数：10”"]
        pages = int(match.group(1))
        if pages > maximum:
            return [f"页数 {pages} 超过上限 {maximum}"]
        return []

    def status(self):
        data = self.features()
        by_id = {item["id"]: item for item in data["features"]}
        items = []
        for item in data["features"]:
            dependencies = [dep for dep in item.get("depends_on", []) if not by_id[dep].get("passes")]
            if item.get("passes"):
                state = "passed"
            elif dependencies:
                state = "blocked"
            elif not item["verification"].get("ready"):
                state = "needs-verification"
            else:
                state = "ready"
            items.append({
                "id": item["id"], "gate": item["gate"], "owner": item["owner"], "due": item["due"],
                "state": state, "human_required": item["human_required"], "blocked_by": dependencies,
                "title": item["title"],
            })
        gates = []
        for gate_id in sorted({item["gate"] for item in data["features"]}):
            group = [item for item in data["features"] if item["gate"] == gate_id]
            gates.append({"gate": gate_id, "passed": sum(item["passes"] is True for item in group), "total": len(group)})
        return {
            "project": data["project"],
            "passed": sum(item["passes"] is True for item in data["features"]),
            "total": len(data["features"]),
            "gates": gates,
            "tasks": items,
        }

    def ci(self):
        errors = self.validate() + self.scan_secrets()
        if errors:
            return errors
        for item in self.features()["features"]:
            if item.get("passes") is True:
                _, feature_errors = self.check_feature(item, use_stored_approval=True)
                errors.extend(f"{item['id']}: {error}" for error in feature_errors)
        return errors

    def history(self, base, head):
        """Anchor false->true feature transitions to Git history and verify records."""
        if not (self.root / ".git").exists():
            return ["history 需要 Git 仓库"]

        def git(args, binary=False):
            return subprocess.run(
                ["git", *args], cwd=self.root, capture_output=True,
                text=not binary, errors="replace" if not binary else None,
            )

        base_result = git(["rev-parse", "--verify", f"{base}^{{commit}}"])
        head_result = git(["rev-parse", "--verify", f"{head}^{{commit}}"])
        if base_result.returncode or head_result.returncode:
            return [f"history 无法解析 base/head: {base}..{head}"]
        base_commit = base_result.stdout.strip()
        head_commit = head_result.stdout.strip()
        feature_path = ".harness/feature_list.json"

        def committed_features(revision, required=False):
            result = git(["show", f"{revision}:{feature_path}"])
            if result.returncode:
                # A bootstrap commit may have the new state file only in the worktree.
                # After commit, CI will see it; a deleted HEAD state file still fails ci().
                if required and not (self.root / feature_path).is_file():
                    raise ValueError(f"{revision} 缺少 feature_list.json，无法进行历史状态锚点校验")
                return {"features": []}
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{revision} 的 feature_list.json 不可解析: {exc}") from exc

        try:
            before = committed_features(base_commit)
            after = committed_features(head_commit, required=True)
        except ValueError as exc:
            return [str(exc)]
        before_by_id = {item.get("id"): item for item in before.get("features", [])}
        transitions = [
            item for item in after.get("features", [])
            if item.get("passes") is True and not before_by_id.get(item.get("id"), {}).get("passes")
        ]
        if not transitions:
            return []
        commits = git(["rev-list", "--reverse", f"{base_commit}..{head_commit}"])
        allowed_heads = {base_commit} | set(commits.stdout.splitlines())
        errors = []
        for item in transitions:
            task_id = item["id"]
            evidence = item.get("last_verification") or {}
            record_relative = evidence.get("record_path")
            expected = f".harness/evidence/{task_id}/result.json"
            prefix = f"历史状态 {task_id}"
            if record_relative != expected:
                errors.append(f"{prefix}: 通过记录路径必须是 {expected}")
                continue
            record_result = git(["show", f"{head_commit}:{record_relative}"], binary=True)
            if record_result.returncode:
                errors.append(f"{prefix}: 通过记录未随提交保存")
                continue
            raw = record_result.stdout
            if self.bytes_sha256(raw, Path(record_relative).suffix) != evidence.get("record_sha256"):
                errors.append(f"{prefix}: 通过记录哈希与 feature_list 不一致")
                continue
            try:
                record = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"{prefix}: 通过记录不可解析: {exc}")
                continue
            record_head = record.get("git_head")
            if record_head not in allowed_heads:
                errors.append(f"{prefix}: git_head 不在 {base}..{head} 的历史中")
                continue
            if record.get("task_id") != task_id or record.get("passed") is not True:
                errors.append(f"{prefix}: 通过记录与任务不匹配")
            changed = git(["diff", "--name-only", record_head, head_commit, "--", record_relative])
            if changed.returncode or record_relative not in changed.stdout.splitlines():
                errors.append(f"{prefix}: 通过记录未在其 git_head 之后的提交中出现")
        return errors

    def doctor(self):
        messages = [f"Python: {sys.version.split()[0]}", f"仓库根目录: {self.root}"]
        errors = []
        if sys.version_info < (3, 10):
            errors.append("需要 Python 3.10+")
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                errors.append("未找到 git")
            else:
                messages.append(result.stdout.strip())
        except OSError:
            errors.append("未找到 git")
        for relative in REQUIRED_CONFIGS:
            if not self.path(relative).is_file():
                errors.append(f"缺少 {relative}")
        try:
            docker = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            messages.append(docker.stdout.strip() if docker.returncode == 0 else "Docker: 不可用（仅部署任务需要）")
        except OSError:
            messages.append("Docker: 未安装（仅部署任务需要）")
        return not errors, messages + errors

    def bootstrap(self):
        self.path(".harness/evidence").mkdir(parents=True, exist_ok=True)
        messages = []
        if (self.root / ".git").exists():
            result = subprocess.run(["git", "config", "core.hooksPath", ".harness/hooks"], cwd=self.root)
            if result.returncode != 0:
                return False, ["无法配置 core.hooksPath"]
            messages.append("已配置 Git hooks: .harness/hooks")
        errors = self.validate()
        return not errors, messages + (["Harness 结构校验通过"] if not errors else errors)


def print_result(ok, messages):
    for message in messages:
        print(message)
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="UnifiedMessagesManagement portable Harness")
    parser.add_argument("command", choices=[
        "doctor", "bootstrap", "validate", "status", "verify", "gate", "report", "scan-secrets",
        "connectivity", "json", "openapi", "page-budget", "ci", "pre-commit", "history",
    ])
    parser.add_argument("value", nargs="?")
    parser.add_argument("maximum", nargs="?")
    parser.add_argument("--human-approved-by")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    harness = Harness(Path(__file__).resolve().parents[2])

    try:
        if args.command == "doctor":
            ok, messages = harness.doctor()
            return print_result(ok, messages)
        if args.command == "bootstrap":
            ok, messages = harness.bootstrap()
            return print_result(ok, messages)
        if args.command == "validate":
            errors = harness.validate()
            return print_result(not errors, errors or ["Harness 结构校验通过"])
        if args.command == "status":
            status = harness.status()
            if args.json_output:
                print(json.dumps(status, ensure_ascii=False, indent=2))
            else:
                print(f"{status['project']}: {status['passed']}/{status['total']} 个任务通过")
                print("质量门: " + ", ".join(f"{g['gate']}={g['passed']}/{g['total']}" for g in status["gates"]))
                for item in status["tasks"]:
                    if item["state"] != "passed":
                        blocked = f" 依赖={','.join(item['blocked_by'])}" if item["blocked_by"] else ""
                        human = " 人工" if item["human_required"] else ""
                        print(f"[{item['state']}] {item['id']} {item['gate']} {item['owner']} {item['due']}{human}{blocked} - {item['title']}")
            return 0
        if args.command == "verify":
            if not args.value:
                parser.error("verify 需要 TASK_ID")
            ok, messages = harness.verify(args.value, args.human_approved_by)
            return print_result(ok, messages)
        if args.command == "gate":
            if not args.value:
                parser.error("gate 需要 G0~G6")
            ok, messages = harness.gate(args.value, args.human_approved_by)
            return print_result(ok, messages)
        if args.command == "report":
            if not args.value:
                parser.error("report 需要 JSON 路径")
            errors = harness.report(args.value)
            return print_result(not errors, errors or ["Agent 报告结构与证据校验通过；仍需独立 verify"])
        if args.command == "scan-secrets":
            errors = harness.scan_secrets()
            return print_result(not errors, errors or ["密钥扫描通过"])
        if args.command == "connectivity":
            errors = harness.connectivity()
            return print_result(not errors, errors or ["至少一个平台的收发证据完整；真实性由人工批准负责"])
        if args.command == "json":
            if not args.value:
                parser.error("json 需要文件路径")
            harness.load(args.value)
            print(f"JSON 解析通过: {args.value}")
            return 0
        if args.command == "openapi":
            errors = harness.openapi(args.value)
            return print_result(not errors, errors or [f"OpenAPI 校验通过: {args.value}"])
        if args.command == "page-budget":
            if not args.value or args.maximum is None:
                parser.error("page-budget 需要文件路径与最大页数")
            try:
                maximum = int(args.maximum)
            except ValueError:
                parser.error("page-budget 最大页数必须是整数")
            errors = harness.page_budget(args.value, maximum)
            return print_result(not errors, errors or [f"页数符合 ≤{args.maximum} 页"])
        if args.command == "history":
            if not args.value or not args.maximum:
                parser.error("history 需要 BASE_REV 和 HEAD_REV")
            errors = harness.history(args.value, args.maximum)
            return print_result(not errors, errors or [f"Git 历史状态锚点校验通过: {args.value}..{args.maximum}"])
        if args.command in {"ci", "pre-commit"}:
            errors = harness.ci()
            label = "CI" if args.command == "ci" else "pre-commit"
            return print_result(not errors, errors or [f"{label} Harness 校验通过"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Harness 执行错误: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
