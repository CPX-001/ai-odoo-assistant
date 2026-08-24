from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase

from ..services.batch_tools import (
    ATOMIC_CHUNK,
    CONTINUE_ON_ERROR,
    execute_create_chunk,
    execute_delete_chunk,
    execute_uniform_patch_chunk,
)


class _Savepoint:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Cursor:
    def savepoint(self):
        return _Savepoint()


class _Env:
    def __init__(self, model):
        self.cr = _Cursor()
        self._model = model

    def __getitem__(self, model):
        if model != "x.batch.demo":
            raise KeyError(model)
        return self._model


class _Recordset:
    def __init__(self, model, ids):
        self.model = model
        self.ids = [record_id for record_id in ids if record_id in model.records]

    def __len__(self):
        return len(self.ids)

    @property
    def id(self):
        return self.ids[0] if len(self.ids) == 1 else False

    def __iter__(self):
        for record_id in self.ids:
            yield _Recordset(self.model, [record_id])

    def check_access(self, operation):
        del operation
        return True

    def exists(self):
        return _Recordset(self.model, self.ids)

    def write(self, values):
        if any(record_id in self.model.blocked_patch for record_id in self.ids):
            raise ValidationError("blocked patch")
        for record_id in self.ids:
            self.model.records[record_id].update(values)
        return True

    def unlink(self):
        if any(record_id in self.model.blocked_delete for record_id in self.ids):
            raise UserError("blocked delete")
        for record_id in tuple(self.ids):
            self.model.records.pop(record_id, None)
        return True


class _Model:
    def __init__(self):
        self.records = {
            1: {"name": "One", "city": "Old"},
            2: {"name": "Two", "city": "Old"},
            3: {"name": "Three", "city": "Old"},
        }
        self.next_id = 10
        self.blocked_patch = set()
        self.blocked_delete = set()

    def browse(self, ids=None):
        return _Recordset(self, ids or [])

    def create(self, values):
        rows = values if isinstance(values, list) else [values]
        if any(row.get("name") == "BAD" for row in rows):
            raise ValidationError("bad create")
        created_ids = []
        for row in rows:
            self.next_id += 1
            self.records[self.next_id] = dict(row)
            created_ids.append(self.next_id)
        return _Recordset(self, created_ids)


class TestBatchTools(TransactionCase):
    def test_create_falls_back_to_rows_and_keeps_valid_records(self):
        model = _Model()
        results = execute_create_chunk(
            _Env(model),
            model="x.batch.demo",
            rows=(
                ("row:1", {"name": "Alpha"}),
                ("row:2", {"name": "BAD"}),
                ("row:3", {"name": "Gamma"}),
            ),
            failure_mode=CONTINUE_ON_ERROR,
        )

        self.assertEqual([item["state"] for item in results], ["applied", "failed", "applied"])
        self.assertEqual(results[1]["error_code"], "business_rule_rejected")
        self.assertIn("Alpha", {row["name"] for row in model.records.values()})
        self.assertIn("Gamma", {row["name"] for row in model.records.values()})

    def test_patch_falls_back_per_record_after_group_failure(self):
        model = _Model()
        model.blocked_patch.add(2)
        results = execute_uniform_patch_chunk(
            _Env(model),
            model="x.batch.demo",
            rows=(("row:1", 1), ("row:2", 2), ("row:3", 3)),
            values={"city": "Barcelona"},
            failure_mode=CONTINUE_ON_ERROR,
        )

        self.assertEqual([item["state"] for item in results], ["applied", "failed", "applied"])
        self.assertEqual(model.records[1]["city"], "Barcelona")
        self.assertEqual(model.records[2]["city"], "Old")
        self.assertEqual(model.records[3]["city"], "Barcelona")

    def test_delete_falls_back_per_record_after_group_failure(self):
        model = _Model()
        model.blocked_delete.add(2)
        results = execute_delete_chunk(
            _Env(model),
            model="x.batch.demo",
            rows=(("row:1", 1), ("row:2", 2), ("row:3", 3)),
            failure_mode=CONTINUE_ON_ERROR,
        )

        self.assertEqual([item["state"] for item in results], ["applied", "failed", "applied"])
        self.assertNotIn(1, model.records)
        self.assertIn(2, model.records)
        self.assertNotIn(3, model.records)

    def test_atomic_chunk_does_not_fallback_to_valid_rows(self):
        model = _Model()
        model.blocked_delete.add(2)
        results = execute_delete_chunk(
            _Env(model),
            model="x.batch.demo",
            rows=(("row:1", 1), ("row:2", 2), ("row:3", 3)),
            failure_mode=ATOMIC_CHUNK,
        )

        self.assertEqual([item["state"] for item in results], ["failed", "failed", "failed"])
        self.assertEqual(set(model.records), {1, 2, 3})
