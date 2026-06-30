resource "aws_cloudwatch_event_rule" "daily_ingest" {
  count               = var.enable_daily_ingest_schedule ? 1 : 0
  name                = "${local.name_prefix}-daily-ingest"
  description         = "Daily refresh for curated public sports data"
  schedule_expression = "rate(1 day)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "daily_ingest" {
  count = var.enable_daily_ingest_schedule ? 1 : 0
  rule  = aws_cloudwatch_event_rule.daily_ingest[0].name
  arn   = aws_lambda_function.ingest.arn
}

resource "aws_lambda_permission" "eventbridge_ingest" {
  count         = var.enable_daily_ingest_schedule ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_ingest[0].arn
}
