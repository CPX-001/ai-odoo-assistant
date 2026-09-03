"""Host-owned projection of verified but incomplete business outcomes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_BUSINESS_OUTCOMES = frozenset({"completed", "partial", "blocked"})
_INCOMPLETE_OUTCOMES = frozenset({"partial", "blocked"})
_COUNT_FIELDS = ("count", "requested_count", "failed_count", "excluded_count")


def incomplete_effect_summary(steps) -> dict[str, object] | None:
    """Return exact aggregate counts when any verified step is partial or blocked.

    The projection is capability-neutral: providers opt into it through the complete
    structural ``outcome`` + exact-count contract rather than through a capability-name
    branch.  A coincidental or malformed ``outcome`` field is ignored, so arbitrary
    capability payloads cannot change the host's completion semantics.
    """

    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes, bytearray)):
        return None
    incomplete_outcomes = []
    counted_results = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        normalized = normalized_business_outcome(step.get("result"))
        if normalized is None:
            continue
        outcome = normalized["outcome"]
        if outcome in _INCOMPLETE_OUTCOMES:
            incomplete_outcomes.append(outcome)
            counted_results.append(
                (outcome, {key: normalized[key] for key in _COUNT_FIELDS})
            )
    if not incomplete_outcomes:
        return None

    aggregate_outcome = (
        "partial"
        if "partial" in incomplete_outcomes
        or any(counts["count"] > 0 for _outcome, counts in counted_results)
        else "blocked"
    )
    summary: dict[str, object] = {"outcome": aggregate_outcome}
    if counted_results:
        for key in _COUNT_FIELDS:
            summary[key] = sum(counts[key] for _outcome, counts in counted_results)
    return summary


def normalized_business_outcome(result) -> dict[str, object] | None:
    """Validate and normalize the common exact business-outcome result contract."""

    if not isinstance(result, Mapping):
        return None
    outcome = result.get("outcome")
    if outcome not in _BUSINESS_OUTCOMES:
        return None
    counts = _exact_counts(result)
    if counts is None:
        return None
    return {"outcome": outcome, **counts}


def incomplete_effect_answer(summary, *, spanish: bool) -> str:
    """Format a conservative fallback without turning verification into full success."""

    counts = _summary_counts(summary)
    if counts is not None:
        applied = counts["count"]
        requested = counts["requested_count"]
        failed = counts["failed_count"]
        excluded = counts["excluded_count"]
        blocked = isinstance(summary, Mapping) and summary.get("outcome") == "blocked"
        if blocked:
            if spanish:
                return (
                    "El resultado quedó verificado: no se pudo aplicar la operación a "
                    f"ninguno de los {requested} registros; {failed} fallaron y "
                    f"{excluded} quedaron excluidos."
                )
            return (
                "The result was verified: the operation could not be applied to any of "
                f"the {requested} records; {failed} failed and {excluded} were excluded."
            )
        if spanish:
            return (
                "El resultado quedó verificado, pero la operación fue parcial: "
                f"se aplicó a {applied} de {requested} registros; {failed} fallaron y "
                f"{excluded} quedaron excluidos."
            )
        return (
            "The result was verified, but the operation was partial: "
            f"it applied to {applied} of {requested} records; {failed} failed and "
            f"{excluded} were excluded."
        )

    blocked = isinstance(summary, Mapping) and summary.get("outcome") == "blocked"
    if spanish:
        return (
            "El resultado quedó verificado, pero la operación quedó bloqueada y no se "
            "aplicó por completo."
            if blocked
            else "El resultado quedó verificado, pero la operación solo se aplicó parcialmente."
        )
    return (
        "The result was verified, but the operation was blocked and was not fully applied."
        if blocked
        else "The result was verified, but the operation was only partially applied."
    )


def _exact_counts(result):
    counts = {}
    for key in _COUNT_FIELDS:
        value = result.get(key)
        if type(value) is not int or value < 0:
            return None
        counts[key] = value
    if counts["requested_count"] <= 0:
        return None
    if (
        counts["count"] + counts["failed_count"] + counts["excluded_count"]
        != counts["requested_count"]
    ):
        return None
    return counts


def _summary_counts(summary):
    if not isinstance(summary, Mapping):
        return None
    return _exact_counts(summary)
