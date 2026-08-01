from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "proofreading_queue.py"
spec = importlib.util.spec_from_file_location("proofreading_queue", MODULE_PATH)
assert spec and spec.loader
queue = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = queue
spec.loader.exec_module(queue)


class MemoryKv:
    def __init__(self):
        self.values: dict[str, str] = {}
    def get(self, key: str):
        return self.values.get(key)
    def put(self, key: str, value: str):
        self.values[key] = value
    def delete(self, key: str):
        self.values.pop(key, None)
    def list_keys(self, *, prefix: str, limit: int = 1000, cursor=None):
        return sorted(k for k in self.values if k.startswith(prefix))[:limit], None, True


class ProofreadingQueueTests(unittest.TestCase):
    def make_record(self, status="approved"):
        now = "2026-07-27T00:00:00.000Z"
        return {
            "id": "ps_fixture_1234567890",
            "status": status,
            "updated_at": now,
            "index_key": queue.index_key(status, now, "ps_fixture_1234567890"),
        }

    def test_transition_updates_record_and_index(self):
        client = MemoryKv()
        record = self.make_record()
        client.put(queue.record_key(record["id"]), json.dumps(record))
        client.put(record["index_key"], queue.record_key(record["id"]))
        updated = queue.transition(client, record, "processing", {"processing_error": ""})
        self.assertEqual(updated["status"], "processing")
        self.assertNotIn(record["index_key"], client.values)
        self.assertIn(updated["index_key"], client.values)

    def test_invalid_transition_is_rejected(self):
        client = MemoryKv()
        with self.assertRaises(queue.QueueError):
            queue.transition(client, self.make_record("rejected"), "approved")

    def test_iter_status_ignores_stale_index(self):
        client = MemoryKv()
        record = self.make_record("held")
        raw_key = queue.record_key(record["id"])
        client.put(raw_key, json.dumps(record))
        client.put(queue.index_key("approved", record["updated_at"], record["id"]), raw_key)
        self.assertEqual(list(queue.iter_status_records(client, "approved")), [])


if __name__ == "__main__":
    unittest.main()
