resource "aws_apigatewayv2_api" "capture" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"
  tags          = local.common_tags
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  count = var.enable_jwt_authorization ? 1 : 0

  api_id           = aws_apigatewayv2_api.capture.id
  name             = "${var.name_prefix}-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [var.jwt_audience]
    issuer   = var.jwt_issuer
  }

  lifecycle {
    precondition {
      condition     = startswith(var.jwt_issuer, "https://") && trimspace(var.jwt_audience) != ""
      error_message = "Set an HTTPS jwt_issuer and a non-empty jwt_audience when JWT authorization is enabled."
    }
    precondition {
      condition     = trimspace(var.jwt_scope) != ""
      error_message = "Set jwt_scope to a scope issued by the configured identity provider."
    }
  }
}

resource "aws_apigatewayv2_integration" "ingress" {
  api_id                 = aws_apigatewayv2_api.capture.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.ingress.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 10000
}

resource "aws_apigatewayv2_route" "post_proxy" {
  api_id    = aws_apigatewayv2_api.capture.id
  route_key = "POST /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.ingress.id}"

  authorization_type   = var.enable_jwt_authorization ? "JWT" : "NONE"
  authorizer_id        = var.enable_jwt_authorization ? aws_apigatewayv2_authorizer.jwt[0].id : null
  authorization_scopes = var.enable_jwt_authorization ? [var.jwt_scope] : null
}

resource "aws_apigatewayv2_route" "post_root" {
  api_id    = aws_apigatewayv2_api.capture.id
  route_key = "POST /"
  target    = "integrations/${aws_apigatewayv2_integration.ingress.id}"

  authorization_type   = var.enable_jwt_authorization ? "JWT" : "NONE"
  authorizer_id        = var.enable_jwt_authorization ? aws_apigatewayv2_authorizer.jwt[0].id : null
  authorization_scopes = var.enable_jwt_authorization ? [var.jwt_scope] : null
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.name_prefix}"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.capture.id
  name        = "$default"
  auto_deploy = true
  tags        = local.common_tags

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      sourceIp       = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      method         = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
    })
  }

  default_route_settings {
    throttling_rate_limit    = var.api_rate_limit
    throttling_burst_limit   = var.api_burst_limit
    detailed_metrics_enabled = true
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingress.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.capture.execution_arn}/*/*/*"
}
