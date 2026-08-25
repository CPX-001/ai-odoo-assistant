"""Central execution-authority and approval policy for capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityRisk,
)


class ExecutionAuthority(str, Enum):
    REASONING = "reasoning"
    PLAN = "plan"
    HOST = "host"


@dataclass(frozen=True, slots=True)
class CapabilityPolicyDecision:
    allowed: bool
    requires_approval: bool = False
    reason: str = "allowed"


class CapabilityPolicy:
    """Default host policy; deployments may compose stricter checks around it."""

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
        autonomy = context.metadata.get("autonomy", "balanced")
        if autonomy == "full_access":
            return False
        if autonomy == "strict":
            return definition.risk not in {CapabilityRisk.METADATA, CapabilityRisk.READ}
        if autonomy == "autonomous":
            return definition.risk is CapabilityRisk.HOST
        return definition.risk in {CapabilityRisk.ACTION, CapabilityRisk.HOST}
