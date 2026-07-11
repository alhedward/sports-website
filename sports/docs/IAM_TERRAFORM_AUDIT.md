# IAM and Terraform audit

Version: 0.7.12-terraform-iam-audit

This project now keeps the repeatable deployment IAM surface in Terraform rather than relying on one-off console/CLI patches.

## Code-owned roles and policies

- `sports/terraform-bootstrap/` creates the GitHub Actions OIDC provider, Terraform state bucket, and `sports-github-actions-deploy` role.
- `sports/terraform-bootstrap/main.tf` grants the deploy role permissions for the main stack: S3 state/site buckets, DynamoDB, Lambda, Lambda IAM role/pass-role, API Gateway, CloudFront, ACM, Route 53, Cognito, EventBridge, and CloudWatch Logs.
- `sports/terraform/lambda.tf` creates the Lambda execution role and its DynamoDB access policy.

## Deliberate split

The bootstrap stack is still run once with owner/admin AWS credentials in a new AWS account. After that, GitHub Actions assumes the Terraform deploy role by OIDC. This avoids storing long-lived AWS access keys in GitHub.

## Notes

- Normal application redeploys do not reseed DynamoDB. Seeding is a manual workflow dispatch option only.
- `boto3_direct` mode in the admin app remains an owner/bootstrap mode. Normal administration should use Cognito/API mode.
- For an existing manually-created dev deploy role, either attach/import the bootstrap-managed policy or recreate the role through the bootstrap stack before relying on a fresh-account production deployment.
