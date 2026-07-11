# Admin PWA routing

The admin PWA is served from `/admin/` under the same CloudFront distribution as the public sports site.

CloudFront does not automatically apply `default_root_object` to subdirectories when the S3 REST origin receives `/admin` or `/admin/`. Without an explicit route rewrite, those requests can fall through to the public `index.html` through the SPA error fallback.

The Terraform stack now attaches a CloudFront Function named `<project>-<env>-site-router` to the viewer-request event. It rewrites:

- `/admin`
- `/admin/`
- `/admin/<deep-link-without-file-extension>`

so they resolve to `/admin/index.html`.

Admin assets such as `/admin/admin.js`, `/admin/admin.css`, and `/admin/manifest.webmanifest` are not rewritten.

The service worker also stores admin navigation responses under `/admin/index.html`, not `/index.html`, so public and admin app shells do not overwrite each other in the browser cache.
