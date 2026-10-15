# AWS Asynchronous Request Capture

Terraform-managed AWS infrastructure that captures HTTP POST requests and stores request records in S3 asynchronously.

## Architecture

```text
Client
  |
  v
API Gateway HTTP API (JWT authorizer enabled by default)
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

## Request flow

- API Gateway routes POST requests to the ingress Lambda.
- The ingress Lambda validates the path and JSON body, redacts common sensitive headers and values, and sends a record to SQS.
- The API returns `202 Accepted` after SQS accepts the message; it does not wait for S3 persistence.
- The worker Lambda consumes queued messages and writes records under `accepted/YYYY/MM/DD/` or `rejected/YYYY/MM/DD/`.
- Records include request headers, path, query parameters, body (when valid and within configured limits), response information, timestamp and outcome.
- Invalid requests are recorded when they can be queued. If SQS is unavailable, the API returns `503` and cannot guarantee that the request is persisted.
- SQS retries failed processing and moves repeatedly failing messages to the dead-letter queue.

## Security and reliability

- JWT authorization is enabled by default. The API requires an external OIDC issuer, audience and token containing the configured `capture/write` scope.
- Separate least-privilege IAM roles for the ingress and worker Lambdas.
- S3 public access blocked, TLS-only bucket policy, SSE-S3 encryption, versioning and 30-day lifecycle retention.
- SQS-managed encryption, retry handling, a dead-letter queue and a CloudWatch alarm.
- CloudWatch logs with 14-day retention and API throttling.
- Sensitive values are redacted before records are queued. Do not use real credentials or secrets in test requests.

## Prerequisites

- Terraform `>= 1.10.0`, AWS CLI and Python for the unit tests.
- AWS credentials with permissions to create the required resources.
- A globally unique S3 bucket name for Terraform state.
- An existing OIDC identity provider that issues tokens for this API if testing authenticated requests.

Use `aws sts get-caller-identity` to verify which AWS account your CLI credentials target. Never commit AWS credentials, local state, plans or environment-specific `.tfvars` files.

## First-time setup

The state bucket must exist before Terraform can use it as a remote backend. Bootstrap it first, then migrate the bootstrap configuration's local state to S3.

1. Choose a globally unique state bucket name. If you use a different name from the repository's default, use it consistently in `terraform-backend/variables.tf`, `terraform-backend/backend.tf` and `infra-tf/backend.tf`. Keep the two backend keys distinct.
2. In `terraform-backend/backend.tf`, temporarily comment out the S3 backend block. This lets the initial bootstrap run with local state because the bucket does not exist yet.
3. From `terraform-backend/`, initialize and create the bucket and its protections:

   ```powershell
   terraform init
   terraform validate
   terraform plan -var="state_bucket_name=your-unique-state-bucket"
   terraform apply -var="state_bucket_name=your-unique-state-bucket"
   ```

   Replace `your-unique-state-bucket` with the actual bucket name. Do not commit the temporary backend-file edit.
4. Restore the S3 backend block in `terraform-backend/backend.tf` and verify its bucket name matches the bucket just created. Migrate the local bootstrap state to S3:

   ```powershell
   terraform init -migrate-state
   terraform state list
   ```

   Confirm that Terraform reports the state migration and that the resources are present in state before continuing. The bootstrap backend stores its state at `jodo-backend/terraform.tfstate`.
5. Configure the OIDC values for the application. Create an untracked `infra-tf/terraform.tfvars` file containing values from your identity provider:

   ```hcl
   jwt_issuer   = "https://your-oidc-issuer.example.com/"
   jwt_audience = "your-api-audience"
   ```

   Replace both example values with the exact issuer and audience for your provider. The default required scope is `capture/write`. The repository does not create or manage an identity provider.

## Deploy the application

Once the remote state bucket exists and the JWT variables are configured:

```powershell
cd infra-tf
terraform init
terraform validate
terraform plan
terraform apply
```

Review the plan before applying. The application state uses the separate key `jodo-infra/terraform.tfstate` in the state bucket.

JWT authorization is enabled by default. Disabling it with `-var="enable_jwt_authorization=false"` is intended only for short-lived, controlled integration testing. Do not leave a public unauthenticated endpoint running.

## Tests

Run the unit tests from the repository root:

```powershell
python -m unittest discover -s tests -v
```

## Cleanup

Destroy only the application resources from `infra-tf` when they are no longer needed. Because the capture bucket is versioned, delete its object versions and delete markers before destroying the bucket. Do not destroy the Terraform state backend while it contains state needed to manage resources.
