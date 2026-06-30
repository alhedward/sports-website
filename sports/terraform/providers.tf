provider "aws" {
  region = var.aws_region
}

# CloudFront can use an ACM certificate only when the certificate is in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
