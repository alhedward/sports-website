variable "aws_region" {
  description = "AWS region for regional resources. CloudFront remains global."
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Project name used in AWS resource naming."
  type        = string
  default     = "sports-aggregator"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "lambda_runtime" {
  description = "Python runtime for Lambda."
  type        = string
  default     = "python3.13"
}

variable "cors_allow_origin" {
  description = "Allowed CORS origin for API responses. For this POC, the default is the sports.vk2ale.com frontend origin."
  type        = string
  default     = "https://sports.vk2ale.com"
}

variable "custom_domain_name" {
  description = "Optional custom domain name for the CloudFront site. Leave blank to use the default CloudFront domain."
  type        = string
  default     = "sports.vk2ale.com"
}

variable "route53_zone_name" {
  description = "Route 53 public hosted zone name used to validate the certificate and create the alias record."
  type        = string
  default     = "vk2ale.com"
}

variable "create_route53_records" {
  description = "Whether Terraform should create DNS validation and site alias records in Route 53. Keep true for the vk2ale.com POC when the public hosted zone is in this AWS account."
  type        = bool
  default     = true
}

variable "enable_daily_ingest_schedule" {
  description = "Whether to run the seed/ingest Lambda once per day."
  type        = bool
  default     = false
}
