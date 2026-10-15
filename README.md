\# AWS Asynchronous Request Capture



\## Overview



Terraform-managed AWS infrastructure for capturing HTTP POST requests and persisting their records to S3 asynchronously.



\## Architecture



```text

Client

&#x20; |

API Gateway HTTP API

&#x20; |

Ingress Lambda

&#x20; |

SQS Queue ---> Dead-Letter Queue

&#x20; |

Worker Lambda

&#x20; |

S3 Bucket

```



\## How It Works



\- API Gateway routes POST requests to the ingress Lambda.

\- The ingress Lambda validates requests, redacts sensitive data and sends records to SQS.

\- The API returns `202 Accepted` after SQS accepts a message, without waiting for S3.

\- The worker Lambda processes queued messages and writes records to S3.

\- Records include request headers, path, query parameters, body, response information and timestamp.

\- Invalid requests are recorded when they can be queued. SQS retries failed processing and moves repeatedly failing messages to a dead-letter queue.



\## Security and Reliability



\- JWT authorization is enabled by default and requires an external OIDC issuer, audience and token with the configured scope.

\- Separate least-privilege IAM roles for the ingress and worker Lambdas.

\- S3 public access blocked, TLS-only bucket policy, SSE-S3 encryption and versioning.

\- SQS-managed encryption, retries, a dead-letter queue and a CloudWatch alarm.

\- CloudWatch logs with 14-day retention and API throttling.

\- Captured records have a configured retention period of 30 days.



\## Prerequisites



\- Terraform and AWS CLI.

\- AWS credentials with permissions to provision the required resources.

\- An existing S3 Terraform backend bucket configured in `infra-tf/backend.tf`.

\- A valid external OIDC provider for authenticated API requests.



\## Deployment



Configure the backend and JWT variables for your environment, then run:



```bash

cd infra-tf

terraform init

terraform validate

terraform plan

terraform apply

```



Set `jwt\_issuer` and `jwt\_audience` before deployment. JWT authorization is enabled by default. Disabling it with `-var="enable\_jwt\_authorization=false"` is intended only for controlled testing; do not leave a public unauthenticated endpoint running.



\## Tests



Run the unit tests from the repository root:



```bash

python -m unittest discover -s tests -v

```

