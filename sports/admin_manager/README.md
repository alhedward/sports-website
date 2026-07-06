# Sports.vk2ale Local Admin Manager

A local-only Tkinter administration tool for the Sports.vk2ale POC.

It uses your local AWS credentials through `boto3` and edits the DynamoDB runtime catalogue directly. There is no public admin microsite and no Cognito dependency in this version.

## What it manages

- Pending public suggestions
- Approve a suggestion into the official sporting bodies table
- Approve a suggestion into the pathway profiles table
- Reject or delete suggestions
- View/create/edit/delete curated records in:
  - suggestions
  - sport bodies
  - top-player spotlights
  - pathway profiles
  - tournaments
  - event hubs
- Export all DynamoDB tables to JSON
- Import a JSON catalogue backup and upsert by `id`

## Requirements

```bash
python3 -m pip install boto3
sudo apt install python3-tk
```

You also need AWS credentials configured locally. For example:

```bash
aws configure sso
# or
aws configure --profile your-profile-name
```

## Run

From the repository root:

```bash
python3 sports/admin_manager/sports_admin_manager.py
```

Or with a specific profile:

```bash
AWS_PROFILE=your-profile-name python3 sports/admin_manager/sports_admin_manager.py
```

The defaults match the current POC:

```text
Region:      ap-southeast-2
Project:     sports-aggregator
Environment: dev
Table prefix: sports-aggregator-dev
```

## IAM permissions

The local AWS identity needs read/write access to these DynamoDB tables:

```text
sports-aggregator-dev-suggestions
sports-aggregator-dev-sport-bodies
sports-aggregator-dev-top-players
sports-aggregator-dev-players
sports-aggregator-dev-tournaments
sports-aggregator-dev-events
```

Minimum DynamoDB actions:

```text
dynamodb:DescribeTable
dynamodb:Scan
dynamodb:GetItem
dynamodb:PutItem
dynamodb:DeleteItem
```

## Safety model

Public users can submit suggestions, but those suggestions remain `pending_review` until you approve them locally. Approval creates/updates a curated record and marks the suggestion as `approved`. Rejection marks it as `rejected` but keeps the record for audit/review.

This is deliberately local-first so the POC has no public admin surface.
