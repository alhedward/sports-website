locals {
  name_prefix = "${var.project_name}-${var.environment}"

  custom_domain_enabled = trimspace(var.custom_domain_name) != ""
  route53_enabled       = local.custom_domain_enabled && var.create_route53_records

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  cloudfront_certificate_arn = local.custom_domain_enabled ? aws_acm_certificate_validation.site[0].certificate_arn : null
  public_site_url            = local.custom_domain_enabled ? "https://${var.custom_domain_name}" : "https://${aws_cloudfront_distribution.site.domain_name}"

  content_types = {
    html = "text/html; charset=utf-8"
    css  = "text/css; charset=utf-8"
    js   = "application/javascript; charset=utf-8"
    json = "application/json; charset=utf-8"
    svg  = "image/svg+xml"
    png  = "image/png"
    jpg  = "image/jpeg"
    jpeg = "image/jpeg"
    ico  = "image/x-icon"
    txt  = "text/plain; charset=utf-8"
  }
}
