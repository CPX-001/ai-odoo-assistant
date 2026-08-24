from odoo.tests.common import TransactionCase

from ..services.batch_preflight import DelegatedBatchPreflightExecutor

SCHEMA_ID = "schema:v1:sha256:" + "a" * 64


class _Recordset:
    def __init__(self, model, ids=()):
        self.model = model
        self.ids = tuple(record_id for record_id in ids if record_id in model.records)

    def __len__(self):
        return len(self.ids)

    def check_access(self, operation):
        self.model.access_checks.append((operation, self.ids))
        return True

    def exists(self):
        return self

    def create(self, values):
        raise AssertionError("preflight must never create")

    def write(self, values):
        raise AssertionError("preflight must never write")

    def unlink(self):
        raise AssertionError("preflight must never unlink")


class _Model:
    def __init__(self, *, records=(), fields=None):
        self.records = set(records)
        self.fields = fields or {}
        self.access_checks = []
        self.field_access_checks = []

    def browse(self, ids=None):
        return _Recordset(self, ids or ())

    def check_field_access_rights(self, operation, fields):
        self.field_access_checks.append((operation, tuple(fields)))
        return True

    def fields_get(self, fields, attributes=None):
        del attributes
        return {field: dict(self.fields[field]) for field in fields if field in self.fields}

    def create(self, values):
        raise AssertionError("preflight must never create")


class _Env:
    def __init__(self, models):
        self.models = models

    def __getitem__(self, model):
        if model not in self.models:
            raise KeyError(model)
        return self.models[model]


class TestBatchPreflight(TransactionCase):
    def test_create_preflight_partitions_relation_rows_without_writes(self):
        target = _Model(
            fields={
                "name": {
                    "type": "char",
                    "readonly": False,
                    "required": True,
                    "relation": False,
                    "selection": False,
                },
                "parent_id": {
                    "type": "many2one",
                    "readonly": False,
                    "required": False,
                    "relation": "res.partner",
                    "selection": False,
                },
            }
        )
        related = _Model(records=(10,))
        env = _Env({"x.batch.demo": target, "res.partner": related})
        batch = {
            "operation": "create",
            "model": "x.batch.demo",
            "schema_id": SCHEMA_ID,
            "failure_mode": "continue_on_error",
            "items": [
                {
                    "operation": "create",
                    "source_ref": "row:1",
                    "values": [
                        {"field": "name", "value": {"kind": "text", "value": "Alpha"}},
                        {"field": "parent_id", "value": {"kind": "many2one", "value": 10}},
                    ],
                },
                {
                    "operation": "create",
                    "source_ref": "row:2",
                    "values": [
                        {"field": "name", "value": {"kind": "text", "value": "Beta"}},
                        {"field": "parent_id", "value": {"kind": "many2one", "value": 999}},
                    ],
                },
            ],
        }

        result = DelegatedBatchPreflightExecutor().preflight(
            env=env,
            batch=batch,
            max_records=50,
        )

        self.assertEqual(result["accepted_source_refs"], ["row:1"])
        self.assertEqual(
            result["issues"],
            [{"source_ref": "row:2", "error_code": "relation_not_found"}],
        )
        self.assertIn(("create", ()), target.access_checks)
        self.assertIn(("read", (10,)), related.access_checks)

    def test_delete_preflight_reports_missing_target_without_unlink(self):
        target = _Model(records=(1,))
        env = _Env({"x.batch.demo": target})
        batch = {
            "operation": "delete",
            "model": "x.batch.demo",
            "schema_id": None,
            "failure_mode": "continue_on_error",
            "items": [
                {"operation": "delete", "source_ref": "row:1", "record_id": 1},
                {"operation": "delete", "source_ref": "row:2", "record_id": 2},
            ],
        }

        result = DelegatedBatchPreflightExecutor().preflight(
            env=env,
            batch=batch,
            max_records=50,
        )

        self.assertEqual(result["accepted_source_refs"], ["row:1"])
        self.assertEqual(
            result["issues"],
            [{"source_ref": "row:2", "error_code": "target_not_found"}],
        )
