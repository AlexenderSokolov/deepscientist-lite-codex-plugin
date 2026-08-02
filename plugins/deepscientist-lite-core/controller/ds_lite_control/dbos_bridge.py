from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PHASE1_WORKFLOW_NAMES = (
    "reconcile_job_v1",
    "run_action_v1",
    "project_status_v1",
)
PHASE2_WORKFLOW_NAMES = PHASE1_WORKFLOW_NAMES + ("run_codex_action_v1",)
PHASE3_WORKFLOW_NAMES = PHASE2_WORKFLOW_NAMES + (
    "schedule_job_v1", "cooldown_gate_v1", "reconcile_gate_v1",
)
PHASE4_WORKFLOW_NAMES = PHASE3_WORKFLOW_NAMES + (
    "verify_gate_v1", "review_gate_v1", "aggregate_release_v1",
)
PHASE5_WORKFLOW_NAMES = PHASE4_WORKFLOW_NAMES + ("run_codex_action_v2",)
PHASE5_CODEX_VERSION = "0.146.0"


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _run_action_body(action_id: str, domain_path: str, owner_id: str, fence_epoch: int,
                     barrier_path: str | None = None, delay_seconds: float = 0.0) -> dict[str, Any]:
    import hashlib

    from .errors import FenceRejected
    from .store import ControlStore

    if barrier_path is not None:
        marker = Path(barrier_path)
        try:
            marker.write_text("workflow-started\n", encoding="ascii")
        except FileExistsError:
            pass
    if delay_seconds:
        from dbos import DBOS
        DBOS.sleep(delay_seconds)
    store = ControlStore(Path(domain_path))
    try:
        try:
            store.transition_outbox(action_id, "host_dispatching", owner_id, fence_epoch)
            store.record_host_event(
                event_id=f"terminal-{action_id}", action_id=action_id, event_type="terminal",
                observed_at="2026-07-31T00:00:00Z",
                payload_hash=hashlib.sha256(f"terminal:{action_id}".encode()).hexdigest(),
                owner_id=owner_id, fence_epoch=fence_epoch,
            )
        except FenceRejected:
            return {"action_id": action_id, "terminal_status": "fenced", "evidence_class": "real-dbos-sqlite"}
        return {"action_id": action_id, "terminal_status": "completed", "evidence_class": "fake-host"}
    finally:
        store.close()


def _reconcile_body(job_id: str, domain_path: str) -> dict[str, Any]:
    from .store import ControlStore

    store = ControlStore(Path(domain_path))
    try:
        return store.project_status(job_id)
    finally:
        store.close()


def _cooldown_gate_body(
    work_item_id: str,
    domain_path: str,
    owner_id: str,
    fence_epoch: int,
    delay_seconds: float,
    sleep_fn=None,
    now=None,
    barrier_path: str | None = None,
) -> dict[str, Any]:
    from .errors import FenceRejected
    from .store import ControlStore

    if sleep_fn is None:
        from dbos import DBOS
        sleep_fn = DBOS.sleep
    if barrier_path is not None:
        marker = Path(barrier_path)
        try:
            with marker.open("x", encoding="ascii", newline="\n") as handle:
                handle.write("cooldown-sleep-started\n")
                handle.flush()
                import os
                os.fsync(handle.fileno())
        except FileExistsError:
            pass
    sleep_fn(delay_seconds)
    store = ControlStore(Path(domain_path), clock=(lambda: now) if now is not None else None)
    try:
        try:
            state = store.mark_gate_ready_if_due(work_item_id, owner_id, fence_epoch)
        except FenceRejected:
            return {
                "work_item_id": work_item_id, "terminal_status": "fenced",
                "evidence_class": "real-dbos-sqlite",
            }
        return {
            "work_item_id": work_item_id,
            "terminal_status": "ready" if state == "pending" else state,
            "evidence_class": "real-dbos-sqlite",
        }
    finally:
        store.close()


def _schedule_job_body(
    job_id: str,
    domain_path: str,
    owner_id: str,
    max_concurrency: int = 2,
    retry_concurrency: int = 1,
) -> dict[str, Any]:
    from .failure_policy import FailureClassifier
    from .scheduler import DagScheduler
    from .store import ControlStore

    store = ControlStore(Path(domain_path))
    try:
        scheduler = DagScheduler(
            store, FailureClassifier(seed=20260731),
            max_concurrency=max_concurrency, retry_concurrency=retry_concurrency,
        )
        scheduler.requeue_due(job_id)
        claims = scheduler.claim_ready(job_id, owner_id)
        return {
            "job_id": job_id,
            "claimed_action_ids": [claim.action_id for claim in claims],
            "terminal_status": "scheduled",
            "evidence_class": "real-dbos-sqlite",
        }
    finally:
        store.close()


def _reconcile_gate_body(work_item_id: str, domain_path: str) -> dict[str, Any]:
    from .store import ControlStore

    store = ControlStore(Path(domain_path))
    try:
        item = store.work_item(work_item_id)
        return {
            "work_item_id": work_item_id,
            "terminal_status": str(item["state"]),
            "next_eligible_at": item["next_eligible_at"],
            "evidence_class": str(item["evidence_class"]),
        }
    finally:
        store.close()


def _verify_gate_body(
    work_item_id: str, evidence_set_id: str, policy: dict[str, Any], domain_path: str,
    receipt_root: str, owner_id: str, fence_epoch: int,
) -> dict[str, Any]:
    from .store import ControlStore
    from .verification import DeterministicVerifier

    store = ControlStore(Path(domain_path))
    try:
        return DeterministicVerifier(store, Path(receipt_root)).verify(
            work_item_id, evidence_set_id, policy,
            owner_id=owner_id, fence_epoch=fence_epoch,
        )
    finally:
        store.close()


def _review_gate_body(review_id: str, domain_path: str) -> dict[str, Any]:
    from .store import ControlStore

    store = ControlStore(Path(domain_path))
    try:
        row = store.connection.execute(
            "SELECT state,reviewer_thread_id,reviewer_turn_id FROM review_requests WHERE review_id=?",
            (review_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown review request")
        return {
            "review_id": review_id, "terminal_status": str(row[0]),
            "thread_bound": row[1] is not None, "turn_bound": row[2] is not None,
            "evidence_class": "domain-review-reconciliation",
        }
    finally:
        store.close()


def _aggregate_release_body(job_id: str, profile: dict[str, Any], domain_path: str,
                            receipt_root: str) -> dict[str, Any]:
    from .release import StrictReleaseAggregate
    from .store import ControlStore

    store = ControlStore(Path(domain_path))
    try:
        return StrictReleaseAggregate(store, Path(receipt_root)).decide(job_id, profile)
    finally:
        store.close()


def _run_codex_action_common(
    action_id: str, domain_path: str, owner_id: str, fence_epoch: int,
    codex_bin: str, schema_root: str, codex_home: str,
    spool_path: str, input_items: list[dict[str, Any]],
    observe_timeout: float = 120.0, *, resume_bound_thread: bool,
) -> dict[str, Any]:
    import hashlib
    import os
    import subprocess

    from .app_server import AppServerAdapter, ProtocolSpool
    from .codex_actions import CodexActionRunner
    from .store import ControlStore

    store = ControlStore(Path(domain_path))
    process = None
    try:
        action = store.action_context(action_id)
        command = [codex_bin, "app-server"]
        env = os.environ.copy()
        if codex_home:
            env["CODEX_HOME"] = str(Path(codex_home).resolve())
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", env=env,
        )
        adapter = AppServerAdapter(
            process, Path(schema_root), response_timeout=30.0,
            spool=ProtocolSpool(Path(spool_path)),
        )
        adapter.initialize(request_id=f"{action_id}:initialize")
        if resume_bound_thread:
            binding = store.thread_binding(action["attempt_id"])
            thread_id = str(binding.get("thread_id") or "")
            if not thread_id:
                raise RuntimeError("run_codex_action_v2 canonical thread missing")
            resumed = adapter.resume_thread(
                thread_id, request_id=f"{action_id}:thread-resume"
            )
            if resumed.thread_id != thread_id:
                raise RuntimeError("run_codex_action_v2 canonical thread resume mismatch")
        runner = CodexActionRunner(store, adapter)
        observation = runner.dispatch_turn(
            action_id, action["attempt_id"], input_items, owner_id, fence_epoch,
        )
        if observation.disposition == "ambiguous":
            return {"action_id": action_id, "terminal_status": "ambiguous", "evidence_class": "real-codex"}
        terminal = adapter.observe_turn(
            str(observation.thread_id), str(observation.turn_id), timeout=observe_timeout,
        )
        if terminal.disposition == "failed":
            store.record_host_event(
                event_id=f"codex-terminal-{action_id}", action_id=action_id,
                event_type="terminal-failed", observed_at="2026-07-31T00:00:00Z",
                payload_hash=hashlib.sha256(
                    json.dumps(terminal.response, sort_keys=True).encode()
                ).hexdigest(),
                owner_id=owner_id, fence_epoch=fence_epoch,
            )
            return {
                "action_id": action_id, "terminal_status": "failed",
                "evidence_class": "real-codex",
            }
        if terminal.disposition != "terminal":
            return {"action_id": action_id, "terminal_status": "ambiguous", "evidence_class": "real-codex"}
        store.record_host_event(
            event_id=f"codex-terminal-{action_id}", action_id=action_id, event_type="terminal",
            observed_at="2026-07-31T00:00:00Z",
            payload_hash=hashlib.sha256(json.dumps(terminal.response, sort_keys=True).encode()).hexdigest(),
            owner_id=owner_id, fence_epoch=fence_epoch,
        )
        return {"action_id": action_id, "terminal_status": "completed", "evidence_class": "real-codex"}
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        store.close()


def _run_codex_action_body(
    action_id: str, domain_path: str, owner_id: str, fence_epoch: int,
    codex_bin: str, schema_root: str, codex_home: str,
    spool_path: str, input_items: list[dict[str, Any]],
    observe_timeout: float = 120.0,
) -> dict[str, Any]:
    return _run_codex_action_common(
        action_id, domain_path, owner_id, fence_epoch, codex_bin, schema_root,
        codex_home, spool_path, input_items, observe_timeout,
        resume_bound_thread=False,
    )


def _run_codex_action_v2_body(
    action_id: str, domain_path: str, owner_id: str, fence_epoch: int,
    codex_bin: str, schema_root: str, codex_home: str,
    spool_path: str, input_items: list[dict[str, Any]],
    observe_timeout: float = 120.0,
    codex_platform: str = "windows-x86_64",
) -> dict[str, Any]:
    from .runtime_pin import verify_runtime_selection

    pin = verify_runtime_selection(
        Path(codex_bin), Path(schema_root), expected_version=PHASE5_CODEX_VERSION,
        expected_platform=codex_platform,
    )
    if not pin["valid"]:
        raise RuntimeError("run_codex_action_v2 runtime pin mismatch")
    return _run_codex_action_common(
        action_id, domain_path, owner_id, fence_epoch, codex_bin, schema_root,
        codex_home, spool_path, input_items, observe_timeout,
        resume_bound_thread=True,
    )


class DBOSBridge:
    """Pinned DBOS adapter. Importing this module does not require DBOS."""

    def __init__(self, runtime_path: Path) -> None:
        from dbos import DBOS

        self.DBOS = DBOS
        self._run_action = DBOS.workflow(name="run_action_v1")(_run_action_body)
        self._run_codex_action = DBOS.workflow(name="run_codex_action_v1")(_run_codex_action_body)
        self._run_codex_action_v2 = DBOS.workflow(name="run_codex_action_v2")(
            _run_codex_action_v2_body
        )
        self._reconcile_job = DBOS.workflow(name="reconcile_job_v1")(_reconcile_body)
        self._project_status = DBOS.workflow(name="project_status_v1")(_reconcile_body)
        self._schedule_job = DBOS.workflow(name="schedule_job_v1")(_schedule_job_body)
        self._cooldown_gate = DBOS.workflow(name="cooldown_gate_v1")(_cooldown_gate_body)
        self._reconcile_gate = DBOS.workflow(name="reconcile_gate_v1")(_reconcile_gate_body)
        self._verify_gate = DBOS.workflow(name="verify_gate_v1")(_verify_gate_body)
        self._review_gate = DBOS.workflow(name="review_gate_v1")(_review_gate_body)
        self._aggregate_release = DBOS.workflow(name="aggregate_release_v1")(_aggregate_release_body)
        DBOS(config={
            "name": "ds-lite-control",
            "system_database_url": sqlite_url(runtime_path),
            "application_version": "ds-lite-phase5-v1",
            "enable_otlp": False,
            "console_log_level": "ERROR",
            "run_admin_server": False,
        })
        DBOS.launch()

    def start_action(self, action_id: str, domain_path: Path, owner_id: str, fence_epoch: int,
                     barrier_path: Path | None = None, delay_seconds: float = 0.0):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._run_action, action_id, str(domain_path.resolve()), owner_id, fence_epoch,
                str(barrier_path.resolve()) if barrier_path is not None else None, delay_seconds,
            )

    def start_codex_action(self, action_id: str, domain_path: Path, owner_id: str, fence_epoch: int,
                           codex_bin: Path, schema_root: Path, codex_home: Path,
                           spool_path: Path, input_items: list[dict[str, Any]],
                           observe_timeout: float = 120.0):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._run_codex_action, action_id, str(domain_path.resolve()), owner_id, fence_epoch,
                str(codex_bin.resolve()), str(schema_root.resolve()), str(codex_home.resolve()),
                str(spool_path.resolve()), input_items, observe_timeout,
            )

    def start_codex_action_v2(
        self, action_id: str, domain_path: Path, owner_id: str, fence_epoch: int,
        codex_bin: Path, schema_root: Path, codex_home: Path,
        spool_path: Path, input_items: list[dict[str, Any]],
        observe_timeout: float = 120.0,
        codex_platform: str = "windows-x86_64",
    ):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._run_codex_action_v2, action_id, str(domain_path.resolve()),
                owner_id, fence_epoch, str(codex_bin.resolve()),
                str(schema_root.resolve()), str(codex_home.resolve()),
                str(spool_path.resolve()), input_items, observe_timeout, codex_platform,
            )

    def start_schedule(
        self, action_id: str, job_id: str, domain_path: Path, owner_id: str,
        *, max_concurrency: int = 2, retry_concurrency: int = 1,
    ):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._schedule_job, job_id, str(domain_path.resolve()), owner_id,
                max_concurrency, retry_concurrency,
            )

    def start_cooldown(
        self, action_id: str, work_item_id: str, domain_path: Path,
        owner_id: str, fence_epoch: int, *, delay_seconds: float,
        barrier_path: Path | None = None,
    ):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._cooldown_gate, work_item_id, str(domain_path.resolve()),
                owner_id, fence_epoch, delay_seconds, None, None,
                str(barrier_path.resolve()) if barrier_path is not None else None,
            )

    def start_reconcile(self, action_id: str, work_item_id: str, domain_path: Path):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._reconcile_gate, work_item_id, str(domain_path.resolve()),
            )

    def start_verify(
        self, action_id: str, work_item_id: str, evidence_set_id: str,
        policy: dict[str, Any], domain_path: Path, receipt_root: Path,
        owner_id: str, fence_epoch: int,
    ):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._verify_gate, work_item_id, evidence_set_id, policy,
                str(domain_path.resolve()), str(receipt_root.resolve()), owner_id, fence_epoch,
            )

    def start_review_reconciliation(self, action_id: str, review_id: str, domain_path: Path):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._review_gate, review_id, str(domain_path.resolve()),
            )

    def start_aggregate(
        self, action_id: str, job_id: str, profile: dict[str, Any],
        domain_path: Path, receipt_root: Path,
    ):
        from dbos import SetWorkflowID

        with SetWorkflowID(action_id):
            return self.DBOS.start_workflow(
                self._aggregate_release, job_id, profile,
                str(domain_path.resolve()), str(receipt_root.resolve()),
            )

    def retrieve(self, workflow_id: str):
        return self.DBOS.retrieve_workflow(workflow_id)

    def close(self) -> None:
        self.DBOS.destroy()
