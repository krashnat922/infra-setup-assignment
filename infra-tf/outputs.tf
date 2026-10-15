output "api_endpoint" {
  value = aws_apigatewayv2_api.capture.api_endpoint
}

output "capture_endpoint" {
  value = "${aws_apigatewayv2_api.capture.api_endpoint}/capture"
}

output "capture_bucket_name" {
  value = aws_s3_bucket.captures.bucket
}

output "capture_queue_name" {
  value = aws_sqs_queue.captures.name
}
