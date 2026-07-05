variable "project_name" {
  type        = string
  description = "Prefix used in resource names."
  default     = "lroc"
}

variable "aws_region" {
  type        = string
  description = "Primary AWS region for S3, Lambda, Cognito, and API Gateway."
  default     = "ap-southeast-2"
}

variable "hosted_zone_name" {
  type        = string
  description = "Existing public Route 53 hosted zone name."
  default     = "vk2ale.com"
}

variable "site_domain" {
  type        = string
  description = "Custom site hostname served by CloudFront."
  default     = "lroc.vk2ale.com"
}

variable "subject_alternative_names" {
  type        = list(string)
  description = "Optional additional DNS names for the CloudFront certificate."
  default     = []
}

variable "cloudfront_price_class" {
  type        = string
  description = "CloudFront price class."
  default     = "PriceClass_100"
}

variable "site_bucket_name" {
  type        = string
  description = "Optional explicit S3 bucket name for the public site."
  default     = ""
}

variable "member_files_bucket_name" {
  type        = string
  description = "Optional explicit S3 bucket name for private member files."
  default     = ""
}

variable "member_files_prefix" {
  type        = string
  description = "Prefix inside the member files bucket used for shared uploads."
  default     = "member-files/shared/"
}

variable "cognito_domain_prefix" {
  type        = string
  description = "Unique Cognito Hosted UI domain prefix, for example lroc-members-demo."
}

variable "callback_urls" {
  type        = list(string)
  description = "Optional override for Cognito callback URLs. Leave empty to use sensible defaults."
  default     = []
}

variable "logout_urls" {
  type        = list(string)
  description = "Optional override for Cognito logout URLs. Leave empty to use sensible defaults."
  default     = []
}

variable "allowed_origins" {
  type        = list(string)
  description = "Optional override for site origins that may call the API and use S3 presigned uploads."
  default     = []
}

variable "upload_url_expiry_seconds" {
  type    = number
  default = 900
}

variable "download_url_expiry_seconds" {
  type    = number
  default = 900
}

variable "ses_email_domain" {
  type        = string
  description = "Optional SES sending domain or subdomain to verify. Defaults to site_domain so email can be sent from that subdomain."
  default     = ""
}

variable "ses_from_email" {
  type        = string
  description = "Optional from address for SES mail, for example no-reply@lroc.vk2ale.com. Defaults to no-reply@<ses_email_domain>."
  default     = ""
}

variable "ses_reply_to_email" {
  type        = string
  description = "Optional reply-to address for SES mail. Defaults to the configured SES from address."
  default     = ""
}

variable "ses_mail_from_subdomain" {
  type        = string
  description = "Subdomain prefix used for the SES custom MAIL FROM domain."
  default     = "mail"
}

variable "ses_configuration_set_name" {
  type        = string
  description = "Optional SES configuration set name for club mail."
  default     = ""
}

variable "enable_webmail" {
  type        = bool
  description = "Enable role-based SES inbound/outbound webmail. When true, Terraform creates SES inbound receipt rules and a webmail page/API."
  default     = true
}

variable "webmail_inbound_domain" {
  type        = string
  description = "Domain that SES should receive for role webmail. Defaults to the SES email domain so addresses such as president@<domain> work. Keep the SES MAIL FROM domain separate."
  default     = ""
}

variable "create_webmail_inbound_txt" {
  type        = bool
  description = "Create a TXT/SPF record on the inbound webmail domain. Usually false for root-domain inbound because the domain likely already has TXT records."
  default     = false
}

variable "webmail_inbound_recipients" {
  type        = list(string)
  description = "Optional explicit SES receipt recipients/domains. Leave empty to receive for webmail_inbound_domain, enabling typo-safe unmatched mailbox routing."
  default     = []
}

variable "webmail_unmatched_mailbox_address" {
  type        = string
  description = "Mailbox address used for inbound messages that do not match a configured club role address. Defaults to unmatched@<webmail_inbound_domain>."
  default     = ""
}

variable "webmail_unmatched_position_ids" {
  type        = list(string)
  description = "Club role/position IDs allowed to view unmatched inbound email caused by typos or unconfigured addresses."
  default     = ["president", "webmaster"]
}

variable "webmail_spam_retention_days" {
  type        = number
  description = "How long quarantined spam/virus-flagged inbound webmail is retained before the purge scheduler deletes it."
  default     = 30
}

variable "webmail_spam_purge_schedule_expression" {
  type        = string
  description = "EventBridge Scheduler cron expression for the webmail quarantine purge."
  default     = "cron(30 3 * * ? *)"
}

variable "webmail_spam_purge_schedule_timezone" {
  type        = string
  description = "Time zone used by the webmail quarantine purge scheduler."
  default     = "Australia/Sydney"
}

variable "webmail_max_attachment_bytes" {
  type        = number
  description = "Maximum size of a single inbound/outbound webmail attachment processed by Lambda."
  default     = 52428800
}

variable "webmail_max_total_attachment_bytes" {
  type        = number
  description = "Maximum total attachment payload size accepted by a single webmail send/index operation."
  default     = 52428800
}

variable "enable_webmail_attachment_malware_protection" {
  type        = bool
  description = "Enable GuardDuty Malware Protection for S3 on inbound webmail attachment objects and require clean scan tags before download/import. This may incur GuardDuty scanning/tagging charges."
  default     = false
}

variable "webmail_trust_ses_virus_scan" {
  type        = bool
  description = "When GuardDuty attachment scanning is disabled, allow webmail attachment download/import if SES did not flag the message as malware."
  default     = true
}

variable "enable_article_notifications" {
  type        = bool
  description = "Enable SES notification emails to active members when a new article is published."
  default     = true
}

variable "enable_event_reminders" {
  type        = bool
  description = "Enable SES reminder emails for upcoming club events."
  default     = true
}

variable "system_email_mode" {
  type        = string
  description = "Guardrail for scheduled/member lifecycle emails. Use test during SES trials, live for normal sending, or off to suppress these emails."
  default     = "test"

  validation {
    condition     = contains(["off", "test", "live"], var.system_email_mode)
    error_message = "system_email_mode must be one of: off, test, live."
  }
}

variable "system_email_test_recipients" {
  type        = list(string)
  description = "Email addresses allowed to receive scheduled/member lifecycle emails when system_email_mode is test."
  default     = []
}

variable "system_email_require_cognito_presence" {
  type        = bool
  description = "When true, scheduled/member lifecycle emails are skipped for imported member records that do not yet have a Cognito login identity, unless the recipient is in system_email_test_recipients."
  default     = true
}

variable "club_time_zone" {
  type        = string
  description = "IANA time zone used for club event reminder calculations."
  default     = "Australia/Sydney"
}

variable "event_reminder_lookahead_days" {
  type        = number
  description = "How many days before an event the reminder should be sent."
  default     = 2
}

variable "event_reminder_schedule_expression" {
  type        = string
  description = "EventBridge Scheduler cron expression for the daily event reminder scan."
  default     = "cron(0 9 * * ? *)"
}

variable "event_reminder_schedule_timezone" {
  type        = string
  description = "Time zone used by the EventBridge Scheduler daily event reminder scan."
  default     = "Australia/Sydney"
}

variable "enable_vehicle_registration_push_reminders" {
  type        = bool
  description = "Enable daily PWA push reminders for member vehicle registration expiry dates."
  default     = true
}

variable "vehicle_registration_reminder_months_before" {
  type        = number
  description = "How many calendar months before vehicle registration expiry to send the PWA reminder."
  default     = 1
}

variable "vehicle_registration_final_notice_months_after" {
  type        = number
  description = "How many whole calendar months after vehicle registration expiry to send the final no-more-reminders notice."
  default     = 3
}

variable "vehicle_registration_final_notice_text" {
  type        = string
  description = "Final PWA notification body sent when a vehicle appears unregistered for the configured cutoff period."
  default     = "This vehicle appears to have been unregistered for 3 months. You may need a new pink slip for historic registration, or for classic registration, a new blue slip before re-registering. Registration plates must be surrendered to the Motor Registry office if registration is not renewed within 3 months of expiry."
}

variable "enable_historic_registration_reminders" {
  type        = bool
  description = "Enable Historic / Classic registration renewal, post-processing update, and financial-status reminder emails."
  default     = true
}

variable "historic_rego_update_reminder_months_after" {
  type        = number
  description = "Months after registration expiry or request date before reminding members to update Historic / Classic vehicle details."
  default     = 1
}

variable "historic_rego_renewal_notice_text" {
  type        = string
  description = "Default one-month-before-expiry Historic / Classic renewal notice body. Can be replaced once club wording is final."
  default     = "Your Historic / Classic registration renewal is approaching. Please use the LROC Vehicle Registration page to submit your inspection certificate and the required vehicle photos to the Historic Registrar."
}

variable "vehicle_registration_reminder_schedule_expression" {
  type        = string
  description = "EventBridge Scheduler cron expression for the daily vehicle registration reminder scan."
  default     = "cron(15 9 * * ? *)"
}

variable "vehicle_registration_reminder_schedule_timezone" {
  type        = string
  description = "Time zone used by the EventBridge Scheduler daily vehicle registration reminder scan."
  default     = "Australia/Sydney"
}

variable "geoapify_maptiles_api_key" {
  type        = string
  description = "Geoapify API key used by the browser for Leaflet map tiles in the trip editor. This key is exposed to the browser by design."
  default     = ""
}

variable "geoapify_geocoding_api_key" {
  type        = string
  description = "Geoapify API key used by the member-files Lambda for admin address search/geocoding. If blank, the map tile key is reused."
  default     = ""
  sensitive   = true
}

# Backward-compatible misspelled aliases for existing local tfvars. Prefer the correctly spelled geoapify_* variables above.
variable "geoaplify_maptiles_api_key" {
  type        = string
  description = "Deprecated misspelled alias for geoapify_maptiles_api_key. This key is exposed to the browser by design."
  default     = ""
}

variable "geoaplify_geocoding_api_key" {
  type        = string
  description = "Deprecated misspelled alias for geoapify_geocoding_api_key."
  default     = ""
  sensitive   = true
}

variable "geoapify_maptiles_url_template" {
  type        = string
  description = "Geoapify tile URL template. Use {z}/{x}/{y} and optionally {apiKey}; if {apiKey} is missing the key is appended."
  default     = "https://maps.geoapify.com/v1/tile/carto/{z}/{x}/{y}.png?&apiKey={apiKey}"
}

variable "geoapify_geocoding_url" {
  type        = string
  description = "Geoapify forward geocoding endpoint base URL."
  default     = "https://api.geoapify.com/v1/geocode/search"
}

variable "enable_lroc_monthly_meetings" {
  type        = bool
  description = "Automatically seed LROC January-November monthly meeting events for the current calendar year."
  default     = true
}


# Web push / chat notification settings
variable "push_vapid_public_key" {
  description = "Web push VAPID public key. Terraform writes this to SSM Parameter Store and also uses it in browser runtime config because it is intentionally public."
  type        = string
  default     = ""
}

variable "push_vapid_private_key" {
  description = "Web push VAPID private key. Terraform writes this to SSM Parameter Store as SecureString; do not commit real values."
  type        = string
  default     = ""
  sensitive   = true
}

variable "push_vapid_subject" {
  description = "Web push VAPID subject/contact, usually mailto:admin@example.org. Terraform writes this to SSM Parameter Store."
  type        = string
  default     = ""
}

variable "site_app_version" {
  type        = string
  description = "Site/PWA version generated by the deploy machine in local time."
  default     = ""
}

variable "openai_api_key" {
  type        = string
  description = "OpenAI API key used by the member vehicle help assistant. Leave blank to disable AI suggestions."
  default     = ""
  sensitive   = true
}

variable "openai_model" {
  type        = string
  description = "OpenAI model used by the member vehicle help assistant."
  default     = "gpt-5-mini"
}

variable "openai_web_search_enabled" {
  type        = bool
  description = "Enable Responses API web_search for Vehicle Help parts-number requests when no verified parts record matches."
  default     = true
}

variable "openai_web_search_context_size" {
  type        = string
  description = "Responses API web_search context size for Vehicle Help parts lookups: low, medium, or high."
  default     = "low"
}

variable "articles_inbound_local_parts" {
  description = "Local-parts that mark inbound article submissions as public articles."
  type        = list(string)
  default     = ["article", "articles"]
}

variable "articles_member_inbound_local_parts" {
  description = "Local-parts that mark inbound article submissions as members-only."
  type        = list(string)
  default     = ["clubarticle", "clubarticles"]
}

variable "tripreports_inbound_local_parts" {
  description = "Local-parts that route inbound trip reports to the Editor mailbox only."
  type        = list(string)
  default     = ["tripreport", "tripreports"]
}


variable "presentations_inbound_local_parts" {
  description = "Local-parts that route inbound PowerPoint/presentation submissions to the presentations intake queue."
  type        = list(string)
  default     = ["presentation", "presentations"]
}

variable "magazines_inbound_local_parts" {
  description = "Local-parts that publish inbound magazine PDFs to the magazines library."
  type        = list(string)
  default     = ["magazine", "magazines"]
}

variable "enable_chime_meetings" {
  description = "Enable LROC browser meetings using Amazon Chime SDK Meetings."
  type        = bool
  default     = true
}

variable "chime_media_region" {
  description = "Amazon Chime SDK media Region. Leave blank to use aws_region."
  type        = string
  default     = ""
}

variable "chime_meeting_launch_position_ids" {
  description = "LROC committee position IDs allowed to launch/end browser meetings."
  type        = list(string)
  default     = ["president", "vice-president", "secretary", "treasurer"]
}

variable "chime_default_meeting_title" {
  description = "Default title shown for active LROC browser meetings."
  type        = string
  default     = "LROC online meeting"
}
