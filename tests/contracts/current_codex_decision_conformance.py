"""Dependency-light binding of the current CodexDecisionEngine to the Phase 1 v2 harness.

This adapter intentionally observes committed source contracts. It does not pretend to be a live
Codex App Server probe; real protocol behavior remains covered by the Phase 1 real-environment debt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class CurrentCodexDecisionConformanceAdapter:
    """Return sanitized observations for the current custom decision adapter."""

    def __init__(self, repo_root: Path) -> None:
        self._decision = (
            repo_root / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "codex_decision.py"
        ).read_text(encoding="utf-8")
        self._codex = (
            repo_root / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "codex.py"
        ).read_text(encoding="utf-8")
        self._contracts = (
            repo_root / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "contracts.py"
        ).read_text(encoding="utf-8")

    def _decision_kind_is_decoded(self, kind: str, result_type: str) -> bool:
        return all(
            (
                "return parse_next_decision(" in self._decision,
                f'if kind == "{kind}":' in self._contracts,
                f"return {result_type}(" in self._contracts,
            )
        )

    async def observe(self, case: dict[str, Any]) -> dict[str, Any]:
        case_id = case["id"]
        observation = getattr(self, f"_observe_{case_id}")()
        return {
            "outcome": observation[0],
            "assertions": observation[1],
        }

    def _observe_initialize(self):
        ok = all(
            token in self._codex
            for token in (
                'client.request(\n                "initialize"',
                'await client.notify("initialized"',
                '"codex_initialize_response_invalid"',
            )
        )
        return ("accepted" if ok else "rejected", {"initialized": ok})

    def _observe_thread_isolation(self):
        checks = {
            "approval_never": '"approvalPolicy": "never"' in self._decision,
            "sandbox_read_only": '"sandbox": "read-only"' in self._decision,
            "ephemeral_thread": '"ephemeral": True' in self._decision,
            "workspace_roots_empty": '"runtimeWorkspaceRoots": []' in self._decision,
        }
        return ("accepted" if all(checks.values()) else "rejected", checks)

    def _observe_turn_output_schema(self):
        checks = {
            "output_schema_present": all(
                token in self._decision
                for token in (
                    '"outputSchema": _codex_next_decision_schema(',
                    "final_answer_only=final_answer_only",
                )
            ),
            "one_decision_envelope": '"properties": {"decision": {"anyOf": wire_alternatives}}' in self._decision,
        }
        return ("accepted" if all(checks.values()) else "rejected", checks)

    def _observe_agent_message_delta(self):
        ok = '"item/agentMessage/"' in self._codex and "_validate_decision_notification" in self._decision
        return ("accepted" if ok else "rejected", {"delta_accepted": ok})

    def _observe_completed_agent_message(self):
        ok = all(
            token in self._decision
            for token in (
                'if method == "item/completed"',
                'if item.get("type") == "agentMessage"',
                "completed_agent_messages.append(item)",
            )
        )
        return ("accepted" if ok else "rejected", {"completed_message_accepted": ok})

    def _observe_reasoning_decision_mapping(self):
        decoded = (
            self._decision_kind_is_decoded(
                "reasoning_capability_call",
                "ReasoningCapabilityCall",
            )
            and "return validate_next_decision(" in self._decision
        )
        host_owned = "executor.execute" not in self._decision
        checks = {
            "reasoning_decision_decoded": decoded,
            "host_executor_remains_authoritative": host_owned,
        }
        return ("accepted" if all(checks.values()) else "rejected", checks)

    def _observe_plan_decision_mapping(self):
        decoded = self._decision_kind_is_decoded("plan_step_proposal", "PlanStepProposal")
        stage_only = "executor.execute" not in self._decision
        checks = {
            "plan_proposal_decoded": decoded,
            "stage_only": stage_only,
            "host_action_lifecycle_preserved": stage_only,
        }
        return ("accepted" if all(checks.values()) else "rejected", checks)

    def _observe_final_answer_mapping(self):
        decoded = self._decision_kind_is_decoded("final_answer", "FinalAnswer")
        no_effect = "executor.execute" not in self._decision
        checks = {"final_answer_decoded": decoded, "no_host_effect": no_effect}
        return ("accepted" if all(checks.values()) else "rejected", checks)

    def _observe_unknown_notification(self):
        tolerant = all(
            token in self._decision
            for token in (
                "def _validate_decision_notification(",
                'if error.code != "codex_event_not_allowed":',
                'if "threadId" in params',
                'if "turnId" in params',
                'if "callId" in params:',
                'raise CodexAgentError("codex_event_identity_mismatch")',
                'raise CodexAgentError("codex_event_identity_unverified")',
            )
        )
        return (
            "accepted" if tolerant else "rejected",
            {"unknown_notification_ignored_safely": tolerant},
        )

    def _observe_malformed_critical_event(self):
        closed = all(
            token in self._decision
            for token in (
                'raise CodexAgentError("codex_event_invalid")',
                'raise CodexAgentError("codex_turn_completion_mismatch")',
            )
        )
        return ("rejected", {"failed_closed": closed})

    def _observe_identity_mismatch(self):
        closed = all(
            token in self._decision
            for token in (
                'params.get("threadId") != thread_id',
                'turn.get("id") != turn_id',
                'raise CodexAgentError("codex_turn_completion_mismatch")',
            )
        )
        return ("rejected", {"failed_closed": closed})

    def _observe_cancellation(self):
        correct = all(
            token in self._decision
            for token in (
                "await _best_effort_interrupt(client, thread_id, turn_id)",
                'raise CodexAgentError("agent_cancelled")',
            )
        )
        return ("cancelled" if correct else "rejected", {"correct_turn_interrupted": correct})

    def _observe_terminal_failure(self):
        structured = all(
            token in self._decision
            for token in (
                "class CodexProviderFailure:",
                "class CodexDecisionError(CodexAgentError):",
                "self.provider_failure = provider_failure",
                "def _provider_failure_details(",
                '"codexErrorInfo"',
                '"httpStatusCode"',
                "upstream_code",
                "return CodexDecisionError(",
                "provider_failure=provider_failure",
            )
        ) and self._decision.count("raise _decision_terminal_error(") >= 2
        return ("rejected", {"structured_error_preserved": structured})

    def _observe_overload_backpressure(self):
        classification = all(
            token in self._decision
            for token in (
                '_RETRYABLE_PROVIDER_CATEGORIES = frozenset({"serverOverloaded"})',
                "def _provider_failure_is_backpressure(",
                "provider_retryable=provider_retryable",
            )
        )
        effect_gate = self._decision.count("host_effect_safe=True") >= 2
        host_effect_absent = "executor.execute" not in self._decision
        retryable = classification and effect_gate and host_effect_absent
        return (
            "retryable" if retryable else "rejected",
            {
                "retryable_classified": retryable,
                "unsafe_host_effect_not_retried": host_effect_absent and effect_gate,
            },
        )
