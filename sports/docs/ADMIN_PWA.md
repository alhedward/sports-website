# Sports.vk2ale Admin PWA

Version: 0.7.21-primaryadmin-device-approval

The admin PWA is delivered from the same CloudFront/S3 site as the public Sports.vk2ale PWA, but it is a separate browser/PWA entry point:

- Public app: `https://sports.vk2ale.com/`
- Admin app: `https://sports.vk2ale.com/admin/`

The public app does not show an admin login button. Admin users should be sent the `/admin/` address directly.

## Security model

The admin PWA uses the existing Cognito-backed admin API. The desktop/Tkinter `boto3_direct` pathway remains only for owner/bootstrap/emergency work.

The browser/PWA flow is:

1. User opens `/admin/`.
2. User enters admin email and device label.
3. API performs a server-side pre-login check.
4. If this is the first device, or an active/temporarily approved device, the PWA opens Cognito hosted login.
5. An unknown additional device is stored as `pending`; Cognito login does not open yet.
6. A signed-in `PrimaryAdmins` user reviews the request under **Admin → Devices** and approves or rejects it.
7. Approval is valid for 30 minutes. The requesting device retries the pre-login check and completes Cognito login.
8. Cognito returns an authorization code to `/admin/`, and the PWA exchanges it with PKCE for tokens.
9. Successful login changes the approved device to `active`.
10. Admin API calls send both the Cognito token and `X-Admin-Device-Id`.
11. API Gateway validates the JWT; Lambda checks the Cognito group and active device before protected operations.
12. Lambda performs the action and writes the activity log.

MFA/passkeys are intentionally not enabled in this build, but the flow is compatible with enabling Cognito MFA/WebAuthn later.

## Device registration

PWA installation alone does not create an admin device registration.

A trusted admin device record is created/updated only after successful Cognito login. The current implementation stores a browser-generated device ID and device label. A later hardening pass can add Web Crypto challenge-response device keys.

If an admin user has no device records, the first Cognito login is allowed so the initial device can register. Once any device record exists, an unknown device creates a pending approval request. Only a member of the `PrimaryAdmins` Cognito group can approve or reject that request.

Device states are:

- `pending`: waiting for PrimaryAdmin review
- `approved`: allowed to complete Cognito login for up to 30 minutes
- `active`: successful Cognito login completed; protected admin API calls are allowed
- `revoked`: blocked until a fresh request is explicitly approved

The `X-Admin-Device-Id` value is a browser-generated identifier, not a hardware fingerprint or secret. It supplements Cognito authentication and group authorisation; it does not replace MFA.

## Public notifications

The public PWA includes a cog/settings entry in the side drawer. Public users can opt in or disable notification registration. This does not grant admin access.

This build stores notification subscription/permission records server-side. Full background Web Push delivery requires VAPID key configuration and a sender implementation, which should be added as a separate deployment step.

## Admin operations supported

The admin PWA currently supports:

- view pending suggestions
- approve suggestion as official body
- approve suggestion as pathway
- reject suggestion
- delete suggestion
- view/edit/delete curated catalogue records via JSON editor
- view activity log
- view/register/revoke admin devices
- approve or reject pending devices when signed in as a PrimaryAdmin
- enable/disable admin notification preference scaffold
- export catalogue JSON
- export activity log JSON

## AWS resources added

- `public_push_subscriptions` DynamoDB table
- `admin_devices` DynamoDB table
- `admin_prelogin_attempts` DynamoDB table with TTL
- Cognito app callback/logout URLs for `/admin/`
- Lambda runtime environment variables for the new tables
- Lambda IAM permission to list Cognito users and groups for the pre-login check

## Server-side attempt controls

The admin pre-login check uses server-side controls:

- fixed 5 second response delay
- failed attempt count stored in DynamoDB
- 5 failed attempts causes a 15 minute temporary lockout
- generic access-denied response for invalid accounts
- a valid admin using an unknown device receives a pending-approval status without increasing the failed-login counter
- activity-log entries for allowed/denied/rate-limited checks



## 0.7.14 note

The public PWA settings modal was hardened so the side-drawer cog opens reliably, the close button works, Escape closes the modal, and notification enablement does not request browser notification permission until VAPID push keys are configured. The admin PWA also avoids requesting notification permission until push delivery is configured.
## 0.7.15 notification modal fix

The public settings/notifications modal is now hidden with an explicit CSS rule so it cannot appear automatically on page load. Notification prompts remain user-initiated from Settings only.


## Form and JSON record editing

Curated records open in a field-based form by default. Administrators can switch to
JSON mode for advanced editing. Switching modes synchronises the current unsaved
values, while the API continues to validate that the record id matches the URL.
Lists of simple values are edited one item per line; nested objects are displayed
as grouped form fields where possible.
