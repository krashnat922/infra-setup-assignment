terraform {
  backend "s3" {
    bucket       = "ktapdiya-jodo-terraform"
    key          = "jodo-infra/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
