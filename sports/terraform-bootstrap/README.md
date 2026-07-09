# Sports AWS bootstrap Terraform

This folder creates the AWS account-level pieces needed before the normal GitHub Actions deployment can run in a clean account:

- S3 bucket for Terraform remote state
- GitHub Actions OIDC provider
- GitHub Actions deploy role
- Deploy-role policy for the Sports stack, including Cognito

The main application stack remains in:

```text
sports/terraform
```

Use this bootstrap layer once per AWS account/environment, from a local shell with normal AWS admin credentials. After that, GitHub Actions assumes the generated role and deploys the main stack.

## Why this is separate

The GitHub deploy role cannot reliably create or expand its own permissions in a brand-new account. Bootstrap is the clean first step: owner/admin credentials create the deploy role, then the CI/CD role runs the normal Terraform stack.

## Dev bootstrap

```bash
cd ~/git/sports-website/sports/terraform-bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
terraform output
```

Put these outputs into GitHub Actions settings:

```text
Secret:
  AWS_ROLE_ARN = deploy_role_arn

Variables:
  TF_STATE_BUCKET = terraform_state_bucket
  TF_STATE_KEY    = terraform_state_key
  AWS_REGION      = aws_region
  TF_PROJECT_NAME = project_name value
  TF_ENVIRONMENT  = environment value
```

The existing workflow also uses these variables for the public site:

```text
CUSTOM_DOMAIN_NAME
CORS_ALLOW_ORIGIN
ROUTE53_ZONE_NAME
CREATE_ROUTE53_RECORDS
ENABLE_DAILY_INGEST_SCHEDULE
```

## Prod bootstrap later

For a production AWS account, copy the example vars and change at least:

```hcl
environment = "prod"
state_key   = "sports/prod/terraform.tfstate"
```

You will also usually set production GitHub variables such as:

```text
TF_ENVIRONMENT=prod
CUSTOM_DOMAIN_NAME=sports.example.com
CORS_ALLOW_ORIGIN=https://sports.example.com
ROUTE53_ZONE_NAME=example.com
CREATE_ROUTE53_RECORDS=true
```

## Existing dev account note

If you already created the GitHub OIDC provider or deploy role manually, this bootstrap stack may need Terraform imports before it can manage those exact resources. For the current dev account, the quick fix is still to attach the missing Cognito permission manually. For a fresh prod account, use this bootstrap layer first.
