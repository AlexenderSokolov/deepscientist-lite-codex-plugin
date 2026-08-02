"""Deterministic fake app-server for Phase 0.5 protocol faults only."""

from __future__ import annotations


class FakeAppServer:
    def __init__(self) -> None:
        self.threads: dict[str, str] = {}
        self.start_count = 0

    def resume_or_classify(self, thread_id: str) -> dict[str, str]:
        state = self.threads.get(thread_id)
        if state in {"active", "terminal"}:
            return {"state": state, "thread_id": thread_id}
        return {"state": "ambiguous", "thread_id": thread_id}

    def observe_notification(self, thread_id: str, terminal: bool = False) -> dict[str, str]:
        self.threads[thread_id] = "terminal" if terminal else "active"
        return self.resume_or_classify(thread_id)

    def dispatch_acknowledged_then_lost(self, thread_id: str) -> dict[str, str]:
        self.threads.pop(thread_id, None)
        return {"state": "ambiguous", "thread_id": thread_id}

