import importlib.util
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from test_ingress import ClientError, fake_clients

ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "infra-tf" / "code" / "worker" / "handler.py"
os.environ.setdefault("CAPTURE_BUCKET", "test-captures")


class FakeS3:
    def __init__(self):
        self.objects = []
        self.fail = False
        self.error_code = "AccessDenied"

    def put_object(self, **kwargs):
        if self.fail:
            raise ClientError("put failed", self.error_code)
        self.objects.append(kwargs)
        return {"ETag": '"test"'}


fake_s3 = FakeS3()
fake_clients["s3"] = fake_s3

spec = importlib.util.spec_from_file_location("worker_handler", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        fake_s3.objects.clear()
        fake_s3.fail = False
        fake_s3.error_code = "AccessDenied"

    def record(self, outcome="accepted"):
        return {
            "requestId": "request-123",
            "timestamp": datetime(2026, 10, 15, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "outcome": outcome,
            "path": "/capture",
            "response": {"statusCode": 202},
        }

    def event(self, record):
        return {"Records": [{"messageId": "message-1", "body": json.dumps(record)}]}

    def test_accepted_record_is_written_to_accepted_prefix(self):
        result = worker.lambda_handler(self.event(self.record()), None)
        self.assertEqual(result["batchItemFailures"], [])
        self.assertTrue(fake_s3.objects[0]["Key"].startswith("accepted/2026/10/15/"))
        self.assertEqual(fake_s3.objects[0]["IfNoneMatch"], "*")

    def test_rejected_record_is_written_to_rejected_prefix(self):
        result = worker.lambda_handler(self.event(self.record("rejected")), None)
        self.assertEqual(result["batchItemFailures"], [])
        self.assertTrue(fake_s3.objects[0]["Key"].startswith("rejected/2026/10/15/"))

    def test_duplicate_object_is_treated_as_success(self):
        fake_s3.fail = True
        fake_s3.error_code = "PreconditionFailed"
        result = worker.lambda_handler(self.event(self.record()), None)
        self.assertEqual(result["batchItemFailures"], [])

    def test_s3_failure_returns_message_for_retry(self):
        fake_s3.fail = True
        result = worker.lambda_handler(self.event(self.record()), None)
        self.assertEqual(result["batchItemFailures"], [{"itemIdentifier": "message-1"}])


if __name__ == "__main__":
    unittest.main()
