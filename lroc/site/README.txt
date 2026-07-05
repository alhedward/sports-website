
LROC Website + AWS Member File Sharing Starter
==============================================

This bundle combines the red/white LROC website prototype with a starter AWS stack for:
- public static website hosting in S3 + CloudFront
- Cognito member sign-in
- API Gateway + Lambda protected endpoints
- private S3 member file sharing with presigned upload and download URLs
- browser content editor that exports content.json for publishing

Top-level contents
------------------
site files in this folder
terraform/                Infrastructure as code
lambda/                   Python Lambda handlers
content.json              Published site content file for S3
config.js                 Front-end runtime config placeholders
auth.js                   Cognito Hosted UI + PKCE helper for the members page

How the content editor works
----------------------------
1. Open admin.html locally or from your hosted site.
2. Edit the content.
3. Click Save changes to keep a browser draft.
4. Click Export JSON to produce content.json.
5. Upload content.json to your S3 site bucket with your existing Python uploader.

How the member file area works
------------------------------
1. members.html redirects members to Cognito Hosted UI sign-in.
2. After login, the page stores Cognito tokens locally in the browser.
3. The page calls protected API routes using the Cognito access token.
4. Lambda returns:
   - a presigned PUT URL for uploads
   - a list of private member files
   - a presigned GET URL for downloads
5. Files stay private in S3 and are never exposed publicly.

Before deploy
-------------
- Update config.js with the Cognito domain, app client ID, and API base URL outputs from Terraform.
- Upload the website files to the public S3 site bucket.
- Upload content.json whenever your editor changes need to go live.

Terraform notes
---------------
- Terraform creates the Lambda ZIP automatically from lambda/member_files.py.
- The sample uses ap-southeast-2 by default.
- CloudFront ACM certificates must live in us-east-1 if you later add a custom domain.
- The private member file bucket is not public.

API routes created
------------------
GET    /member/files
POST   /member/files/upload-url
POST   /member/files/download-url
DELETE /member/files/{proxy+}   (admin/committee if you later extend the handler)
