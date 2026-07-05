window.LROC_AUTH = {
  enabled: false,
  cognitoDomain: 'https://lroc-members-demo.auth.ap-southeast-2.amazoncognito.com',
  clientId: 'REPLACED_BY_TERRAFORM',
  redirectUri: `${window.location.origin}${window.location.pathname.replace(/[^/]+$/, '')}members.html`,
  logoutUri: `${window.location.origin}${window.location.pathname.replace(/[^/]+$/, '')}index.html`,
  scopes: ['openid', 'email', 'profile', 'phone', 'aws.cognito.signin.user.admin']
};

window.LROC_MEMBER_API = {
  baseUrl: ''
};

window.LROC_PUSH = {
  // Public half of your generated VAPID keypair. This MUST match terraform.tfvars.
  vapidPublicKey: ''
};

window.LROC_APP = {
  // Local fallback only. Terraform overwrites this file with deploy metadata.
  name: 'LROC Website',
  version: 'local-dev',
  lastUpdated: '28 May 2026',
  author: 'Tony Edward',
  copyrightYear: '2026'
};
