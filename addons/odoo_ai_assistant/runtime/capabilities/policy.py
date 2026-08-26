"""Central execution-authority and approval policy for capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityRisk,
)


class ExecutionAuthority(StrEnum):
    REASONING = "reasoning"
    PLAN = "plan"
    HOST = "host"


@dataclass(frozen=True, slots=True)
class CapabilityPolicyDecision:
    allowed: bool
    requires_approval: bool = False
    reason: str = "allowed"


class CapabilityPolicy:
    """Interpret one normalized host-policy snapshot plus capability metadata."""

    def evaluate(
        self,
        definition: CapabilityDefinition,
        context: CapabilityContext,
        *,
        authority: ExecutionAuthority,
        approved: bool = False,
    ) -> CapabilityPolicyDecision:
        if authority.value != definition.exposure.value:
            return CapabilityPolicyDecision(False, reason="capability_authority_mismatch")
        if definition.approval is CapabilityApproval.ALWAYS and not approved:
            return CapabilityPolicyDecision(False, True, "capability_approval_required")
        if definition.approval is CapabilityApproval.POLICY and not approved:
            if self._policy_requires_approval(definition, context):
                return CapabilityPolicyDecision(False, True, "capability_approval_required")
        return CapabilityPolicyDecision(True)

    @staticmethod
    def _policy_requires_approval(
        definition: CapabilityDefinition,
        context: CapabilityContext,
    ) -> bool:
        policy = context.metadata.get("capability_policy")
        if not isinstance(policy, dict):
            # Tests/custom callers that do not carry an Odoo policy snapshot fail closed
            # for effectful plan capabilities while read-only reasoning remains usable.
            return definition.effect is not CapabilityEffect.READ_ONLY
        mode = policy.get("confirmation_mode")
        ceiling = policy.get("max_auto_risk")
        if mode not in {"always_confirm", "risk_based", "protected_only"}:
            return True
        if ceiling not in {"low", "moderate", "high", "protected"}:
            return True
        if mode == "always_confirm":
            return definition.effect is not CapabilityEffect.READ_ONLY
        return _RISK_RANK[_effective_risk(definition)] > _RISK_RANK[ceiling]


_RISK_RANK = {"low": 0, "moderate": 1, "high": 2, "protected": 3}


def _effective_risk(definition: CapabilityDefinition) -> str:
    """Map descriptor metadata to the existing host policy's four stable risk bands."""

    if definition.effect in {
        CapabilityEffect.INTERNAL_IRREVERSIBLE,
        CapabilityEffect.EXTERNAL,
        CapabilityEffect.HOST,
    } or definition.risk is CapabilityRisk.HOST:
        return "protected"
    if definition.risk is CapabilityRisk.ACTION:
        return "high"
    if definition.risk in {CapabilityRisk.WRITE, CapabilityRisk.ACTION_PREVIEW}:
        return "moderate"
    return "low"
