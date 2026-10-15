data "archive_file" "ingress" {
  type        = "zip"
  source_dir  = "${path.module}/code/ingress"
  output_path = "${path.module}/.terraform/ingress.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

data "archive_file" "worker" {
  type        = "zip"
  source_dir  = "${path.module}/code/worker"
  output_path = "${path.module}/.terraform/worker.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.name_prefix}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "captures" {
  name                       = "${var.name_prefix}-captures"
  max_message_size           = var.max_sqs_message_bytes
  visibility_timeout_seconds = 180
  message_retention_seconds  = 1209600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 5
  })
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "ingress" {
  name              = "/aws/lambda/${var.name_prefix}-ingress"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.name_prefix}-worker"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_lambda_function" "ingress" {
  function_name    = "${var.name_prefix}-ingress"
  role             = aws_iam_role.ingress.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.ingress.output_path
  source_code_hash = data.archive_file.ingress.output_base64sha256
  timeout          = 10
  memory_size      = 256
  tags             = local.common_tags

  environment {
    variables = {
      QUEUE_URL             = aws_sqs_queue.captures.url
      MAX_BODY_BYTES        = tostring(var.max_body_bytes)
      MAX_SQS_MESSAGE_BYTES = tostring(var.max_sqs_message_bytes)
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.ingress_logs,
    aws_iam_role_policy.ingress_sqs,
    aws_cloudwatch_log_group.ingress
  ]
}

resource "aws_lambda_function" "worker" {
  function_name    = "${var.name_prefix}-worker"
  role             = aws_iam_role.worker.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.worker.output_path
  source_code_hash = data.archive_file.worker.output_base64sha256
  timeout          = 30
  memory_size      = 256
  tags             = local.common_tags

  environment {
    variables = {
      CAPTURE_BUCKET = aws_s3_bucket.captures.bucket
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.worker_logs,
    aws_iam_role_policy.worker_sqs,
    aws_iam_role_policy.worker_s3,
    aws_cloudwatch_log_group.worker
  ]
}

resource "aws_lambda_event_source_mapping" "captures" {
  event_source_arn        = aws_sqs_queue.captures.arn
  function_name           = aws_lambda_function.worker.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = 5
  }
}

resource "aws_cloudwatch_metric_alarm" "dead_letter_messages" {
  alarm_name          = "${var.name_prefix}-dlq-not-empty"
  alarm_description   = "One or more capture messages reached the dead-letter queue."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dead_letter.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  tags                = local.common_tags
}
