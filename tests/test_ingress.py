import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
HANDLER_PATH = ROOT / "infra-tf" / "code" / "ingress" / "handler.py"


class BotoCoreError(Exception):
    pass


class ClientError(Exception):
    def __init__(self, message="client error", code=None):
        super().__init__(message)
        self.response = {"Error": {"Code": code or "Unknown"}}


class FakeSQS:
    def __init__(self):
        self.messages = []
        self.fail = False

    def send_message(self, **kwargs):
        if self.fail:
            raise ClientError("send failed")
        self.messages.append(kwargs)
        return {"MessageId": "test-message"}


fake_sqs = FakeSQS()
fake_clients = {"sqs": fake_sqs}
os.environ.setdefault("QUEUE_URL", "https://example.test/queue")
boto3 = types.ModuleType("boto3")
boto3.client = lambda service: fake_clients[service]
botocore = types.ModuleType("botocore")
exceptions = types.ModuleType("botocore.exceptions")
exceptions.BotoCoreError = BotoCoreError
exceptions.ClientError = ClientError
sys.modules["boto3"] = boto3
sys.modules["botocore"] = botocore
sys.modules["botocore.exceptions"] = exceptions

spec = importlib.util.spec_from_file_location("ingress_handler", HANDLER_PATH)
handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler)


class IngressHandlerTests(unittest.TestCase):
    def setUp(self):
        fake_sqs.messages.clear()
        fake_sqs.fail = False
        handler.MAX_BODY_BYTES = 65536
        handler.MAX_SQS_MESSAGE_BYTES = 262144

    def event(self, path="/capture", body='{"message":"hello"}', headers=None):
        return {
            "version": "2.0",
            "rawPath": path,
            "headers": headers or {"content-type": "application/json"},
            "queryStringParameters": {"page": "1"},
            "body": body,
            "isBase64Encoded": False,
            "requestContext": {
                "requestId": "test-request-id",
                "http": {"method": "POST"},
            },
        }

    def invoke(self, event):
        return handler.lambda_handler(event, SimpleNamespace(aws_request_id="fallback-id"))

    def capture(self):
        return json.loads(fake_sqs.messages[0]["MessageBody"])

    def test_valid_request_is_accepted_and_sensitive_values_are_redacted(self):
        event = self.event(
            headers={"authorization": "Bearer hidden", "content-type": "application/json"},
            body='{"name":"sample","api_key":"hidden"}',
        )
        result = self.invoke(event)
        self.assertEqual(result["statusCode"], 202)
        record = self.capture()
        self.assertEqual(record["path"], "/capture")
        self.assertEqual(record["queryParameters"], {"page": "1"})
        self.assertEqual(record["headers"]["authorization"], "[REDACTED]")
        self.assertEqual(record["requestBody"]["api_key"], "[REDACTED]")
        self.assertEqual(record["response"]["statusCode"], 202)
        self.assertEqual(record["outcome"], "accepted")
        self.assertIn("timestamp", record)

    def test_inline_secret_patterns_in_string_values_are_redacted(self):
        result = self.invoke(self.event(body='{"note":"password=hiddenvalue"}'))
        self.assertEqual(result["statusCode"], 202)
        message = fake_sqs.messages[0]["MessageBody"]
        self.assertNotIn("hiddenvalue", message)
        self.assertIn("[REDACTED]", message)

    def test_unknown_path_is_captured_as_rejected(self):
        result = self.invoke(self.event(path="/admin"))
        self.assertEqual(result["statusCode"], 404)
        self.assertEqual(self.capture()["outcome"], "rejected")

    def test_invalid_json_is_rejected_without_retaining_raw_body(self):
        result = self.invoke(self.event(body='{"password":"do-not-store"'))
        self.assertEqual(result["statusCode"], 400)
        message = fake_sqs.messages[0]["MessageBody"]
        self.assertNotIn("do-not-store", message)
        self.assertEqual(self.capture()["outcome"], "rejected")

    def test_json_scalar_is_rejected_without_storing_scalar_text(self):
        result = self.invoke(self.event(body='"password=do-not-store"'))
        self.assertEqual(result["statusCode"], 400)
        message = fake_sqs.messages[0]["MessageBody"]
        self.assertNotIn("do-not-store", message)

    def test_oversized_body_is_rejected_and_omitted(self):
        handler.MAX_BODY_BYTES = 4
        result = self.invoke(self.event(body='{"ok":true}'))
        self.assertEqual(result["statusCode"], 413)
        self.assertIn("omitted", self.capture()["requestBody"])

    def test_capture_record_over_sqs_limit_is_rejected_and_compacted(self):
        handler.MAX_SQS_MESSAGE_BYTES = 2048
        event = self.event(headers={"x-large-header": "x" * 5000})
        result = self.invoke(event)
        self.assertEqual(result["statusCode"], 413)
        message = fake_sqs.messages[0]["MessageBody"]
        self.assertLessEqual(len(message.encode("utf-8")), handler.MAX_SQS_MESSAGE_BYTES)
        record = json.loads(message)
        self.assertEqual(record["outcome"], "rejected")
        self.assertEqual(record["response"]["statusCode"], 413)
        self.assertIn("omitted", record["headers"])

    def test_queue_failure_returns_503(self):
        fake_sqs.fail = True
        result = self.invoke(self.event())
        self.assertEqual(result["statusCode"], 503)
        self.assertEqual(fake_sqs.messages, [])


if __name__ == "__main__":
    unittest.main()
