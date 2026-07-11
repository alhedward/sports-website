data "aws_caller_identity" "current" {}

data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  account_id        = data.aws_caller_identity.current.account_id
  state_bucket_name = var.state_bucket_name != "" ? var.state_bucket_name : "${var.state_bucket_prefix}-${local.account_id}"
  name_prefix       = "${var.project_name}-${var.environment}"

  github_subjects = [
    for branch in var.github_branches : "repo:${var.github_owner}/${var.github_repo}:ref:refs/heads/${branch}"
  ]

  common_tags = merge({
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Component   = "bootstrap"
  }, var.tags)

  site_bucket_arn_pattern = "arn:aws:s3:::${local.name_prefix}-site-*"

  route53_hosted_zone_resources = var.allow_broad_route53 ? ["*"] : var.route53_hosted_zone_arns
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = local.state_bucket_name

  tags = merge(local.common_tags, {
    Name    = local.state_bucket_name
    Purpose = "Sports Terraform remote state"
  })
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]

  tags = merge(local.common_tags, {
    Name    = "github-actions-oidc"
    Purpose = "GitHub Actions OIDC trust provider"
  })
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.github_subjects
    }
  }
}

resource "aws_iam_role" "github_actions_deploy" {
  name               = var.deploy_role_name
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json

  tags = merge(local.common_tags, {
    Name    = var.deploy_role_name
    Purpose = "Sports GitHub Actions Terraform deployment"
  })
}

data "aws_iam_policy_document" "github_actions_deploy" {
  statement {
    sid    = "ReadCallerIdentity"
    effect = "Allow"
    actions = [
      "sts:GetCallerIdentity",
      "s3:ListAllMyBuckets"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageTerraformStateBucket"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:CreateBucket",
      "s3:PutBucketVersioning",
      "s3:GetBucketVersioning",
      "s3:PutEncryptionConfiguration",
      "s3:GetEncryptionConfiguration",
      "s3:PutBucketPublicAccessBlock",
      "s3:GetBucketPublicAccessBlock",
      "s3:DeleteBucketPublicAccessBlock",
      "s3:PutBucketTagging",
      "s3:GetBucketTagging",
      "s3:DeleteBucketTagging",
      "s3:DeleteBucketEncryption"
    ]
    resources = [aws_s3_bucket.terraform_state.arn]
  }

  statement {
    sid    = "ReadWriteTerraformStateObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:GetObjectVersion"
    ]
    resources = [
      "${aws_s3_bucket.terraform_state.arn}/*"
    ]
  }

  statement {
    sid    = "ManageSportsSiteBuckets"
    effect = "Allow"
    actions = [
      "s3:CreateBucket",
      "s3:DeleteBucket",
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:GetBucketPolicy",
      "s3:PutBucketPolicy",
      "s3:DeleteBucketPolicy",
      "s3:GetBucketPublicAccessBlock",
      "s3:PutBucketPublicAccessBlock",
      "s3:DeleteBucketPublicAccessBlock",
      "s3:GetBucketVersioning",
      "s3:PutBucketVersioning",
      "s3:GetEncryptionConfiguration",
      "s3:PutEncryptionConfiguration",
      "s3:DeleteBucketEncryption",
      "s3:GetBucketTagging",
      "s3:PutBucketTagging",
      "s3:DeleteBucketTagging",
      "s3:PutBucketWebsite",
      "s3:GetBucketWebsite",
      "s3:DeleteBucketWebsite"
    ]
    resources = [local.site_bucket_arn_pattern]
  }

  statement {
    sid    = "ManageSportsSiteObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:GetObjectVersion",
      "s3:PutObjectTagging",
      "s3:GetObjectTagging"
    ]
    resources = ["${local.site_bucket_arn_pattern}/*"]
  }

  statement {
    sid    = "ManageSportsDynamoDbTables"
    effect = "Allow"
    actions = [
      "dynamodb:CreateTable",
      "dynamodb:DeleteTable",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeContinuousBackups",
      "dynamodb:UpdateContinuousBackups",
      "dynamodb:UpdateTable",
      "dynamodb:UpdateTimeToLive",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:ListTagsOfResource",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan",
      "dynamodb:Query",
      "dynamodb:BatchWriteItem"
    ]
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${local.name_prefix}-*"
    ]
  }

  statement {
    sid    = "ManageSportsLambdas"
    effect = "Allow"
    actions = [
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:GetFunction",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetPolicy",
      "lambda:ListTags",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:PublishVersion",
      "lambda:ListVersionsByFunction",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:InvokeFunction"
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${local.account_id}:function:${local.name_prefix}-*"
    ]
  }

  statement {
    sid    = "ManageSportsLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DescribeLogGroups",
      "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy",
      "logs:ListTagsForResource",
      "logs:TagResource",
      "logs:UntagResource"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageSportsLambdaIamRoles"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:PassRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:GetRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:TagRole",
      "iam:UntagRole"
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${local.name_prefix}-*"
    ]
  }

  statement {
    sid    = "ReadAwsManagedLambdaPolicies"
    effect = "Allow"
    actions = [
      "iam:GetPolicy",
      "iam:GetPolicyVersion"
    ]
    resources = [
      "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    ]
  }


  statement {
    sid    = "ManageHttpApiGateway"
    effect = "Allow"
    actions = [
      "apigateway:*"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageCloudFront"
    effect = "Allow"
    actions = [
      "cloudfront:*"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageAcmCertificatesForCloudFront"
    effect = "Allow"
    actions = [
      "acm:*"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ListRoute53HostedZonesAndChanges"
    effect = "Allow"
    actions = [
      "route53:GetHostedZoneCount",
      "route53:ListHostedZones",
      "route53:ListHostedZonesByName",
      "route53:GetChange"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageRoute53HostedZoneRecords"
    effect = "Allow"
    actions = [
      "route53:GetHostedZone",
      "route53:ListResourceRecordSets",
      "route53:ChangeResourceRecordSets",
      "route53:ListTagsForResource",
      "route53:ChangeTagsForResource"
    ]
    resources = local.route53_hosted_zone_resources
  }

  statement {
    sid    = "ManageSportsCognitoAdminPool"
    effect = "Allow"
    actions = [
      "cognito-idp:*"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageEventBridgeIngestSchedule"
    effect = "Allow"
    actions = [
      "events:PutRule",
      "events:DescribeRule",
      "events:DeleteRule",
      "events:EnableRule",
      "events:DisableRule",
      "events:PutTargets",
      "events:RemoveTargets",
      "events:ListTargetsByRule",
      "events:ListTagsForResource",
      "events:TagResource",
      "events:UntagResource"
    ]
    resources = [
      "arn:aws:events:${var.aws_region}:${local.account_id}:rule/${local.name_prefix}-*"
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name   = "SportsGithubActionsDeployAccess"
  role   = aws_iam_role.github_actions_deploy.id
  policy = data.aws_iam_policy_document.github_actions_deploy.json
}
