from unittest.mock import patch

import pytest

from odoo_ai.api.__main__ import DEFAULT_HOST, DEFAULT_PORT, main, runtime_bind


def test_runtime_bind_defaults_to_loopback() -> None:
    assert runtime_bind({}) == (DEFAULT_HOST, DEFAULT_PORT)


def test_runtime_bind_accepts_configured_loopback_port() -> None:
    assert runtime_bind({"ODOO_AI_HOST": "::1", "ODOO_AI_PORT": "8123"}) == ("::1", 8123)


def test_runtime_bind_rejects_public_bind() -> None:
    with pytest.raises(ValueError, match="loopback"):
        runtime_bind({"ODOO_AI_HOST": "0.0.0.0"})


def test_entrypoint_uses_runtime_configuration() -> None:
    with (
        patch.dict("os.environ", {"ODOO_AI_HOST": "localhost", "ODOO_AI_PORT": "8124"}, clear=True),
        patch("odoo_ai.api.__main__.uvicorn.run") as run,
    ):
        main()

    run.assert_called_once_with("odoo_ai.api:app", host="localhost", port=8124)
