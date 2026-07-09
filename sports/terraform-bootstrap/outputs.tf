output "aws_account_id" {
  description = "AWS account ID bootstrapped by this stack."
  value       = data.aws_caller_identity.current.account_id
}

output "deploy_role_arn" {
  description = "GitHub Actions IAM role ARN. Store this in GitHub Actions secret AWS_ROLE_ARN."
  value       = aws_iam_role.github_actions_deploy.arn
}

output "terraform_state_bucket" {
  description = "S3 bucket for Terraform remote state. Store this in GitHub Actions variable TF_STATE_BUCKET."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "terraform_state_key" {
  description = "Suggested Terraform state key. Store this in GitHub Actions variable TF_STATE_KEY."
  value       = var.state_key
}

output "aws_region" {
  description = "AWS region for GitHub Actions variable AWS_REGION."
  value       = var.aws_region
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC provider ARN created by the bootstrap stack."
  value       = aws_iam_openid_connect_provider.github_actions.arn
}

output "github_actions_subjects" {
  description = "GitHub OIDC subject claims allowed to assume the deploy role."
  value       = local.github_subjects
}

output "github_actions_setup_hint" {
  description = "Values to put in GitHub Actions settings."
  value = {
    secret_AWS_ROLE_ARN = aws_iam_role.github_actions_deploy.arn
    var_TF_STATE_BUCKET = aws_s3_bucket.terraform_state.bucket
    var_TF_STATE_KEY    = var.state_key
    var_AWS_REGION      = var.aws_region
    var_TF_PROJECT_NAME = var.project_name
    var_TF_ENVIRONMENT  = var.environment
  }
}
