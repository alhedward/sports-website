# Sports.vk2ale — community sports aggregator POC

`Sports.vk2ale` is a serverless proof-of-concept for a sports aggregator site with one main purpose:

> Help people find a way into sport — whatever their age, background, ability, budget, confidence level, or role.

The site is intentionally not just an elite-stats database. It links visitors to official sporting bodies, inclusive participation resources, major international event hubs, and pathway starters for players, fans, families, volunteers, officials and coaches.

## What is included

- Static frontend hosted from private S3 through CloudFront.
- Custom-domain-ready Terraform for `sports.vk2ale.com`.
- API Gateway HTTP API backed by Python Lambda.
- DynamoDB tables for tournaments, pathway profiles, top-player spotlights, public suggestions, event hubs and official sporting bodies.
- Python ingest Lambda for curated public-link seed data.
- Sponsor-ready placements, deliberately empty until partners are approved.
- Moderated public suggestion endpoint so users can help grow the curated directory without auto-publishing unverified links.
- Sports-aware deployment helper layout: top-level `sports/` folder and `sports/file.deploy.txt`.

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

Seed DynamoDB:

```bash
aws lambda invoke   --function-name "$(terraform output -raw ingest_lambda_name)"   --cli-binary-format raw-in-base64-out   --payload '{}'   /tmp/sports-seed-response.json

cat /tmp/sports-seed-response.json
```

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

## Curated directory update

This package expands the official body directory with Cricket Australia / Play Cricket, Motorsport Australia, FIA, Motorcycling Australia, Karting Australia, the Australian Power Boat Association, Australian Sailing / Discover Sailing, World Sailing, and accessible Sailability pathways. It also adds top-player spotlight cards for cricket, motorsport, sailing, football and basketball.

## PWA support

The public site is installable as a Progressive Web App. The package includes:

- `site/manifest.webmanifest` for install metadata, app name, theme colour, shortcuts and icons.
- `site/sw.js` for service-worker caching of the app shell and a network-first cached fallback for read-only API calls.
- `site/offline.html` as the offline fallback page.
- PNG icons under `site/icons/`, including a maskable 512px icon.
- An install button that appears only when the browser exposes the PWA install prompt.

The public PWA does not add login or admin capability; admin management should remain in a separate microsite.

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

The deploy job validates, applies Terraform, seeds DynamoDB through the ingest Lambda, and invalidates CloudFront.

## Community-assisted growth

The frontend includes a `Suggest an official sporting body or pathway` form. Submissions go to the `suggestions` table as `pending_review`; they are not added to the public directory until reviewed. The recommended OpenAI-assisted research workflow is documented in `docs/COMMUNITY_DISCOVERY_PIPELINE.md`.

Current version: 0.4.4-pwa-section-drawer

## UX polish

The public PWA includes a section drawer and floating back-to-top control for quicker navigation on long mobile pages.
