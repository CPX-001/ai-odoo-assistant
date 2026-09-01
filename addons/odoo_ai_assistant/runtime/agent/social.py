"""Bounded provider-free answers for exact social messages."""

from __future__ import annotations

import re

_GREETING = re.compile(
    r"^[.!¡?¿ ]*(?:hola|hello|hi|hey|buenos d[ií]as|buenas tardes|buenas noches)"
    r"(?:[,.!¡?¿ ]*(?:qu[eé] tal|c[oó]mo est[aá]s|how are you))?[,.!¡?¿ ]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"^[.!¡?¿ ]*(?:gracias|muchas gracias|thanks|thank you)[,.!¡?¿ ]*$",
    re.IGNORECASE,
)
_FAREWELL = re.compile(
    r"^[.!¡?¿ ]*(?:adi[oó]s|hasta luego|bye|goodbye|see you)[,.!¡?¿ ]*$",
    re.IGNORECASE,
)
_ENGLISH_TOKEN = re.compile(
    r"\b(?:hello|hi|hey|how are you|thanks|thank you|bye|goodbye|see you)\b",
    re.IGNORECASE,
)


def simple_social_answer(message: object, *, lang: object = None) -> str | None:
    """Return a local answer only for a closed exact social utterance."""

    if (
        not isinstance(message, str)
        or not 1 <= len(message.strip()) <= 80
        or "\x00" in message
    ):
        return None
    normalized = " ".join(message.split())
    english = bool(_ENGLISH_TOKEN.search(normalized)) or (
        isinstance(lang, str)
        and lang.lower().startswith("en")
        and not _has_spanish_token(normalized)
    )
    if _GREETING.fullmatch(normalized):
        return "Hello! How can I help?" if english else "¡Hola! ¿En qué puedo ayudarte?"
    if _THANKS.fullmatch(normalized):
        return (
            "You're welcome! Is there anything else I can help with?"
            if english
            else "¡De nada! ¿Necesitas algo más?"
        )
    if _FAREWELL.fullmatch(normalized):
        return "Goodbye!" if english else "¡Hasta luego!"
    return None


def is_simple_social_message(message: object) -> bool:
    return simple_social_answer(message) is not None


def _has_spanish_token(message: str) -> bool:
    return bool(
        re.search(
            r"\b(?:hola|buenos|buenas|qu[eé] tal|c[oó]mo est[aá]s|gracias|adi[oó]s|hasta luego)\b",
            message,
            re.IGNORECASE,
        )
    )
