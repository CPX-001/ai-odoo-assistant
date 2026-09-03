"""Provider-neutral response-detail policy for Assistant answers."""

from __future__ import annotations

RESPONSE_DETAIL_LEVELS = frozenset({"concise", "normal", "extensive"})
DEFAULT_RESPONSE_DETAIL = "normal"

_CODEX_VERBOSITY = {
    "concise": "low",
    "normal": "medium",
    "extensive": "high",
}

_PROFILE_INSTRUCTIONS = {
    "concise": (
        "For the same task, be proportionally more compact than the normal profile. Lead with "
        "the conclusion and preserve every fact, piece of evidence, material caveat, required "
        "reasoning step and next action needed to satisfy the request. Remove introductions, "
        "repetition, generic reassurance and optional background first. If the user asks for a "
        "deep or comprehensive analysis, still provide a substantive deep analysis; make it "
        "tighter, never superficial or arbitrarily limited to a few lines."
    ),
    "normal": (
        "Give a balanced, complete answer with the explanation and structure warranted by the "
        "task. Preserve relevant evidence, caveats and next actions without padding or avoidable "
        "repetition."
    ),
    "extensive": (
        "Use the available relevant evidence fully and explain useful connections, reasoning, "
        "caveats and next actions when the task benefits from them. Do not pad, repeat yourself "
        "or lengthen greetings, simple facts or narrow requests merely because this profile "
        "allows more detail."
    ),
}


def codex_verbosity(response_detail: str) -> str:
    """Translate the product preference to Codex's supported verbosity value."""

    try:
        return _CODEX_VERBOSITY[response_detail]
    except KeyError:
        raise ValueError("assistant_response_detail_invalid") from None


def response_detail_instructions(response_detail: str) -> str:
    """Return adaptive host guidance; profiles are not character quotas."""

    if response_detail not in RESPONSE_DETAIL_LEVELS:
        raise ValueError("assistant_response_detail_invalid")
    return (
        "\n\n<response_detail>\n"
        f"The host-selected response detail profile is {response_detail}. This is a flexible "
        "default level of detail, not a character, paragraph, sentence or token quota. Scale the "
        "answer to the task's actual complexity and combine this preference with the user's "
        "explicit request for depth, format and required content. "
        f"{_PROFILE_INSTRUCTIONS[response_detail]}\n"
        "</response_detail>"
    )


__all__ = [
    "DEFAULT_RESPONSE_DETAIL",
    "RESPONSE_DETAIL_LEVELS",
    "codex_verbosity",
    "response_detail_instructions",
]
