# Admin API CORS Preflight

Version: `0.7.19-admin-cors-preflight-fix`

The admin API uses an API Gateway JWT authorizer for protected routes such as
`/admin/me`. Browser calls to these routes include an `Authorization` header,
so browsers first send an unauthenticated `OPTIONS` preflight request.

If that `OPTIONS` request is handled by the JWT-protected `ANY /admin/{proxy+}`
route, API Gateway rejects it before Lambda can return CORS headers. The browser
then reports a CORS error and blocks the real request.

The Terraform now includes an unauthenticated route:

```hcl
OPTIONS /admin/{proxy+}
```

This route uses the same Lambda integration, and the Lambda handler returns a
204 response with the configured CORS headers for `OPTIONS` requests.

The service worker was also adjusted so authenticated admin API responses are
not cached.
