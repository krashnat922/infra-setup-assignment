import base64
import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", "65536"))
MAX_SQS_MESSAGE_BYTES = int(os.environ.get("MAX_SQS_MESSAGE_BYTES", "262144"))
REDACT = "[REDACTED]"
SENSITIVE_PARTS = (
    "authorization", "cookie", "token", "secret", "password", "api_key",
    "api-key", "credential", "private_key", "private-key",
)
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
SECRET_TEXT_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|client[_-]?secret)\b\s*[:=]\s*([^,\s;\"}]+)"
)


def is_sensitive(name):
    name = str(name).lower().replace("-", "_")
    return any(part.replace("-", "_") in name for part in SENSITIVE_PARTS)


def redact(value):
    if isinstance(value, dict):
        return {key: REDACT if is_sensitive(key) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = BEARER_PATTERN.sub("Bearer [REDACTED]", value)
        return SECRET_TEXT_PATTERN.sub(r"\1=[REDACTED]", value)
    return value


def response(status, request_id, message):
    body = {"requestId": request_id, "status": message}
    if status >= 400:
        body = {"requestId": request_id, "error": message}
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def lambda_handler(event, context):
    request_context = event.get("requestContext", {})
    request_id = request_context.get("requestId") or context.aws_request_id
    http = request_context.get("http", {})
    method = (http.get("method") or event.get("httpMethod") or "POST").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    headers = redact(event.get("headers") or {})
    query = redact(event.get("queryStringParameters") or {})
    raw_body = event.get("body") or ""
    body_value = "[omitted: invalid JSON]"
    body_parse_error = False
    body_too_large = False

    try:
        raw_bytes = base64.b64decode(raw_body) if event.get("isBase64Encoded") else raw_body.encode("utf-8")
        if len(raw_bytes) > MAX_BODY_BYTES:
            body_too_large = True
            body_value = "[omitted: body exceeds configured limit]"
        elif raw_bytes:
            body_value = redact(json.loads(raw_bytes.decode("utf-8")))
        else:
            body_value = None
            body_parse_error = True
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        body_parse_error = True

    if not body_parse_error and not body_too_large and not isinstance(body_value, (dict, list)):
        body_value = "[omitted: JSON body must be an object or array]"
        body_parse_error = True

    if method != "POST":
        result = response(405, request_id, "method_not_allowed")
    elif path != "/capture":
        result = response(404, request_id, "not_found")
    elif body_too_large:
        result = response(413, request_id, "request_body_too_large")
    elif body_parse_error or not isinstance(body_value, (dict, list)):
        result = response(400, request_id, "invalid_json_body")
    else:
        result = response(202, request_id, "accepted")

    outcome = "accepted" if result["statusCode"] == 202 else "rejected"
    record = {
        "schemaVersion": 1,
        "requestId": request_id,
        "timestamp": timestamp,
        "method": method,
        "path": path,
        "queryParameters": query,
        "headers": headers,
        "requestBody": body_value,
        "response": result,
        "outcome": outcome,
    }
    message = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    if len(message.encode("utf-8")) > MAX_SQS_MESSAGE_BYTES:
        result = response(413, request_id, "capture_record_too_large")
        record["response"] = result
        record["outcome"] = "rejected"
        record["requestBody"] = "[omitted: capture record exceeds SQS message limit]"
        message = json.dumps(record, separators=(",", ":"), ensure_ascii=False)

        if len(message.encode("utf-8")) > MAX_SQS_MESSAGE_BYTES:
            marker = "[omitted: capture record exceeds SQS message limit]"
            record["headers"] = marker
            record["queryParameters"] = marker
            record["path"] = path[:2048]
            message = json.dumps(record, separators=(",", ":"), ensure_ascii=False)

        if len(message.encode("utf-8")) > MAX_SQS_MESSAGE_BYTES:
            logger.error("Capture record exceeds queue limit requestId=%s", request_id)
            return response(503, request_id, "capture_unavailable")

    try:
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=message)
    except (BotoCoreError, ClientError) as exc:
        logger.error("Queue handoff failed for requestId=%s errorType=%s", request_id, type(exc).__name__)
        return response(503, request_id, "capture_unavailable")

    logger.info("Capture queued requestId=%s outcome=%s responseStatus=%s", request_id, outcome, result["statusCode"])
    return result
