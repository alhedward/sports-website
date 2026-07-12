# Sports.vk2ale — community sports aggregator POC

`Sports.vk2ale` is a serverless proof-of-concept for a sports aggregator site with one main purpose:

> Help people find a way into sport — whatever their age, background, ability, budget, confidence level, or role.

The site is intentionally not just an elite-stats database. It links visitors to official sporting bodies, inclusive participation resources, major international event hubs, and pathway starters for players, fans, families, volunteers, officials and coaches.

## What is included

- Static frontend hosted from private S3 through CloudFront.
- Custom-domain-ready Terraform for `sports.vk2ale.com`.
- API Gateway HTTP API backed by Python Lambda.
- DynamoDB tables for tournaments, pathway profiles, top-player spotlights, public suggestions, event hubs, official sporting bodies and the admin activity log.
- Python ingest Lambda for curated public-link seed data.
- Sponsor-ready placements, deliberately empty until partners are approved.
- Moderated public suggestion endpoint so users can help grow the curated directory without auto-publishing unverified links.
- Sports-aware deployment helper layout: top-level `sports/` folder and `sports/file.deploy.txt`.


## PrimaryAdmin device approval

When an existing admin account attempts to sign in from a new browser or device, the pre-login check records a pending device request instead of allowing Cognito login. A signed-in member of the `PrimaryAdmins` Cognito group can review the request under **Admin → Devices**, then approve or reject it. Approval expires after 30 minutes if the requesting device does not complete Cognito login. Successful login activates the device.

Protected admin API calls now include the browser-generated `X-Admin-Device-Id` header and Lambda verifies that the device is active, in addition to API Gateway JWT validation and Cognito group checks.

## Deploy with your helper

Use the sports-aware helper:

```bash
python3 deploy_helper_sports.py
```

Select this package ZIP. The helper should detect the `sports/` context, use `sports/file.deploy.txt`, copy the folder into your repo, validate what it can, commit and push.

## Deploy directly with Terraform

```bash
cd sports/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Seed DynamoDB only for first bootstrap or a deliberate curated-data reset:

```bash
aws lambda invoke \
  --function-name "$(terraform output -raw ingest_lambda_name)" \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  /tmp/sports-seed-response.json

cat /tmp/sports-seed-response.json
```

Normal redeploys must not run seed/ingest, because the live DynamoDB tables can contain community-approved edits that should not be overwritten by packaged starter data.

Open the site:

```bash
terraform output -raw site_url
```

## Data model

- `sport_bodies`: official sporting-body and participation-resource links.
- `tournaments`: major upcoming international event hubs.
- `events`: official event/milestone links attached to tournaments.
- `players`: now used as pathway profiles for this POC, rather than celebrity/player stats.
- `top_players`: sport-genre spotlight cards for elite inspiration.
- `suggestions`: moderated public suggestions waiting for review before publication.
- `activity_log`: shared site-side audit log for local admin app sessions and changes.

## Curated directory update

This package expands the official body directory with Cricket Australia / Play Cricket, Motorsport Australia, FIA, Motorcycling Australia, Karting Australia, the Australian Power Boat Association, Australian Sailing / Discover Sailing, World Sailing, and accessible Sailability pathways. It also adds top-player spotlight cards for cricket, motorsport, sailing, football and basketball.

## PWA support

The public site is installable as a Progressive Web App. The package includes:

- `site/manifest.webmanifest` for install metadata, app name, theme colour, shortcuts and icons.
- `site/sw.js` for service-worker caching of the app shell and a network-first cached fallback for read-only API calls.
- `site/offline.html` as the offline fallback page.
- PNG icons under `site/icons/`, including a maskable 512px icon.
- An install button that appears only when the browser exposes the PWA install prompt.

The public PWA does not add login or admin capability; admin management stays outside the public site. The current admin path is the local Tkinter app using Cognito hosted login plus the protected admin API, with boto3 direct mode retained only as an owner/emergency fallback.

## Commercial direction

The POC includes sponsor slots but no live ad network code. That is deliberate. This keeps the first release clean and lets you define a sponsor policy before monetising.

Good long-run revenue options:

1. foundation sponsors,
2. local community sponsor slots,
3. clearly labelled affiliate/referral links,
4. event ticket/hospitality referral partnerships where permitted,
5. sponsored “get involved” guides,
6. ethical display advertising later.

Avoid anything that undermines the mission, especially gambling-heavy ads, misleading performance products, exploitative financial products, or anything that makes participation feel less accessible.

## GitHub Actions

The workflow is staged at the package root as `.github/workflows/sports-validate.yml`, not inside `sports/.github`. During deployment, `sports/file.deploy.txt` copies it into the repository root so GitHub can discover it.

## GitHub Actions deployment

The package includes a CI/CD workflow at the package root under `.github/workflows/sports-validate.yml`. The deploy helper copies that workflow into the repository root so GitHub can discover it.

To allow Actions to deploy to AWS, configure:

- Secret: `AWS_ROLE_ARN`
- Variable: `TF_STATE_BUCKET`

Optional variables such as `AWS_REGION`, `CUSTOM_DOMAIN_NAME`, `ROUTE53_ZONE_NAME`, and `CREATE_ROUTE53_RECORDS` are documented in `docs/GITHUB_ACTIONS_DEPLOY.md`.

The deploy job validates, applies Terraform, and invalidates CloudFront. It does **not** seed DynamoDB during normal redeploys. Seed/ingest is available only as an explicit manual workflow-dispatch option for first bootstrap or deliberate reset.

## Community-assisted growth

The frontend includes a `Suggest an official sporting body or pathway` form. Submissions go to the `suggestions` table as `pending_review`; they are not added to the public directory until reviewed. The recommended OpenAI-assisted research workflow is documented in `docs/COMMUNITY_DISCOVERY_PIPELINE.md`.

Current version: 0.7.21-primaryadmin-device-approval

## UX polish

The public PWA includes a section drawer and floating back-to-top control for quicker navigation on long mobile pages.

## AWS bootstrap for a fresh account

Before GitHub Actions can deploy the stack in a new AWS account, run the bootstrap Terraform layer once with owner/admin AWS credentials:

```bash
cd sports/terraform-bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

That creates the Terraform state bucket, GitHub OIDC provider, and `sports-github-actions-deploy` role, including Cognito deployment permissions. Use its outputs to set the GitHub Actions secret `AWS_ROLE_ARN` and variables such as `TF_STATE_BUCKET`, `TF_STATE_KEY`, `AWS_REGION`, `TF_PROJECT_NAME`, and `TF_ENVIRONMENT`. See `sports/terraform-bootstrap/README.md` for prod-account notes.

## Local admin manager

This package includes a Tkinter admin manager at:

```bash
python3 sports/admin_manager/sports_admin_manager.py
```

Default mode is now **Cognito API mode**:

```text
local admin app → Cognito hosted login → protected /admin API → Lambda → DynamoDB
```

That lets delegated admins manage suggestions and curated records without receiving AWS credentials. The public website still has no login button and no admin view.

After deploy, get the connection settings from Terraform:

```bash
terraform -chdir=sports/terraform output -raw admin_api_base_url
terraform -chdir=sports/terraform output -raw admin_cognito_domain_url
terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_client_id
terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_id
```

Create the first admin user with the owner-only helper:

```bash
python3 sports/admin_manager/cognito_user_manager.py create \
  --user-pool-id "$(terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_id)" \
  --email "you@example.com" \
  --group PrimaryAdmins
```

Run the admin manager, fill in the Admin API, Cognito domain and client ID fields, then click **Login / connect**. The app opens Cognito hosted login in your browser and listens on `http://localhost:8765/callback` for the dev callback.

The legacy `boto3_direct` mode remains available for the primary owner as an emergency fallback, but normal delegated admins should use Cognito API mode.

Install local requirements when needed:

```bash
python3 -m pip install -r sports/admin_manager/requirements.txt
sudo apt install python3-tk
```

MFA is intentionally off in this dev build. TOTP/WebAuthn can be added later without putting login controls on the public PWA.


### 0.7.9 admin app update

The admin app now shows AWS profiles in a dropdown. Leaving the AWS profile field blank uses the default boto3 credential chain; selecting a named profile uses that local AWS profile. The selected profile is saved in `~/.sports-vk2ale-admin-manager.json`.


## Admin PWA

The browser/PWA admin console is available at `/admin/` after deployment. It uses the Cognito-backed admin API and does not use the local boto3 direct pathway. See `docs/ADMIN_PWA.md`.
