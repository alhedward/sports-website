# Cognito-backed local admin mode

The public `sports.vk2ale.com` site remains anonymous and has no login/admin UI.

The local admin manager now supports Cognito API mode:

```text
Tkinter admin app
→ Cognito hosted login in browser
→ localhost callback with authorization-code + PKCE
→ protected /admin API Gateway route
→ Lambda verifies group claims and writes DynamoDB
```

## Terraform resources

The stack creates:

- Cognito user pool: `${project_name}-${environment}-admin-users`
- App client: `${project_name}-${environment}-admin-local-app`
- Hosted-login domain
- Groups: `PrimaryAdmins`, `Admins`, `Editors`
- API Gateway JWT authorizer
- Protected route: `ANY /admin/{proxy+}`

MFA is off in this dev build. TOTP/WebAuthn can be enabled later.

## Outputs used by the local app

```bash
terraform -chdir=sports/terraform output -raw admin_api_base_url
terraform -chdir=sports/terraform output -raw admin_cognito_domain_url
terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_client_id
terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_id
```

## First admin user

There is no public signup. Create users using the owner-only helper:

```bash
python3 sports/admin_manager/cognito_user_manager.py create \
  --user-pool-id "$(terraform -chdir=sports/terraform output -raw admin_cognito_user_pool_id)" \
  --email "you@example.com" \
  --group PrimaryAdmins
```

Normal delegated admins should use Cognito API mode and should not receive AWS credentials.

## Protected admin API

Current admin endpoints include:

```text
GET    /admin/me
GET    /admin/collections/{collection}
GET    /admin/collections/{collection}/{id}
PUT    /admin/collections/{collection}/{id}
DELETE /admin/collections/{collection}/{id}
GET    /admin/activity-log
POST   /admin/activity-log
POST   /admin/suggestions/{id}/status
POST   /admin/suggestions/{id}/approve-body
POST   /admin/suggestions/{id}/approve-pathway
POST   /admin/suggestions/{id}/reject
```

The Lambda checks Cognito group claims server-side. Hiding a button in the UI is never treated as authorisation.
