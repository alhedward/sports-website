terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.5"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}

locals {
  name_prefix = "lroc"
  common_tags = {
    Name           = local.name_prefix
    Application    = "club-website"
    Site           = "lroc"
    Club           = "LROC"
    Environment    = "development"
    ManagedBy      = "terraform"
    CostCenter     = "lroc"
    CostAllocation = "club-website"
  }
  site_bucket_name                      = "${local.name_prefix}-site-${data.aws_caller_identity.current.account_id}"
  member_bucket_name                    = "${local.name_prefix}-member-files-${data.aws_caller_identity.current.account_id}"
  site_domain_labels                    = split(".", var.site_domain)
  site_parent_domain                    = length(local.site_domain_labels) > 1 ? join(".", slice(local.site_domain_labels, 1, length(local.site_domain_labels))) : var.site_domain
  expo_domain                           = "expo.${local.site_parent_domain}"
  cloudfront_site_aliases               = distinct(concat([var.site_domain, local.expo_domain], var.subject_alternative_names))
  certificate_subject_alternative_names = distinct(concat(var.subject_alternative_names, [local.expo_domain]))
  allowed_origins = [
    "http://localhost:8000",
    "https://${var.site_domain}",
    "https://${local.expo_domain}",
  ]

  ses_email_domain                  = trimspace(var.ses_email_domain) != "" ? trimspace(var.ses_email_domain) : var.site_domain
  ses_from_email                    = trimspace(var.ses_from_email) != "" ? trimspace(var.ses_from_email) : "no-reply@${local.ses_email_domain}"
  ses_reply_to_email                = trimspace(var.ses_reply_to_email) != "" ? trimspace(var.ses_reply_to_email) : local.ses_from_email
  ses_mail_from_domain              = trimspace(var.ses_mail_from_subdomain) != "" ? "${trimspace(var.ses_mail_from_subdomain)}.${local.ses_email_domain}" : "mail.${local.ses_email_domain}"
  ses_configuration_name            = trimspace(var.ses_configuration_set_name) != "" ? trimspace(var.ses_configuration_set_name) : "${local.name_prefix}-club-mail"
  webmail_inbound_domain            = trimspace(var.webmail_inbound_domain) != "" ? trimspace(var.webmail_inbound_domain) : local.ses_email_domain
  webmail_unmatched_mailbox_address = trimspace(var.webmail_unmatched_mailbox_address) != "" ? trimspace(var.webmail_unmatched_mailbox_address) : "unmatched@${local.webmail_inbound_domain}"
  webmail_inbound_recipients        = length(var.webmail_inbound_recipients) > 0 ? var.webmail_inbound_recipients : [local.webmail_inbound_domain]
  site_base_url                     = "https://${var.site_domain}"
  site_app_version                  = trimspace(var.site_app_version) != "" ? trimspace(var.site_app_version) : formatdate("YYYYMMDDhhmmss", timestamp())
  geoapify_maptiles_api_key_raw     = trimspace(var.geoapify_maptiles_api_key) != "" ? trimspace(var.geoapify_maptiles_api_key) : trimspace(var.geoaplify_maptiles_api_key)
  geoapify_geocoding_api_key_raw    = trimspace(var.geoapify_geocoding_api_key) != "" ? trimspace(var.geoapify_geocoding_api_key) : trimspace(var.geoaplify_geocoding_api_key)
  geoapify_maptiles_api_key         = local.geoapify_maptiles_api_key_raw
  # Geoapify keys are account/API keys, so a map-tile key can also be used for forward geocoding unless a separate private key is supplied.
  geoapify_geocoding_api_key         = local.geoapify_geocoding_api_key_raw != "" ? local.geoapify_geocoding_api_key_raw : local.geoapify_maptiles_api_key_raw
  geoapify_maptiles_url_template_raw = trimspace(var.geoapify_maptiles_url_template) != "" ? trimspace(var.geoapify_maptiles_url_template) : "https://maps.geoapify.com/v1/tile/carto/{z}/{x}/{y}.png?&apiKey={apiKey}"
  geoapify_maptiles_url_template     = strcontains(local.geoapify_maptiles_url_template_raw, "{apiKey}") ? local.geoapify_maptiles_url_template_raw : "${local.geoapify_maptiles_url_template_raw}{apiKey}"

  ssm_parameter_prefix         = "/${local.name_prefix}"
  openai_api_key_param_name    = "${local.ssm_parameter_prefix}/openai/api_key"
  openai_model_param_name      = "${local.ssm_parameter_prefix}/openai/model"
  vapid_public_key_param_name  = "${local.ssm_parameter_prefix}/vapid/public_key"
  vapid_private_key_param_name = "${local.ssm_parameter_prefix}/vapid/private_key"
  vapid_subject_param_name     = "${local.ssm_parameter_prefix}/vapid/subject"

  site_runtime_config = <<-EOT
window.LROC_AUTH = {
  enabled: true,
  cognitoDomain: "https://${aws_cognito_user_pool_domain.site.domain}.auth.${var.aws_region}.amazoncognito.com",
  clientId: "${aws_cognito_user_pool_client.site.id}",
  redirectUri: window.location.origin + window.location.pathname.replace(/[^/]+$/, "") + "members.html",
  logoutUri: window.location.origin + window.location.pathname.replace(/[^/]+$/, "") + "index.html",
  scopes: ["openid", "email", "profile", "phone", "aws.cognito.signin.user.admin"]
};

window.LROC_MEMBER_API = {
  baseUrl: "${aws_apigatewayv2_api.member_api.api_endpoint}"
};

window.LROC_PUSH = {
  vapidPublicKey: "${var.push_vapid_public_key}"
};

window.LROC_MAPS = {
  provider: "geoapify",
  geoapifyMaptilesApiKey: "${local.geoapify_maptiles_api_key}",
  tileUrlTemplate: "${local.geoapify_maptiles_url_template}"
};

window.LROC_APP = {
  name: "LROC Website",
  version: "${local.site_app_version}",
  lastUpdated: "${formatdate("DD MMM YYYY", timestamp())}",
  author: "Tony Edward",
  copyrightYear: "${formatdate("YYYY", timestamp())}"
};
EOT

  site_file_content_types = {
    ".html"  = "text/html; charset=utf-8"
    ".css"   = "text/css; charset=utf-8"
    ".js"    = "application/javascript; charset=utf-8"
    ".json"  = "application/json; charset=utf-8"
    ".png"   = "image/png"
    ".jpg"   = "image/jpeg"
    ".jpeg"  = "image/jpeg"
    ".webp"  = "image/webp"
    ".svg"   = "image/svg+xml"
    ".ico"   = "image/x-icon"
    ".ttf"   = "font/ttf"
    ".woff"  = "font/woff"
    ".woff2" = "font/woff2"
    ".txt"   = "text/plain; charset=utf-8"
  }

  site_cache_control_no_store = "no-cache, no-store, must-revalidate"
  site_cache_control_static   = "public, max-age=86400"

  callback_urls = [
    "http://localhost:8000/members.html",
    "http://localhost:8000/admin.html",
    "http://localhost:8000/articles.html",
    "http://localhost:8000/webmail.html",
    "https://${var.site_domain}/members.html",
    "https://${var.site_domain}/admin.html",
    "https://${var.site_domain}/articles.html",
    "https://${var.site_domain}/webmail.html",
  ]

  logout_urls = [
    "http://localhost:8000/members.html",
    "http://localhost:8000/admin.html",
    "http://localhost:8000/articles.html",
    "http://localhost:8000/webmail.html",
    "https://${var.site_domain}/members.html",
    "https://${var.site_domain}/admin.html",
    "https://${var.site_domain}/articles.html",
    "https://${var.site_domain}/webmail.html",
  ]

  site_managed_files = {
    for f in fileset("${path.module}/../site", "**") :
    f => "${path.module}/../site/${f}"
    if !endswith(f, "/") && f != "content.json" && f != "config.js" && f != "articles/index.json" && f != "magazines/index.json"
  }
}

data "aws_caller_identity" "current" {}

data "aws_route53_zone" "site" {
  name         = var.hosted_zone_name
  private_zone = false
}

data "archive_file" "member_files_lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/member_files.py"
  output_path = "${path.module}/build/member_files.zip"
}

data "archive_file" "notification_worker_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../notification_worker"
  output_path = "${path.module}/build/chat_notification_worker.zip"
}

resource "aws_s3_bucket" "site" {
  bucket        = local.site_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket" "member_files" {
  bucket = local.member_bucket_name
}

resource "aws_s3_bucket_public_access_block" "member_files" {
  bucket                  = aws_s3_bucket.member_files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "member_files" {
  bucket = aws_s3_bucket.member_files.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "member_files" {
  bucket = aws_s3_bucket.member_files.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "member_files" {
  bucket = aws_s3_bucket.member_files.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = local.allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_cors_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = local.allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_policy" "member_files" {
  count  = var.enable_webmail ? 1 : 0
  bucket = aws_s3_bucket.member_files.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid       = "AllowSesInboundWebmailWrite"
        Effect    = "Allow"
        Principal = { Service = "ses.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.member_files.arn}/webmail/inbound/*"
        Condition = {
          StringEquals = { "AWS:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      }
    ]
  })
}

resource "aws_acm_certificate" "site" {
  provider                  = aws.us_east_1
  domain_name               = var.site_domain
  validation_method         = "DNS"
  subject_alternative_names = local.certificate_subject_alternative_names

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "site_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.site.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id = data.aws_route53_zone.site.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

resource "aws_acm_certificate_validation" "site" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for record in aws_route53_record.site_cert_validation : record.fqdn]
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${local.name_prefix}-site-oac"
  description                       = "Origin access control for the LROC site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "expo_rewrite" {
  name    = "${local.name_prefix}-expo-rewrite"
  runtime = "cloudfront-js-1.0"
  comment = "Serve the LROC Expo microsite from expo.<domain> using the main site bucket"
  publish = true
  code    = <<-EOT
function handler(event) {
  var request = event.request;
  var host = request.headers.host && request.headers.host.value ? request.headers.host.value.toLowerCase() : '';
  var expoHost = '${local.expo_domain}'.toLowerCase();
  if (host !== expoHost) return request;
  var uri = request.uri || '/';
  if (uri === '/' || uri === '') {
    request.uri = '/expo/index.html';
    return request;
  }
  if (uri.indexOf('/expo/') === 0 || uri.indexOf('/assets/') === 0 || uri.indexOf('/icons/') === 0 || uri === '/favicon.ico' || uri === '/favicon.png') {
    return request;
  }
  request.uri = '/expo' + uri;
  return request;
}
EOT
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = local.cloudfront_site_aliases
  price_class         = var.cloudfront_price_class

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "site-s3-origin"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = "site-s3-origin"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.expo_rewrite.arn
    }

    forwarded_values {
      query_string = true
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 86400
  }

  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  depends_on = [aws_acm_certificate_validation.site]
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid    = "AllowCloudFrontRead",
        Effect = "Allow",
        Principal = {
          Service = "cloudfront.amazonaws.com"
        },
        Action   = ["s3:GetObject"],
        Resource = "${aws_s3_bucket.site.arn}/*",
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.site.arn
          }
        }
      }
    ]
  })
}

resource "aws_s3_object" "site_files" {
  for_each = local.site_managed_files

  bucket       = aws_s3_bucket.site.id
  key          = each.key
  source       = each.value
  etag         = filemd5(each.value)
  content_type = lookup(local.site_file_content_types, length(regexall("\\.[^.]+$", each.key)) > 0 ? regexall("\\.[^.]+$", each.key)[0] : "", "application/octet-stream")
  cache_control = (
    endswith(each.key, ".html") ||
    endswith(each.key, ".css") ||
    endswith(each.key, ".js") ||
    endswith(each.key, ".json") ||
    each.key == "service-worker.js" ||
    each.key == "manifest.json"
  ) ? local.site_cache_control_no_store : local.site_cache_control_static
}

resource "aws_s3_object" "site_runtime_config" {
  bucket        = aws_s3_bucket.site.id
  key           = "config.js"
  content       = local.site_runtime_config
  etag          = md5(local.site_runtime_config)
  content_type  = "application/javascript; charset=utf-8"
  cache_control = local.site_cache_control_no_store
}

resource "aws_route53_record" "site_alias_a" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = var.site_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "site_alias_aaaa" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = var.site_domain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "expo_alias_a" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = local.expo_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "expo_alias_aaaa" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = local.expo_domain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_cognito_user_pool" "members" {
  name = "${local.name_prefix}-members"

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
  mfa_configuration        = "OFF"

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 90
  }

  schema {
    attribute_data_type = "String"
    name                = "callsign"
    mutable             = true
    required            = false

    string_attribute_constraints {
      min_length = 0
      max_length = 32
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  lifecycle {
    ignore_changes = [schema]
  }
}

resource "aws_cognito_user_pool_client" "site" {
  name                                 = "${local.name_prefix}-site-client"
  user_pool_id                         = aws_cognito_user_pool.members.id
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["aws.cognito.signin.user.admin", "email", "openid", "phone", "profile"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = local.callback_urls
  logout_urls                          = local.logout_urls
  generate_secret                      = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH"
  ]
}

resource "aws_cognito_user_pool_domain" "site" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.members.id
}

resource "aws_cognito_user_group" "members" {
  name         = "members"
  user_pool_id = aws_cognito_user_pool.members.id
}

resource "aws_cognito_user_group" "committee" {
  name         = "committee"
  user_pool_id = aws_cognito_user_pool.members.id
}

resource "aws_cognito_user_group" "admins" {
  name         = "admins"
  user_pool_id = aws_cognito_user_pool.members.id
}

resource "aws_cognito_user_group" "webmaster" {
  name         = "webmaster"
  user_pool_id = aws_cognito_user_pool.members.id
}

resource "aws_ses_domain_identity" "club_mail" {
  domain = local.ses_email_domain
}

resource "aws_route53_record" "ses_domain_verification" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = "_amazonses.${aws_ses_domain_identity.club_mail.domain}"
  type    = "TXT"
  ttl     = 600
  records = [aws_ses_domain_identity.club_mail.verification_token]
}

resource "aws_ses_domain_dkim" "club_mail" {
  domain = aws_ses_domain_identity.club_mail.domain
}

resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = data.aws_route53_zone.site.zone_id
  name    = "${aws_ses_domain_dkim.club_mail.dkim_tokens[count.index]}._domainkey.${aws_ses_domain_identity.club_mail.domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.club_mail.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_ses_domain_mail_from" "club_mail" {
  domain           = aws_ses_domain_identity.club_mail.domain
  mail_from_domain = local.ses_mail_from_domain
}

resource "aws_route53_record" "ses_mail_from_mx" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = aws_ses_domain_mail_from.club_mail.mail_from_domain
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${var.aws_region}.amazonses.com"]
}

resource "aws_route53_record" "ses_mail_from_txt" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = aws_ses_domain_mail_from.club_mail.mail_from_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com -all"]
}

resource "aws_route53_record" "ses_dmarc" {
  zone_id = data.aws_route53_zone.site.zone_id
  name    = "_dmarc.${local.ses_email_domain}"
  type    = "TXT"
  ttl     = 300

  records = [
    "v=DMARC1; p=none; adkim=r; aspf=r"
  ]
}

resource "aws_ses_configuration_set" "club_mail" {
  name = local.ses_configuration_name
}


resource "aws_sns_topic" "ses_bounces" {
  name = "${local.name_prefix}-ses-bounces"
}

resource "aws_sns_topic" "ses_complaints" {
  name = "${local.name_prefix}-ses-complaints"
}

resource "aws_sns_topic_policy" "ses_bounces" {
  arn = aws_sns_topic.ses_bounces.arn

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "ses.amazonaws.com" },
      Action    = "sns:Publish",
      Resource  = aws_sns_topic.ses_bounces.arn,
      Condition = {
        StringEquals = { "AWS:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

resource "aws_sns_topic_policy" "ses_complaints" {
  arn = aws_sns_topic.ses_complaints.arn

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "ses.amazonaws.com" },
      Action    = "sns:Publish",
      Resource  = aws_sns_topic.ses_complaints.arn,
      Condition = {
        StringEquals = { "AWS:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

resource "aws_ses_event_destination" "club_mail_bounces" {
  name                   = "${local.name_prefix}-ses-bounces"
  configuration_set_name = aws_ses_configuration_set.club_mail.name
  enabled                = true
  matching_types         = ["bounce"]

  sns_destination {
    topic_arn = aws_sns_topic.ses_bounces.arn
  }
}

resource "aws_ses_event_destination" "club_mail_complaints" {
  name                   = "${local.name_prefix}-ses-complaints"
  configuration_set_name = aws_ses_configuration_set.club_mail.name
  enabled                = true
  matching_types         = ["complaint"]

  sns_destination {
    topic_arn = aws_sns_topic.ses_complaints.arn
  }
}

resource "aws_route53_record" "webmail_inbound_mx" {
  count   = var.enable_webmail ? 1 : 0
  zone_id = data.aws_route53_zone.site.zone_id
  name    = local.webmail_inbound_domain
  type    = "MX"
  ttl     = 300
  records = ["10 inbound-smtp.${var.aws_region}.amazonaws.com"]
}

resource "aws_route53_record" "webmail_inbound_txt" {
  count   = var.enable_webmail && var.create_webmail_inbound_txt ? 1 : 0
  zone_id = data.aws_route53_zone.site.zone_id
  name    = local.webmail_inbound_domain
  type    = "TXT"
  ttl     = 300
  records = ["v=spf1 include:amazonses.com -all"]
}

resource "aws_ses_receipt_rule_set" "webmail" {
  count         = var.enable_webmail ? 1 : 0
  rule_set_name = "${local.name_prefix}-webmail-inbound"
}

resource "aws_ses_active_receipt_rule_set" "webmail" {
  count         = var.enable_webmail ? 1 : 0
  rule_set_name = aws_ses_receipt_rule_set.webmail[0].rule_set_name
}

resource "aws_lambda_permission" "allow_ses_inbound_webmail" {
  count          = var.enable_webmail ? 1 : 0
  statement_id   = "AllowExecutionFromSesInboundWebmail"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.member_files.function_name
  principal      = "ses.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_ses_receipt_rule" "webmail_inbound" {
  count         = var.enable_webmail ? 1 : 0
  name          = "${local.name_prefix}-webmail-inbound"
  rule_set_name = aws_ses_receipt_rule_set.webmail[0].rule_set_name
  recipients    = local.webmail_inbound_recipients
  enabled       = true
  scan_enabled  = true

  s3_action {
    bucket_name       = aws_s3_bucket.member_files.bucket
    object_key_prefix = "webmail/inbound/"
    position          = 1
  }

  lambda_action {
    function_arn    = aws_lambda_function.member_files.arn
    invocation_type = "Event"
    position        = 2
  }

  depends_on = [
    aws_s3_bucket_policy.member_files,
    aws_lambda_permission.allow_ses_inbound_webmail
  ]
}

resource "aws_iam_role" "webmail_malware_protection" {
  count = var.enable_webmail && var.enable_webmail_attachment_malware_protection ? 1 : 0
  name  = "${local.name_prefix}-webmail-malware-protection"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "malware-protection-plan.guardduty.amazonaws.com"
        },
        Action = "sts:AssumeRole",
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          },
          ArnLike = {
            "aws:SourceArn" = "arn:aws:guardduty:${var.aws_region}:${data.aws_caller_identity.current.account_id}:malware-protection-plan/*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "webmail_malware_protection" {
  count = var.enable_webmail && var.enable_webmail_attachment_malware_protection ? 1 : 0
  name  = "${local.name_prefix}-webmail-malware-protection-inline"
  role  = aws_iam_role.webmail_malware_protection[0].id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid    = "AllowManagedRuleToSendS3EventsToGuardDuty",
        Effect = "Allow",
        Action = [
          "events:PutRule",
          "events:DeleteRule",
          "events:PutTargets",
          "events:RemoveTargets"
        ],
        Resource = "arn:aws:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:rule/DO-NOT-DELETE-AmazonGuardDutyMalwareProtectionS3*",
        Condition = {
          StringLike = {
            "events:ManagedBy" = "malware-protection-plan.guardduty.amazonaws.com"
          }
        }
      },
      {
        Sid    = "AllowGuardDutyToMonitorEventBridgeManagedRule",
        Effect = "Allow",
        Action = [
          "events:DescribeRule",
          "events:ListTargetsByRule"
        ],
        Resource = "arn:aws:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:rule/DO-NOT-DELETE-AmazonGuardDutyMalwareProtectionS3*"
      },
      {
        Sid    = "AllowPostScanTag",
        Effect = "Allow",
        Action = [
          "s3:PutObjectTagging",
          "s3:GetObjectTagging",
          "s3:PutObjectVersionTagging",
          "s3:GetObjectVersionTagging"
        ],
        Resource = "${aws_s3_bucket.member_files.arn}/webmail/attachments/*"
      },
      {
        Sid    = "AllowEnableS3EventBridgeEvents",
        Effect = "Allow",
        Action = [
          "s3:PutBucketNotification",
          "s3:GetBucketNotification"
        ],
        Resource = aws_s3_bucket.member_files.arn
      },
      {
        Sid      = "AllowPutValidationObject",
        Effect   = "Allow",
        Action   = ["s3:PutObject"],
        Resource = "${aws_s3_bucket.member_files.arn}/malware-protection-resource-validation-object"
      },
      {
        Sid      = "AllowCheckBucketOwnership",
        Effect   = "Allow",
        Action   = ["s3:ListBucket"],
        Resource = aws_s3_bucket.member_files.arn
      },
      {
        Sid    = "AllowMalwareScan",
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion"
        ],
        Resource = "${aws_s3_bucket.member_files.arn}/webmail/attachments/*"
      }
    ]
  })
}

resource "aws_guardduty_malware_protection_plan" "webmail_attachments" {
  count = var.enable_webmail && var.enable_webmail_attachment_malware_protection ? 1 : 0
  role  = aws_iam_role.webmail_malware_protection[0].arn

  protected_resource {
    s3_bucket {
      bucket_name     = aws_s3_bucket.member_files.bucket
      object_prefixes = ["webmail/attachments/"]
    }
  }

  actions {
    tagging = [{
      status = "ENABLED"
    }]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-webmail-attachment-malware-scan"
  })

  depends_on = [aws_iam_role_policy.webmail_malware_protection]
}

resource "aws_dynamodb_table" "member_metadata" {
  name         = "${local.name_prefix}-member-metadata"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "mail_state" {
  name         = "${local.name_prefix}-mail-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "chat" {
  name         = "${local.name_prefix}-chat"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_sqs_queue" "chat_notifications_dlq" {
  name                      = "${local.name_prefix}-chat-notifications-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "chat_notifications" {
  name                       = "${local.name_prefix}-chat-notifications"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.chat_notifications_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_ssm_parameter" "openai_api_key" {
  name        = local.openai_api_key_param_name
  description = "LROC OpenAI API key for member Vehicle Help."
  type        = "SecureString"
  value       = trimspace(var.openai_api_key) != "" ? var.openai_api_key : "__NOT_CONFIGURED__"

  lifecycle {
    # Existing parameters may have legacy provider-default tags such as lowercase `name`.
    # The GitHub deploy role intentionally does not have ssm:RemoveTagsFromResource,
    # so avoid tag churn on secret/config parameters while global tags are normalised.
    ignore_changes = [tags, tags_all]
  }
}

resource "aws_ssm_parameter" "openai_model" {
  name        = local.openai_model_param_name
  description = "LROC OpenAI model for member Vehicle Help."
  type        = "String"
  value       = trimspace(var.openai_model) != "" ? var.openai_model : "gpt-5-mini"

  lifecycle {
    # Existing parameters may have legacy provider-default tags such as lowercase `name`.
    # The GitHub deploy role intentionally does not have ssm:RemoveTagsFromResource,
    # so avoid tag churn on secret/config parameters while global tags are normalised.
    ignore_changes = [tags, tags_all]
  }
}

resource "aws_ssm_parameter" "vapid_public_key" {
  name        = local.vapid_public_key_param_name
  description = "LROC web push VAPID public key."
  type        = "String"
  value       = trimspace(var.push_vapid_public_key) != "" ? var.push_vapid_public_key : "__NOT_CONFIGURED__"

  lifecycle {
    # Existing parameters may have legacy provider-default tags such as lowercase `name`.
    # The GitHub deploy role intentionally does not have ssm:RemoveTagsFromResource,
    # so avoid tag churn on secret/config parameters while global tags are normalised.
    ignore_changes = [tags, tags_all]
  }
}

resource "aws_ssm_parameter" "vapid_private_key" {
  name        = local.vapid_private_key_param_name
  description = "LROC web push VAPID private key."
  type        = "SecureString"
  value       = trimspace(var.push_vapid_private_key) != "" ? var.push_vapid_private_key : "__NOT_CONFIGURED__"

  lifecycle {
    # Existing parameters may have legacy provider-default tags such as lowercase `name`.
    # The GitHub deploy role intentionally does not have ssm:RemoveTagsFromResource,
    # so avoid tag churn on secret/config parameters while global tags are normalised.
    ignore_changes = [tags, tags_all]
  }
}

resource "aws_ssm_parameter" "vapid_subject" {
  name        = local.vapid_subject_param_name
  description = "LROC web push VAPID subject/contact."
  type        = "String"
  value       = trimspace(var.push_vapid_subject) != "" ? var.push_vapid_subject : "__NOT_CONFIGURED__"

  lifecycle {
    # Existing parameters may have legacy provider-default tags such as lowercase `name`.
    # The GitHub deploy role intentionally does not have ssm:RemoveTagsFromResource,
    # so avoid tag churn on secret/config parameters while global tags are normalised.
    ignore_changes = [tags, tags_all]
  }
}

resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-member-files-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_member_files" {
  name = "${local.name_prefix}-member-files-inline"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["s3:ListBucket"],
        Resource = aws_s3_bucket.member_files.arn
      },
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:HeadObject", "s3:GetObjectTagging"],
        Resource = [
          "${aws_s3_bucket.member_files.arn}/${var.member_files_prefix}*",
          "${aws_s3_bucket.member_files.arn}/webmail/*",
          "${aws_s3_bucket.member_files.arn}/articles/member-files/*"
        ]
      },
      {
        Effect   = "Allow",
        Action   = ["s3:ListBucket"],
        Resource = aws_s3_bucket.site.arn
      },
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:PutObject", "s3:HeadObject"],
        Resource = [
          "${aws_s3_bucket.site.arn}/content.json",
          "${aws_s3_bucket.site.arn}/content-history/*",
          "${aws_s3_bucket.site.arn}/expo/content.json",
          "${aws_s3_bucket.site.arn}/expo/history/*",
          "${aws_s3_bucket.site.arn}/vehicle.json",
          "${aws_s3_bucket.site.arn}/event-data.json",
          "${aws_s3_bucket.site.arn}/articles/index.json",
          "${aws_s3_bucket.site.arn}/articles/files/*",
          "${aws_s3_bucket.site.arn}/magazines/index.json",
          "${aws_s3_bucket.site.arn}/magazines/files/*",
          "${aws_s3_bucket.site.arn}/events/pdfs/*",
          "${aws_s3_bucket.site.arn}/events/images/*"
        ]
      },
      {
        Effect   = "Allow",
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"],
        Resource = aws_dynamodb_table.member_metadata.arn
      },
      {
        Effect = "Allow",
        Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"],
        Resource = [
          aws_dynamodb_table.chat.arn,
          "${aws_dynamodb_table.chat.arn}/index/*"
        ]
      },
      {
        Effect   = "Allow",
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"],
        Resource = aws_dynamodb_table.mail_state.arn
      },
      {
        Effect = "Allow",
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail",
          "ses:SendBulkEmail"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "chime:CreateMeeting",
          "chime:CreateAttendee",
          "chime:DeleteMeeting",
          "chime:GetMeeting"
        ],
        Resource = "*"
      },
      {
        Effect   = "Allow",
        Action   = ["sqs:SendMessage"],
        Resource = aws_sqs_queue.chat_notifications.arn
      },
      {
        Effect = "Allow",
        Action = ["ssm:GetParameter", "ssm:GetParameters"],
        Resource = [
          aws_ssm_parameter.openai_api_key.arn,
          aws_ssm_parameter.openai_model.arn
        ]
      },
      {
        Effect   = "Allow",
        Action   = ["kms:Decrypt"],
        Resource = "*",
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com"
          }
        }
      },
      {
        Effect   = "Allow",
        Action   = ["cloudfront:CreateInvalidation"],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "cognito-idp:ListUsers",
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminAddUserToGroup",
          "cognito-idp:AdminRemoveUserFromGroup",
          "cognito-idp:AdminDisableUser",
          "cognito-idp:AdminEnableUser",
          "cognito-idp:AdminUpdateUserAttributes",
          "cognito-idp:AdminListGroupsForUser"
        ],
        Resource = aws_cognito_user_pool.members.arn
      }
    ]
  })
}

resource "aws_lambda_function" "member_files" {
  function_name    = "${local.name_prefix}-member-files"
  role             = aws_iam_role.lambda_role.arn
  handler          = "member_files.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.member_files_lambda.output_path
  source_code_hash = data.archive_file.member_files_lambda.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = merge({
      MEMBER_FILES_BUCKET                        = aws_s3_bucket.member_files.bucket
      MEMBER_FILES_PREFIX                        = var.member_files_prefix
      CHAT_TABLE                                 = aws_dynamodb_table.chat.name
      CHAT_NOTIFICATION_QUEUE_URL                = aws_sqs_queue.chat_notifications.id
      SITE_BUCKET                                = aws_s3_bucket.site.bucket
      SITE_DISTRIBUTION_ID                       = aws_cloudfront_distribution.site.id
      MEMBER_METADATA_TABLE                      = aws_dynamodb_table.member_metadata.name
      EMAIL_STATE_TABLE                          = aws_dynamodb_table.mail_state.name
      USER_POOL_ID                               = aws_cognito_user_pool.members.id
      SITE_BASE_URL                              = local.site_base_url
      SES_FROM_EMAIL                             = local.ses_from_email
      SES_REPLY_TO_EMAIL                         = local.ses_reply_to_email
      SES_CONFIGURATION_SET                      = aws_ses_configuration_set.club_mail.name
      WEBMAIL_ENABLED                            = tostring(var.enable_webmail)
      WEBMAIL_INBOUND_DOMAIN                     = local.webmail_inbound_domain
      WEBMAIL_UNMATCHED_MAILBOX_ADDRESS          = local.webmail_unmatched_mailbox_address
      WEBMAIL_UNMATCHED_POSITION_IDS             = join(",", var.webmail_unmatched_position_ids)
      ENABLE_ARTICLE_NOTIFICATIONS               = tostring(var.enable_article_notifications)
      ENABLE_EVENT_REMINDERS                     = tostring(var.enable_event_reminders)
      SYSTEM_EMAIL_MODE                          = var.system_email_mode
      SYSTEM_EMAIL_TEST_RECIPIENTS               = join(",", var.system_email_test_recipients)
      ENABLE_VEHICLE_REGISTRATION_PUSH_REMINDERS = tostring(var.enable_vehicle_registration_push_reminders)
      ENABLE_HISTORIC_REGISTRATION_REMINDERS     = tostring(var.enable_historic_registration_reminders)
      GEOAPIFY_GEOCODING_API_KEY                 = local.geoapify_geocoding_api_key
      GEOAPIFY_GEOCODING_URL                     = var.geoapify_geocoding_url
      OPENAI_API_KEY_PARAM                       = local.openai_api_key_param_name
      OPENAI_MODEL_PARAM                         = local.openai_model_param_name
      OPENAI_WEB_SEARCH_ENABLED                  = tostring(var.openai_web_search_enabled)
      ENABLE_LROC_MONTHLY_MEETINGS               = tostring(var.enable_lroc_monthly_meetings)
      CHIME_MEETINGS_ENABLED                     = tostring(var.enable_chime_meetings)
      }, var.enable_webmail_attachment_malware_protection ? {
      WM_SCAN = "true"
    } : {})
  }
}

resource "aws_iam_role" "notification_worker_role" {
  name = "${local.name_prefix}-chat-notification-worker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "notification_worker_basic" {
  role       = aws_iam_role.notification_worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "notification_worker" {
  name = "${local.name_prefix}-chat-notification-worker-inline"
  role = aws_iam_role.notification_worker_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:DeleteItem"],
        Resource = [aws_dynamodb_table.chat.arn, "${aws_dynamodb_table.chat.arn}/index/*"]
      },
      {
        Effect   = "Allow",
        Action   = ["cognito-idp:AdminListGroupsForUser"],
        Resource = aws_cognito_user_pool.members.arn
      },
      {
        Effect   = "Allow",
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"],
        Resource = aws_sqs_queue.chat_notifications.arn
      },
      {
        Effect = "Allow",
        Action = ["ssm:GetParameter", "ssm:GetParameters"],
        Resource = [
          aws_ssm_parameter.vapid_private_key.arn,
          aws_ssm_parameter.vapid_subject.arn
        ]
      },
      {
        Effect   = "Allow",
        Action   = ["kms:Decrypt"],
        Resource = "*",
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_lambda_function" "chat_notification_worker" {
  function_name    = "${local.name_prefix}-chat-notification-worker"
  role             = aws_iam_role.notification_worker_role.arn
  handler          = "notification_worker.handler"
  runtime          = "nodejs22.x"
  filename         = data.archive_file.notification_worker_lambda.output_path
  source_code_hash = data.archive_file.notification_worker_lambda.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      CHAT_TABLE                   = aws_dynamodb_table.chat.name
      USER_POOL_ID                 = aws_cognito_user_pool.members.id
      PUSH_VAPID_PRIVATE_KEY_PARAM = local.vapid_private_key_param_name
      PUSH_VAPID_SUBJECT_PARAM     = local.vapid_subject_param_name
      SITE_BASE_URL                = local.site_base_url
    }
  }
}

resource "aws_lambda_event_source_mapping" "chat_notification_queue" {
  event_source_arn = aws_sqs_queue.chat_notifications.arn
  function_name    = aws_lambda_function.chat_notification_worker.arn
  batch_size       = 10
  enabled          = true

  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_apigatewayv2_api" "member_api" {
  name          = "${local.name_prefix}-member-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers  = ["authorization", "content-type"]
    allow_methods  = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_origins  = local.allowed_origins
    expose_headers = ["content-type"]
    max_age        = 300
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.member_api.id
  authorizer_type  = "JWT"
  name             = "cognito-jwt"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.site.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.members.id}"
  }
}

resource "aws_apigatewayv2_integration" "member_files" {
  api_id                 = aws_apigatewayv2_api.member_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.member_files.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "list_files" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/files"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/files/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "download_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/files/download-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "delete_file" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "DELETE /member/files/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "publish_content" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/content/publish"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_expo_content_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/expo/content"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_expo_content_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/expo/content"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "public_articles" {
  api_id    = aws_apigatewayv2_api.member_api.id
  route_key = "GET /articles"
  target    = "integrations/${aws_apigatewayv2_integration.member_files.id}"
}

resource "aws_apigatewayv2_route" "public_magazines" {
  api_id    = aws_apigatewayv2_api.member_api.id
  route_key = "GET /magazines"
  target    = "integrations/${aws_apigatewayv2_integration.member_files.id}"
}


resource "aws_apigatewayv2_route" "member_magazines_upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/magazines/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_magazines_publish" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/magazines/publish"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "public_events" {
  api_id    = aws_apigatewayv2_api.member_api.id
  route_key = "GET /events"
  target    = "integrations/${aws_apigatewayv2_integration.member_files.id}"
}

resource "aws_apigatewayv2_route" "guest_chime_request" {
  api_id    = aws_apigatewayv2_api.member_api.id
  route_key = "POST /guest/chime/request"
  target    = "integrations/${aws_apigatewayv2_integration.member_files.id}"
}

resource "aws_apigatewayv2_route" "guest_chime_status_get" {
  api_id    = aws_apigatewayv2_api.member_api.id
  route_key = "GET /guest/chime/status"
  target    = "integrations/${aws_apigatewayv2_integration.member_files.id}"
}

resource "aws_apigatewayv2_route" "guest_chime_status_post" {
  api_id    = aws_apigatewayv2_api.member_api.id
  route_key = "POST /guest/chime/status"
  target    = "integrations/${aws_apigatewayv2_integration.member_files.id}"
}

resource "aws_apigatewayv2_route" "guest_chime_join" {
  api_id    = aws_apigatewayv2_api.member_api.id
  route_key = "POST /guest/chime/join"
  target    = "integrations/${aws_apigatewayv2_integration.member_files.id}"
}

resource "aws_apigatewayv2_route" "member_articles" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/articles"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "article_upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/articles/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "article_publish" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/articles/publish"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "article_download" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/articles/download"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_article_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/articles/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_event_info_upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events/info-upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_event_info_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events/info-delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_profile_metadata" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/profile-metadata"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicle_options" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/vehicle-options"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicles_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/vehicles"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicles_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/vehicles"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicles_historic_rego" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/vehicles/historic-rego"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "member_historic_registration_state" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/historic-registration"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_historic_registration_upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/historic-registration/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_historic_registration_submit" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/historic-registration/submit"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_historic_registration_process" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/historic-registration/process"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_historic_registration_vehicle_form_upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/historic-registration/vehicle-form/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_historic_registration_vehicle_record" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/historic-registration/vehicle-record"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicles_registration_response" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/vehicles/registration-response"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicles_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/vehicles/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "member_vehicle_maintenance_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/vehicle-maintenance"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicle_maintenance_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/vehicle-maintenance"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicle_maintenance_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/vehicle-maintenance/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_vehicle_help_suggest" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/vehicle-help/suggest"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_events_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/events"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_events_register" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/events/register"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_events_cancel" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/events/cancel"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_events_attendees_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/events/attendees"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_session_check" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/session-check"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_current" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/meeting-agenda/current"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_meeting" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/meeting"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_items" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/items"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_items_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/items/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_suggestions_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/meeting-agenda/suggestions"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_suggestions_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/suggestions"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_suggestions_add" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/suggestions/add"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_suggestions_dismiss" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/suggestions/dismiss"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_finalise" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/finalise"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_preview_pdf" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/preview-pdf"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_minutes_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/meeting-agenda/minutes"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_meeting_agenda_minutes_download" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/meeting-agenda/minutes/download-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_status" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/status"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_launch" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/launch"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "member_chime_mode" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/mode"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_join" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/join"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_end" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/end"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_attendance" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/attendance"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_attendance_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/attendance"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_guests_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/guests"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_guests_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/guests"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_chat_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/chat"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_chat_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/chat"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_control_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/control"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_control_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/control"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "member_chime_agenda_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/agenda"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_agenda_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/agenda"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_vote_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/vote"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_vote_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chime/vote"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chime_history" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chime/history"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_push_subscribe" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/push/subscribe"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_push_unsubscribe" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/push/unsubscribe"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_mailboxes" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/webmail/mailboxes"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_contacts" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/webmail/contacts"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_messages" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/webmail/messages"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_message_read" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/webmail/messages/{message_id}"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_send" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/webmail/send"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_archive" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/webmail/archive"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_attachment_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/webmail/attachment-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_webmail_attachment_upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/webmail/attachments/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_webmail_backfill_submissions" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/webmail/backfill-submissions"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_webmail_delete_message" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/webmail/messages/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_rooms_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chat/rooms"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_rooms_create" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_messages_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /member/chat/rooms/{room_id}/messages"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_messages_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/messages"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_attachment_upload_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/attachments/upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_attachment_complete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/attachments/complete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_attachment_download_url" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/attachments/download-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_join" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/join"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_notifications_mute" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/notifications/mute"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_notifications_unmute" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/notifications/unmute"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_leave" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/leave"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_chat_room_close" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/chat/rooms/{room_id}/close"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "member_profile_preferences" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /member/profile-preferences"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_metadata_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/member-metadata"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_metadata_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/member-metadata"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_create" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/members/create"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_resend_invite" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/members/resend-invite"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "admin_member_count" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/members/count"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_import_preview" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/members/import-preview"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_import_commit" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/members/import-commit"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "admin_member_import_history" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/members/import-history"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_import_rollback" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/members/import-rollback"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_disable" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/members/disable"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_restore" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/members/restore"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_email_test" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/email/test"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "admin_email_audience" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/email/audience"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_email_positions" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/email/positions"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_positions_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/positions"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_positions_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/positions"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_positions_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/positions/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}


resource "aws_apigatewayv2_route" "admin_landrover_parts_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/landrover-parts"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_landrover_parts_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/landrover-parts"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_landrover_parts_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/landrover-parts/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_vehicle_options_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/vehicle-options"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_vehicle_options_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/vehicle-options"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_event_options_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/event-options"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_event_options_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/event-options"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_structured_events_get" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "GET /admin/events"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_structured_events_post" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_structured_events_delete" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events/delete"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_structured_events_short_descriptions" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events/short-descriptions"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_structured_events_image_upload" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events/image-upload-url"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_structured_events_seed_meetings" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events/seed-meetings"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_maps_geocode" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/maps/geocode"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_member_roles" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/member-roles"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_email_send_test" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/email/send-test"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_email_send_bulk" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/email/send-bulk"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_email_suppress" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/email/suppress"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_email_clear_suppression" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/email/clear-suppression"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_event_reminders_run" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/events/reminders/run"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "admin_vehicle_registration_reminders_run" {
  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = "POST /admin/vehicles/registration-reminders/run"
  target             = "integrations/${aws_apigatewayv2_integration.member_files.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.member_api.id
  name        = "$default"
  auto_deploy = true
}


resource "aws_lambda_permission" "allow_ses_bounce_sns" {
  statement_id  = "AllowExecutionFromSesBounceSns"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.member_files.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.ses_bounces.arn
}

resource "aws_lambda_permission" "allow_ses_complaint_sns" {
  statement_id  = "AllowExecutionFromSesComplaintSns"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.member_files.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.ses_complaints.arn
}

resource "aws_sns_topic_subscription" "ses_bounces_member_files" {
  topic_arn = aws_sns_topic.ses_bounces.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.member_files.arn
}

resource "aws_sns_topic_subscription" "ses_complaints_member_files" {
  topic_arn = aws_sns_topic.ses_complaints.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.member_files.arn
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.member_files.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.member_api.execution_arn}/*/*"
}

resource "aws_iam_role" "scheduler_invoke_lambda" {
  name = "${local.name_prefix}-scheduler-invoke-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "scheduler.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  name = "${local.name_prefix}-scheduler-invoke-lambda"
  role = aws_iam_role.scheduler_invoke_lambda.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["lambda:InvokeFunction"],
        Resource = aws_lambda_function.member_files.arn
      }
    ]
  })
}

resource "aws_scheduler_schedule" "event_reminders_daily" {
  name                         = "${local.name_prefix}-event-reminders-daily"
  description                  = "Run the LROC event reminder email scan once per day."
  schedule_expression          = var.event_reminder_schedule_expression
  schedule_expression_timezone = var.event_reminder_schedule_timezone
  state                        = var.enable_event_reminders ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.member_files.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda.arn
    input = jsonencode({
      action = "event_reminders"
    })
  }
}

resource "aws_scheduler_schedule" "vehicle_registration_reminders_daily" {
  name                         = "${local.name_prefix}-vehicle-registration-reminders-daily"
  description                  = "Run the LROC member vehicle registration PWA reminder scan once per day."
  schedule_expression          = var.vehicle_registration_reminder_schedule_expression
  schedule_expression_timezone = var.vehicle_registration_reminder_schedule_timezone
  state                        = var.enable_vehicle_registration_push_reminders ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.member_files.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda.arn
    input = jsonencode({
      action = "vehicle_registration_reminders"
    })
  }
}

resource "aws_scheduler_schedule" "webmail_spam_purge_daily" {
  name                         = "${local.name_prefix}-webmail-spam-purge-daily"
  description                  = "Purge quarantined inbound webmail after the configured retention period."
  schedule_expression          = var.webmail_spam_purge_schedule_expression
  schedule_expression_timezone = var.webmail_spam_purge_schedule_timezone
  state                        = var.enable_webmail ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.member_files.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda.arn
    input = jsonencode({
      action = "webmail_spam_purge"
    })
  }
}

