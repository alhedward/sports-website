variable "aws_region" {
  description = "AWS region where the Sports stack and Terraform state bucket will be created."
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Project name used by the main Sports Terraform stack."
  type        = string
  default     = "sports-aggregator"
}

variable "environment" {
  description = "Environment name used by the main Sports Terraform stack. Use dev, prod, staging, etc."
  type        = string
  default     = "dev"
}

variable "state_bucket_prefix" {
  description = "Prefix used to derive a globally unique Terraform state bucket name when state_bucket_name is blank."
  type        = string
  default     = "sports-vk2ale-terraform-state"
}

variable "state_bucket_name" {
  description = "Explicit Terraform state bucket name. Leave blank to use state_bucket_prefix-account_id."
  type        = string
  default     = ""
}

variable "state_key" {
  description = "Default Terraform state key for the GitHub Actions workflow."
  type        = string
  default     = "sports/dev/terraform.tfstate"
}

variable "github_owner" {
  description = "GitHub repository owner or organisation that may assume the deploy role."
  type        = string
  default     = "alhedward"
}

variable "github_repo" {
  description = "GitHub repository name that may assume the deploy role."
  type        = string
  default     = "sports-website"
}

variable "github_branches" {
  description = "Branch names allowed to assume the deploy role."
  type        = list(string)
  default     = ["main", "master"]
}

variable "deploy_role_name" {
  description = "IAM role name that GitHub Actions will assume through OIDC."
  type        = string
  default     = "sports-github-actions-deploy"
}

variable "route53_hosted_zone_arns" {
  description = "Optional Route 53 hosted zone ARNs to restrict DNS changes. Leave empty to allow the deploy role to manage Route 53 records account-wide."
  type        = list(string)
  default     = []
}

variable "allow_broad_route53" {
  description = "Allow account-wide Route 53 permissions. Keep true for simple bootstrap; set false and provide route53_hosted_zone_arns for tighter production scoping."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags applied to bootstrap resources."
  type        = map(string)
  default     = {}
}
