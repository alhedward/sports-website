# Sports.vk2ale — community sports aggregator POC

`Sports.vk2ale` is a serverless proof-of-concept for a sports aggregator site with one main purpose:

> Help people find a way into sport — whatever their age, background, ability, budget, confidence level, or role.

The site is intentionally not just an elite-stats database. It links visitors to official sporting bodies, inclusive participation resources, major international event hubs, and pathway starters for players, fans, families, volunteers, officials and coaches.

## What is included

- Static frontend hosted from private S3 through CloudFront.
- Custom-domain-ready Terraform for `sports.vk2ale.com`.
- API Gateway HTTP API backed by Python Lambda.
- DynamoDB tables for tournaments, pathway profiles, event hubs and official sporting bodies.
- Python ingest Lambda for curated public-link seed data.
- Sponsor-ready placements, deliberately empty until partners are approved.
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
