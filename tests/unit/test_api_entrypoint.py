from unittest.mock import patch

from odoo_ai.api.__main__ import DEV_HOST, DEV_PORT, main


def test_dev_entrypoint_binds_to_loopback() -> None:
    with patch("odoo_ai.api.__main__.uvicorn.run") as run:
        main()

    run.assert_called_once_with("odoo_ai.api:app", host=DEV_HOST, port=DEV_PORT)
    assert DEV_HOST == "127.0.0.1"
    assert DEV_PORT == 8000
