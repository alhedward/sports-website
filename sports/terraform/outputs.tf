output "site_url" {
  description = "Primary public URL for the static site. Uses the custom domain when enabled."
  value       = local.public_site_url
}

output "cloudfront_url" {
  description = "CloudFront distribution URL. Useful for diagnostics even when a custom domain is enabled."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "custom_domain_name" {
  description = "Configured custom domain name, if enabled."
  value       = local.custom_domain_enabled ? var.custom_domain_name : null
}

output "route53_zone_id" {
  description = "Route 53 public hosted zone ID used for the site, if Terraform manages DNS."
  value       = local.route53_enabled ? data.aws_route53_zone.site[0].zone_id : null
}

output "acm_certificate_arn" {
  description = "ACM certificate ARN used by CloudFront, if a custom domain is enabled."
  value       = local.custom_domain_enabled ? aws_acm_certificate.site[0].arn : null
}

output "acm_dns_validation_records" {
  description = "DNS validation records for the ACM certificate. Useful when DNS is not managed by this Terraform stack."
  value = local.custom_domain_enabled ? {
    for dvo in aws_acm_certificate.site[0].domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  } : {}
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID."
  value       = aws_cloudfront_distribution.site.id
}

output "site_bucket_name" {
  description = "S3 bucket containing website assets."
  value       = aws_s3_bucket.site.bucket
}

output "api_base_url" {
  description = "API Gateway base URL."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "api_lambda_name" {
  description = "API Lambda function name."
  value       = aws_lambda_function.api.function_name
}

output "ingest_lambda_name" {
  description = "Ingest/seed Lambda function name."
  value       = aws_lambda_function.ingest.function_name
}

output "tournaments_table_name" {
  description = "DynamoDB tournaments table name."
  value       = aws_dynamodb_table.tournaments.name
}

output "players_table_name" {
  description = "DynamoDB players table name."
  value       = aws_dynamodb_table.players.name
}

output "events_table_name" {
  description = "DynamoDB events table name."
  value       = aws_dynamodb_table.events.name
}


output "sport_bodies_table_name" {
  description = "DynamoDB sport bodies / official links table name."
  value       = aws_dynamodb_table.sport_bodies.name
}
