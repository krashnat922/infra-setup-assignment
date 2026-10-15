variable "aws_region" {
  description = "AWS region for the Terraform state bucket."
  type        = string
  default     = "ap-south-1"
}

variable "state_bucket_name" {
  description = "S3 bucket name for Terraform state."
  type        = string
  default     = "ktapdiya-jodo-terraform"
}
