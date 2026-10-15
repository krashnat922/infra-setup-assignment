import json
import logging
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)
s3 = boto3.client("s3")
BUCKET = os.environ["CAPTURE_BUCKET"]


def lambda_handler(event, context):
    failures = []
    for message in event.get("Records", []):
        message_id = message["messageId"]
        try:
            record = json.loads(message["body"])
            timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
            outcome = "accepted" if record.get("outcome") == "accepted" else "rejected"
            request_id = str(record["requestId"])
            key = f"{outcome}/{timestamp:%Y/%m/%d}/{request_id}.json"
            s3.put_object(
                Bucket=BUCKET,
                Key=key,
                Body=json.dumps(record, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
            logger.info("Capture persisted requestId=%s outcome=%s", request_id, outcome)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            if code in ("PreconditionFailed", "412"):
                continue
            logger.error("Capture persistence failed messageId=%s errorCode=%s", message_id, code)
            failures.append({"itemIdentifier": message_id})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Capture message invalid messageId=%s errorType=%s", message_id, type(exc).__name__)
            failures.append({"itemIdentifier": message_id})
        except Exception as exc:
            logger.error("Capture persistence failed messageId=%s errorType=%s", message_id, type(exc).__name__)
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
