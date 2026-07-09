# Sports.vk2ale Admin Manager

A Tkinter administration tool for the Sports.vk2ale POC.

The default mode is now **Cognito API mode**:

```text
local admin app → Cognito hosted login → protected /admin API → Lambda → DynamoDB
```

That means delegated admins do **not** need AWS credentials on their machines.
A `boto3_direct` mode is still available as an owner/emergency fallback while the project is in development.

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
- Export all catalogue tables to JSON
- Import a JSON catalogue backup and upsert by `id`
- Write/read/export the shared site-side activity log

The shared activity log is stored in DynamoDB and is only displayed inside this local admin tool, not on the public website/PWA.

## Requirements

```bash
python3 -m pip install -r sports/admin_manager/requirements.txt
sudo apt install python3-tk
```

## Cognito API mode

After Terraform deploy, get the admin config:

```bash
cd ~/git/sports-website/sports/terraform
terraform output -raw admin_api_base_url
terraform output -raw admin_cognito_domain_url
terraform output -raw admin_cognito_user_pool_client_id
terraform output -raw admin_cognito_user_pool_id
```

Run the app:

```bash
cd ~/git/sports-website
python3 sports/admin_manager/sports_admin_manager.py
```

In the top panel, select:

```text
Mode: cognito_api
Admin API: <admin_api_base_url output>
Cognito domain: <admin_cognito_domain_url output>
Client ID: <admin_cognito_user_pool_client_id output>
Callback port: 8765
```

Click **Login / connect**. The app opens the Cognito hosted login in your browser, listens on `http://localhost:8765/callback`, exchanges the authorization code with PKCE, and then calls the protected admin API with the Cognito token.

You can also set these as environment variables:

```bash
export SPORTS_ADMIN_AUTH_MODE=cognito_api
export SPORTS_ADMIN_API_URL="$(terraform -chdir=sports/terraform output -raw admin_api_base_url)"
export SPORTS_ADMIN_COGNITO_DOMAIN="$(terraform -chdir=sports/terraform output -raw admin_cognito_domain_url)"
export SPORTS_ADMIN_COGNITO_CLIENT_ID="$(terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_client_id)"
python3 sports/admin_manager/sports_admin_manager.py
```

## Creating the first admin user

There is no public signup. Use the owner-only helper with your local AWS credentials:

```bash
cd ~/git/sports-website
python3 sports/admin_manager/cognito_user_manager.py create \
  --user-pool-id "$(terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_id)" \
  --email "you@example.com" \
  --group PrimaryAdmins
```

Cognito sends a temporary-password email unless you pass `--suppress-email`.

Other useful commands:

```bash
python3 sports/admin_manager/cognito_user_manager.py list --user-pool-id <pool-id>
python3 sports/admin_manager/cognito_user_manager.py add-group --user-pool-id <pool-id> --email user@example.com --group Admins
python3 sports/admin_manager/cognito_user_manager.py reset-password --user-pool-id <pool-id> --email user@example.com
python3 sports/admin_manager/cognito_user_manager.py disable --user-pool-id <pool-id> --email user@example.com
```

Keep this helper for the primary owner/operator only. Normal admins should not receive AWS credentials.

## boto3 direct fallback

Select `boto3_direct` mode to edit DynamoDB directly using your local AWS credentials. This is intended only for the owner/emergency fallback during development.

```bash
AWS_PROFILE=your-profile-name python3 sports/admin_manager/sports_admin_manager.py
```

The direct identity needs read/write access to these DynamoDB tables:

```text
sports-aggregator-dev-suggestions
sports-aggregator-dev-sport-bodies
sports-aggregator-dev-top-players
sports-aggregator-dev-players
sports-aggregator-dev-tournaments
sports-aggregator-dev-events
sports-aggregator-dev-activity-log
```

## Safety model

Public users can submit suggestions, but suggestions remain `pending_review` until an authenticated admin approves them. Activity-log records now capture the Cognito actor details when using Cognito API mode.

MFA is intentionally off for this development build. The Cognito pool and local app flow are ready for adding TOTP/WebAuthn later.

## 0.7.7 admin UI notes

The admin manager now has a menu bar. API/Cognito settings live under `Admin -> API / Cognito settings...` and are saved automatically in `~/.sports-vk2ale-admin-manager.json`.

`Admin -> Add Cognito user...` is an owner/bootstrap control and is only enabled in `boto3_direct` mode. It uses local AWS credentials to create a Cognito user and place them in `PrimaryAdmins`, `Admins`, or `Editors`.

## Build standalone desktop bundles

Build scripts are in `packaging/`:

```bash
# Linux/macOS
./packaging/build_current_platform.sh

# Windows PowerShell
.\packaging\build_windows.ps1
```

Each platform must be built on that platform. The generated bundles include Python and the required Python packages, so end users do not need to install Python or boto3. See `packaging/README_PACKAGING.md`.



### 0.7.9 admin app update

The admin app now shows AWS profiles in a dropdown. Leaving the AWS profile field blank uses the default boto3 credential chain; selecting a named profile uses that local AWS profile. The selected profile is saved in `~/.sports-vk2ale-admin-manager.json`.
