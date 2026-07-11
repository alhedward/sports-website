locals {
  admin_cognito_domain_prefix = var.admin_cognito_domain_prefix != "" ? var.admin_cognito_domain_prefix : substr("${local.name_prefix}-admin-${data.aws_caller_identity.current.account_id}", 0, 63)
}

resource "aws_cognito_user_pool" "admin" {
  name = "${local.name_prefix}-admin-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = false
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = merge(local.common_tags, {
    Purpose = "Local admin app authentication"
  })
}

resource "aws_cognito_user_pool_client" "admin" {
  name         = "${local.name_prefix}-admin-local-app"
  user_pool_id = aws_cognito_user_pool.admin.id

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = distinct(concat(var.admin_callback_urls, ["${local.public_site_url}/admin/"]))
  logout_urls                          = distinct(concat(var.admin_logout_urls, ["${local.public_site_url}/admin/"]))
  supported_identity_providers         = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_pool_domain" "admin" {
  domain       = local.admin_cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.admin.id
}

resource "aws_cognito_user_group" "primary_admins" {
  name         = "PrimaryAdmins"
  user_pool_id = aws_cognito_user_pool.admin.id
  description  = "Owner-level administrators who can manage admin users and recovery tasks."
  precedence   = 1
}

resource "aws_cognito_user_group" "admins" {
  name         = "Admins"
  user_pool_id = aws_cognito_user_pool.admin.id
  description  = "Administrators who can manage curated sports catalogue data."
  precedence   = 10
}

resource "aws_cognito_user_group" "editors" {
  name         = "Editors"
  user_pool_id = aws_cognito_user_pool.admin.id
  description  = "Editors who can review and manage curated sports catalogue data."
  precedence   = 20
}
