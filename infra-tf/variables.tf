variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "name_prefix" {
  type    = string
  default = "jodo-capture"
}

variable "capture_bucket_name" {
  description = "Globally unique S3 bucket name for captured requests."
  type        = string
  default     = "ktapdiya-jodo-captures-20261015"
}

variable "enable_jwt_authorization" {
  description = "Keep true except during short-lived, controlled integration tests."
  type        = bool
  default     = true
}

variable "jwt_issuer" {
  description = "HTTPS issuer URL for the external OIDC provider. Required when JWT authorization is enabled."
  type        = string
  default     = ""
}

variable "jwt_audience" {
  description = "Expected JWT audience issued for this API. Required when JWT authorization is enabled."
  type        = string
  default     = ""
}

variable "jwt_scope" {
  description = "Required scope the identity provider must include in access tokens."
  type        = string
  default     = "capture/write"
}

variable "max_body_bytes" {
  description = "Maximum JSON request body size captured in full."
  type        = number
  default     = 65536
}

variable "capture_retention_days" {
  description = "Retention period for captured records and noncurrent S3 versions."
  type        = number
  default     = 30
}

variable "api_rate_limit" {
  type    = number
  default = 10
}

variable "api_burst_limit" {
  type    = number
  default = 20
}

variable "max_sqs_message_bytes" {
  type    = number
  default = 262144
}
