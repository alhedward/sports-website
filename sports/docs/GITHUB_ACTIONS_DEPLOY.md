# GitHub Actions deployment

This repo ships a GitHub Actions workflow at the repository root:

```text
.github/workflows/sports-validate.yml
```

The workflow has two jobs:

1. `validate` — runs on pushes, pull requests, and manual dispatch.
2. `deploy` — runs after validation for pushes to `main`/`master` and manual dispatch. It does not run for pull requests.

Normal deploys do **not** seed DynamoDB. The seed/ingest Lambda is only invoked when the workflow is manually dispatched with `seed_database` set to `true`.

## Required GitHub settings

Create these under **Repository → Settings → Secrets and variables → Actions**.

### Secret

| Name | Example | Purpose |
|---|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::123456789012:role/sports-github-actions-deploy` | IAM role GitHub Actions assumes via OIDC. |

### Variables

| Name | Example | Purpose |
|---|---|---|
| `TF_STATE_BUCKET` | `sports-vk2ale-terraform-state-123456789012` | S3 bucket used for Terraform remote state. Must be globally unique. The workflow can create it if the role has permission. |
| `AWS_REGION` | `ap-southeast-2` | AWS region for regional resources. |
| `TF_STATE_KEY` | `sports/dev/terraform.tfstate` | Object key for Terraform state. |
| `CUSTOM_DOMAIN_NAME` | `sports.vk2ale.com` | Public site domain. |
| `CORS_ALLOW_ORIGIN` | `https://sports.vk2ale.com` | API CORS origin. |
| `ROUTE53_ZONE_NAME` | `vk2ale.com` | Route 53 public hosted zone name. |
| `CREATE_ROUTE53_RECORDS` | `true` | Set `false` only if DNS is managed outside Route 53. |
| `ENABLE_DAILY_INGEST_SCHEDULE` | `false` | Leave `false` for curated/community data. Set `true` only if the ingest Lambda has been replaced with a safe licensed updater. |

Only `TF_STATE_BUCKET` is strictly required as a repository variable. The others have safe defaults for the POC.


## Bootstrap Terraform for new AWS accounts

For a clean dev/prod AWS account, first run the bootstrap layer locally with owner/admin credentials:

```bash
cd sports/terraform-bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

The bootstrap layer creates:

- the Terraform state S3 bucket
- the GitHub Actions OIDC provider
- the `sports-github-actions-deploy` IAM role
- the deploy policy needed for S3, CloudFront, ACM, Route 53, DynamoDB, Lambda, API Gateway, IAM, EventBridge, logs, and Cognito

Use `terraform output` from `sports/terraform-bootstrap` to populate GitHub Actions settings. For production later, set `environment = "prod"` and use a separate state key such as `sports/prod/terraform.tfstate`.

## AWS OIDC role

Create an IAM role that trusts GitHub's OIDC provider and allows the specific repository/branch to assume the role.

A trust policy shape looks like this; replace `OWNER/REPO` and branch names as needed:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:OWNER/REPO:ref:refs/heads/main",
            "repo:OWNER/REPO:ref:refs/heads/master"
          ]
        }
      }
    }
  ]
}
```

The preferred repeatable path is to create this role with `sports/terraform-bootstrap`. That bootstrap layer includes a scoped deploy policy for:

- S3 state bucket bootstrap and website object uploads
- CloudFront distribution, origin access control, and invalidations
- ACM certificates in `us-east-1`
- Route 53 validation and alias records
- DynamoDB tables
- Lambda functions and permissions
- API Gateway HTTP API
- Cognito user pool, hosted-login domain, app client and groups
- IAM Lambda execution role and policies
- EventBridge schedule/rules if daily ingest is enabled
- CloudWatch Logs

## Deployment behaviour

The deploy job:

1. Assumes the AWS role using GitHub OIDC.
2. Creates or secures the Terraform state bucket.
3. Runs `terraform init` with the S3 backend.
4. Runs `terraform plan` and `terraform apply`.
5. Skips seed/ingest by default so existing DynamoDB content and community-approved edits are preserved.
6. If manually dispatched with `seed_database=true`, invokes the ingest Lambda and upserts packaged starter data by id.
7. Invalidates the CloudFront cache.
8. Writes the site/API URLs and Cognito admin config to the GitHub Actions step summary.


## Seed/ingest safety

The packaged seed data is starter content, not the live source of truth after community/admin edits begin. A normal redeploy must not reseed the database.

To seed deliberately, run the workflow manually and set:

```text
seed_database = true
```

Only use that for a brand-new environment, first bootstrap, or an intentional curated-data reset. The ingest Lambda upserts records by `id`, so records with matching ids can be overwritten. Public suggestions and activity-log entries are separate tables, but approved records in curated tables can still be overwritten if they share ids with packaged seed data.

## Local helper interaction

The local deployment helper copies this workflow into the repository root `.github/workflows/` directory and commits it along with the `sports/` site package. After the helper pushes, it can watch the GitHub Actions run through the GitHub CLI.
