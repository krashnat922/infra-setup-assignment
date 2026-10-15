# AWS Asynchronous Request Capture

Terraform-managed AWS infrastructure that captures HTTP POST requests and stores their records in S3 asynchronously.

## Architecture

```text
Client
  |
  v
API Gateway HTTP API
  |
  v
Ingress Lambda
  |
  v
SQS capture queue -----> Dead-letter queue after repeated failures
  |
  v
Worker Lambda
  |
  v
S3 bucket
```

## How It Works

- API Gateway routes POST requests to the ingress Lambda.
- The ingress Lambda validates requests, redacts sensitive data and sends records to SQS.
- The API returns `202 Accepted` after SQS accepts a message; it does not wait for S3.
- The worker Lambda processes queued messages and writes records to S3.
- Records include request headers, path, query parameters, body, response information and timestamp.
- Invalid requests are recorded when they can be queued. Failed processing is retried, with repeatedly failing messages moved to the dead-letter queue.

## Security and Reliability

- JWT authorization is enabled by default and requires an external OIDC issuer, audience and token with the configured `capture/write` scope.
- Separate least-privilege IAM roles for the ingress and worker Lambdas.
- S3 public access blocked, TLS-only bucket policy, SSE-S3 encryption and versioning.
- SQS-managed encryption, retry handling, a dead-letter queue and a CloudWatch alarm.
- CloudWatch logs with 14-day retention and API throttling.
- Captured records have a configured retention period of 30 days.

## Prerequisites

- Terraform and AWS CLI.
- AWS credentials with permission to provision the required resources.
- An existing S3 Terraform backend bucket matching `infra-tf/backend.tf`.
- An external OIDC provider for authenticated API requests.

## Deployment

Configure the backend and JWT variables for your environment. Set `jwt_issuer` to your OIDC issuer URL and `jwt_audience` to the expected API audience, then run:

```bash
cd infra-tf
terraform init
terraform validate
terraform plan
terraform apply
```

JWT authorization is enabled by default. Disabling it with `-var="enable_jwt_authorization=false"` is intended only for controlled integration testing. Do not leave a public unauthenticated endpoint running.

## Tests

Run the unit tests from the repository root:

```bash
python -m unittest discover -s tests -v
```
