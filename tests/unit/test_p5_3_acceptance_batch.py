from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "p5_3_acceptance_batch.py"
SPEC = importlib.util.spec_from_file_location("p5_3_acceptance_batch", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
BATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BATCH)


def test_parse_odoo_summary_uses_real_odoo_result_shape():
    output = (
        "2026-08-29 00:00:00,000 INFO odoo.tests.result: "
        "0 failed, 0 error(s) of 137 tests when loading database 'odoo_ai_p53'"
    )

    assert BATCH._parse_odoo_summary(output) == {"failed": 0, "errors": 0, "tests": 137}


def test_parse_browser_observation_requires_p5_3_gate_payload():
    output = "\n".join(
        [
            "browser startup",
            '{"gate":"OTHER","result":"PASS"}',
            '{"gate":"P5-REAL-SETTINGS-SNAPSHOT","snapshot_format":1,'
            '"result":"OBSERVED_OK_NOT_AUTOMATIC_PASS"}',
        ]
    )

    observation = BATCH._parse_browser_observation(output)

    assert observation is not None
    assert observation["snapshot_format"] == 1
    assert observation["result"] == "OBSERVED_OK_NOT_AUTOMATIC_PASS"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://127.0.0.1:8069", ("127.0.0.1", 8069)),
        ("http://localhost:8071/", ("127.0.0.1", 8071)),
    ],
)
def test_managed_server_accepts_only_loopback_http_origins(base_url, expected):
    assert BATCH._loopback_server_details(base_url) == expected


def test_managed_server_rejects_remote_origin():
    with pytest.raises(BATCH.BatchError, match="loopback"):
        BATCH._loopback_server_details("http://odoo.example.com:8069")
