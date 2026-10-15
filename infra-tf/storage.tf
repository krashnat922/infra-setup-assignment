resource "aws_s3_bucket" "captures" {
  bucket = var.capture_bucket_name
  tags   = merge(local.common_tags, { Name = var.capture_bucket_name })
}

resource "aws_s3_bucket_ownership_controls" "captures" {
  bucket = aws_s3_bucket.captures.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "captures" {
  bucket = aws_s3_bucket.captures.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "captures" {
  bucket = aws_s3_bucket.captures.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "captures" {
  bucket = aws_s3_bucket.captures.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "captures_tls" {
  bucket = aws_s3_bucket.captures.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.captures.arn,
        "${aws_s3_bucket.captures.arn}/*"
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.captures]
}

resource "aws_s3_bucket_lifecycle_configuration" "captures" {
  bucket = aws_s3_bucket.captures.id

  rule {
    id     = "expire-captured-records"
    status = "Enabled"

    filter {}

    expiration {
      days = var.capture_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.capture_retention_days
    }
  }
}
