"""Durable domain-to-Codex dispatch boundary for Phase 2."""

from __future__ import annotations

from typing import Any

from .app_server import (
    AppServerAdapter,
    AppServerClosed,
    AppServerResponseTimeout,
    RpcObservation,
)
from .store import ControlStore, _canonical_hash


class CodexActionRunner:
    """One action owns one request identity and never retries an ambiguous turn/start."""

    def __init__(self, store: ControlStore, adapter: AppServerAdapter) -> None:
        self.store = store
        self.adapter = adapter

    @staticmethod
    def _stored_observation(request: dict[str, Any]) -> RpcObservation:
        disposition = str(request["state"])
        if disposition == "terminal":
            disposition = "terminal"
        elif disposition not in {"acknowledged", "ambiguous"}:
            disposition = "ambiguous"
        return RpcObservation(
            str(request["method"]), str(request["request_id"]),
            int(request["wire_request_id"] or 0), None,
            request.get("thread_id"), request.get("turn_id"), disposition,
        )

    def dispatch_turn(self, action_id: str, attempt_id: str, input_items: list[dict[str, Any]],
                      owner_id: str, fence_epoch: int, *,
                      model: str | None = None) -> RpcObservation:
        binding = self.store.thread_binding(attempt_id)
        if not binding.get("thread_id"):
            raise ValueError("canonical thread is not bound")
        request_id = f"{action_id}:turn-start"
        params = {"threadId": binding["thread_id"], "input": input_items}
        if model is not None:
            params["model"] = model
        params_hash = _canonical_hash(params)
        request = self.store.plan_rpc_request(
            request_id=request_id, action_id=action_id, method="turn/start",
            params_hash=params_hash, pre_dispatch_turn_id=binding.get("last_turn_id"),
            owner_id=owner_id, fence_epoch=fence_epoch,
        )
        if request["state"] in {"acknowledged", "terminal", "ambiguous"}:
            return self._stored_observation(request)
        wire_request_id = self.adapter.transport.next_request_id
        self.store.transition_rpc_request(
            request_id, "written", owner_id, fence_epoch, wire_request_id=wire_request_id,
        )
        try:
            observation = self.adapter.start_turn(
                binding["thread_id"], input_items, request_id=request_id,
                wire_request_id=wire_request_id, model=model,
            )
        except (AppServerResponseTimeout, AppServerClosed):
            self.store.transition_rpc_request(request_id, "ambiguous", owner_id, fence_epoch)
            return RpcObservation("turn/start", request_id, wire_request_id, None,
                                  binding["thread_id"], None, "ambiguous")
        if observation.turn_id is None:
            self.store.transition_rpc_request(request_id, "ambiguous", owner_id, fence_epoch)
            return RpcObservation("turn/start", request_id, wire_request_id, observation.response,
                                  binding["thread_id"], None, "ambiguous")
        self.store.transition_rpc_request(
            request_id, "acknowledged", owner_id, fence_epoch,
            thread_id=binding["thread_id"], turn_id=observation.turn_id,
        )
        return RpcObservation("turn/start", request_id, wire_request_id, observation.response,
                              binding["thread_id"], observation.turn_id, "acknowledged")

    def reconcile_turn(self, action_id: str, owner_id: str, fence_epoch: int, *,
                       observe_timeout: float = 0.0) -> RpcObservation:
        request = self.store.rpc_request(f"{action_id}:turn-start")
        if request["state"] != "ambiguous":
            return self._stored_observation(request)
        action = self.store.action_context(action_id)
        binding = self.store.thread_binding(action["attempt_id"])
        reconcile_request = getattr(self.adapter, "reconcile_request", None)
        if callable(reconcile_request):
            exact = reconcile_request(str(request["request_id"]), str(binding["thread_id"]))
            if exact.disposition == "acknowledged" and exact.turn_id and observe_timeout > 0:
                observed = self.adapter.observe_turn(
                    str(binding["thread_id"]), exact.turn_id, timeout=observe_timeout,
                )
                if observed.disposition in {"terminal", "failed"}:
                    exact = observed
            if exact.disposition in {"acknowledged", "terminal", "failed"} and exact.turn_id:
                self.store.transition_rpc_request(
                    request["request_id"],
                    "terminal" if exact.disposition == "failed" else exact.disposition,
                    owner_id, fence_epoch,
                    thread_id=binding["thread_id"], turn_id=exact.turn_id,
                )
                return exact
        observations = self.adapter.observed_turns(str(binding["thread_id"]))
        candidates = {observation.turn_id: observation for observation in observations if observation.turn_id}
        if len(candidates) != 1:
            return self._stored_observation(request)
        observation = next(iter(candidates.values()))
        state = "terminal" if observation.disposition in {"terminal", "failed"} else "acknowledged"
        self.store.transition_rpc_request(
            request["request_id"], state, owner_id, fence_epoch,
            thread_id=binding["thread_id"], turn_id=observation.turn_id,
        )
        return observation

    def dispatch_archive(self, action_id: str, attempt_id: str,
                         owner_id: str, fence_epoch: int) -> RpcObservation:
        binding = self.store.thread_binding(attempt_id)
        thread_id = str(binding.get("thread_id") or "")
        if not thread_id:
            raise ValueError("canonical thread is not bound")
        request_id = f"{action_id}:thread-archive"
        request = self.store.plan_rpc_request(
            request_id=request_id, action_id=action_id, method="thread/archive",
            params_hash=_canonical_hash({"threadId": thread_id}),
            pre_dispatch_turn_id=binding.get("last_turn_id"),
            owner_id=owner_id, fence_epoch=fence_epoch,
        )
        if request["state"] in {"acknowledged", "terminal", "ambiguous"}:
            return self._stored_observation(request)
        self.store.set_thread_archive_pending(attempt_id, True, owner_id, fence_epoch)
        wire_id = self.adapter.transport.next_request_id
        self.store.transition_rpc_request(
            request_id, "written", owner_id, fence_epoch, wire_request_id=wire_id,
            thread_id=thread_id,
        )
        try:
            observation = self.adapter.archive_thread(thread_id, request_id=request_id)
        except (AppServerResponseTimeout, AppServerClosed):
            self.store.transition_rpc_request(request_id, "ambiguous", owner_id, fence_epoch)
            return RpcObservation("thread/archive", request_id, wire_id, None,
                                  thread_id, None, "ambiguous")
        self.store.transition_rpc_request(
            request_id, "acknowledged", owner_id, fence_epoch, thread_id=thread_id,
        )
        return RpcObservation("thread/archive", request_id, wire_id, observation.response,
                              thread_id, None, "acknowledged")

    def reconcile_archive(self, action_id: str, attempt_id: str,
                          owner_id: str, fence_epoch: int) -> RpcObservation:
        request = self.store.rpc_request(f"{action_id}:thread-archive")
        if request["state"] == "terminal":
            return self._stored_observation(request)
        binding = self.store.thread_binding(attempt_id)
        reconcile = getattr(self.adapter, "reconcile_archive", None)
        if not callable(reconcile):
            return self._stored_observation(request)
        observation = reconcile(str(request["request_id"]), str(binding["thread_id"]))
        if observation.disposition == "terminal":
            self.store.transition_rpc_request(
                request["request_id"], "terminal", owner_id, fence_epoch,
                thread_id=binding["thread_id"],
            )
            self.store.complete_thread_archive(attempt_id, owner_id, fence_epoch)
        return observation
