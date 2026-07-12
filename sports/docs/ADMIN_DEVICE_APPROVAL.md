# PrimaryAdmin device approval

Version: 0.7.21-primaryadmin-device-approval

## Purpose

Allow one Cognito admin account to use several browsers, phones and computers without automatically trusting every new device.

## Operator flow

1. On the new device, open `/admin/`, enter the admin email and a useful device label, then continue.
2. The page reports that approval was requested. Cognito login does not start.
3. On an already active device, a `PrimaryAdmins` user opens **Devices**.
4. Review the email, device label, browser user-agent, source IP and request time.
5. Select **Approve** or **Reject**.
6. If approved, return to the new device and press **Continue to Cognito login** again within 30 minutes.
7. Complete Cognito login. The device becomes `active`.

## Security properties

- Approval endpoints require a valid Cognito JWT, membership in `PrimaryAdmins`, and an already active device.
- Other admin groups can use their active devices but cannot list or approve pending requests.
- Protected admin API operations require `X-Admin-Device-Id` to identify an active device in addition to JWT/group checks.
- Approval expires after 30 minutes if login is not completed.
- Rejected or revoked devices may request approval again, but remain blocked until a PrimaryAdmin approves them.
- Pending-device attempts do not contribute to the invalid-account lockout counter.

## Deployment note

The release changes API CORS configuration to allow `X-Admin-Device-Id`. After deployment, refresh `/admin/` so the updated service worker and JavaScript are active. On Chrome, a hard refresh may be useful if an older cached admin script is still running.
