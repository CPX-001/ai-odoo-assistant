"""Runtime entrypoint for the Assistant Service."""

import os
from collections.abc import Mapping

import uvicorn

HOST_ENV = "ODOO_AI_HOST"
PORT_ENV = "ODOO_AI_PORT"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
_ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def runtime_bind(environ: Mapping[str, str] | None = None) -> tuple[str, int]:
    """Resolve the configured local bind without allowing accidental public exposure."""
    source = os.environ if environ is None else environ
    host = source.get(HOST_ENV, DEFAULT_HOST).strip() or DEFAULT_HOST
    if host not in _ALLOWED_LOOPBACK_HOSTS:
        raise ValueError("Assistant Service host must remain loopback in the MVP profile")

    raw_port = source.get(PORT_ENV, str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError as error:
        raise ValueError("Assistant Service port must be an integer") from error
    if not 1 <= port <= 65535:
        raise ValueError("Assistant Service port must be between 1 and 65535")
    return host, port


def main() -> None:
    """Run the local HTTP service using externally configured bind settings."""
    host, port = runtime_bind()
    uvicorn.run("odoo_ai.api:app", host=host, port=port)


if __name__ == "__main__":
    main()
