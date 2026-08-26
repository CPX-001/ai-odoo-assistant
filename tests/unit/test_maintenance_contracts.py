from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from odoo_ai.contracts.maintenance import (
    MaintenanceActor,
    MaintenanceJob,
    MaintenanceMetrics,
    MaintenanceRequest,
    MaintenanceResult,
)


def test_maintenance_request_is_closed_and_actor_is_bounded() -> None:
    actor = MaintenanceActor(odoo_uid=4, odoo_database="odoo-test")
    assert MaintenanceRequest(actor=actor).actor == actor

    with pytest.raises(ValidationError):
        MaintenanceRequest.model_validate(
            {
                "actor": {"odoo_uid": 4, "odoo_database": "odoo-test"},
                "operation": "shell",
            }
        )
    with pytest.raises(ValidationError):
        MaintenanceActor(odoo_uid=0, odoo_database="odoo-test")
    with pytest.raises(ValidationError):
        MaintenanceActor(odoo_uid=4, odoo_database="bad\nname")


def test_result_codes_and_metrics_reject_unbounded_shapes() -> None:
    result = MaintenanceResult(
        operation="logs_test",
        state="succeeded",
        result_code="logs_test_succeeded",
        checked_at=datetime.now(UTC),
        metrics=MaintenanceMetrics(log_matches=3),
    )
    assert result.metrics.log_matches == 3

    with pytest.raises(ValidationError):
        MaintenanceResult.model_validate(
            {
                "operation": "logs_test",
                "state": "succeeded",
                "result_code": "run_arbitrary_command",
                "checked_at": datetime.now(UTC).isoformat(),
            }
        )
    with pytest.raises(ValidationError):
        MaintenanceMetrics.model_validate({"log_matches": 21})
    with pytest.raises(ValidationError):
        MaintenanceMetrics.model_validate({"secret": "canary"})


def test_only_long_running_allowlisted_operations_can_be_jobs() -> None:
    job = MaintenanceJob(
        job_id=uuid4(),
        operation="knowledge_reindex",
        state="queued",
        created_at=datetime.now(UTC),
    )
    assert job.operation == "knowledge_reindex"

    with pytest.raises(ValidationError):
        MaintenanceJob.model_validate(
            {
                "job_id": str(uuid4()),
                "operation": "reasoning_test",
                "state": "queued",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
