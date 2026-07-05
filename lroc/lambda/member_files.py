import base64
import calendar
import csv
import json
import hashlib
import html
import io
import mimetypes
import math
import os
from email import encoders
from email import policy
from email.parser import BytesParser
from email.utils import formataddr, getaddresses, make_msgid, parsedate_to_datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re
import secrets
import uuid
import string
import zipfile
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, unquote, urlencode, urlparse
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

s3 = boto3.client("s3")
cloudfront = boto3.client("cloudfront")
sqs = boto3.client("sqs")
ddb = boto3.client("dynamodb")
cognito = boto3.client("cognito-idp")
sesv2 = boto3.client("sesv2")
ssm = boto3.client("ssm")
chime = boto3.client("chime-sdk-meetings")
_SSM_CACHE: Dict[str, str] = {}
BUCKET = os.environ["MEMBER_FILES_BUCKET"]
SITE_BUCKET = os.environ.get("SITE_BUCKET", "")
SITE_DISTRIBUTION_ID = os.environ.get("SITE_DISTRIBUTION_ID", "").strip()
SITE_CONTENT_KEY = os.environ.get("SITE_CONTENT_KEY", "content.json")
EXPO_CONTENT_KEY = os.environ.get("EXPO_CONTENT_KEY", "expo/content.json")
EXPO_CONTENT_HISTORY_PREFIX = os.environ.get("EXPO_CONTENT_HISTORY_PREFIX", "expo/history/")
SITE_HISTORY_PREFIX = os.environ.get("SITE_HISTORY_PREFIX", "content-history/")
VEHICLE_DATA_KEY = os.environ.get("VEHICLE_DATA_KEY", "vehicle.json")
EVENT_DATA_KEY = os.environ.get("EVENT_DATA_KEY", "event-data.json")
PREFIX = os.environ.get("MEMBER_FILES_PREFIX", "member-files/shared/")
UPLOAD_EXPIRY = int(os.environ.get("UPLOAD_EXPIRY", "900"))
DOWNLOAD_EXPIRY = int(os.environ.get("DOWNLOAD_EXPIRY", "900"))
ALLOWED_GROUPS = {g.strip() for g in os.environ.get("ALLOWED_GROUPS", "members,committee,admins,webmaster").split(",") if g.strip()}
ADMIN_GROUPS = {g.strip() for g in os.environ.get("ADMIN_GROUPS", "committee,admins,webmaster").split(",") if g.strip()}
EMAIL_AUTHOR_GROUPS = {"committee", "admins", "webmaster"}
ROLE_GROUPS = {"members", "committee", "admins", "webmaster"}
POSITION_PK = "CLUB#POSITIONS"
LROC_MEMBER_FILES_BUILD_VERSION = "3.1.6"
LANDROVER_PARTS_PK = "LANDROVER#PARTS"
MEMBER_METADATA_TABLE = os.environ.get("MEMBER_METADATA_TABLE", "")
USER_POOL_ID = os.environ.get("USER_POOL_ID", "")
DELETED_SUFFIX = " - Deleted"
IMPORTED_MEMBER_SUB_PREFIX = "imported:"
ADMIN_IMPORTED_MEMBER_SCAN_MAX = max(500, int(os.environ.get("ADMIN_IMPORTED_MEMBER_SCAN_MAX", "5000")))
# New LROC membership export format.  member_number is the legacy club member
# number and is stored as site_member_id for compatibility with member cards and
# the existing admin list.  Rows without member_number are old/expired and are
# skipped rather than imported.
MEMBER_IMPORT_REQUIRED_HEADERS = ["member_number", "first_name", "last_name"]
# Richer old-site member form export.  These headers are intentionally kept
# close to the source CSV names and remapped into DynamoDB fields during parse.
MEMBER_IMPORT_HEADERS = [
    "Date", "party_id", "first_name", "middle_name", "last_name", "title", "username", "member_number",
    "card_number", "gender", "date_of_birth", "email", "company_name", "mobile", "phone",
    "membership_status", "address1", "address2", "city", "state", "country", "postcode",
    "postal_address1", "postal_address2", "postal_city", "postal_state", "postal_country", "postal_postcode",
    "profile_image", "join_date", "member_type", "primary_first_name", "primary_last_name", "primary_member_number",
    "membership - membership status", "membership - amount paid", "membership - amount outstanding",
    "membership - level start date", "membership - membership expiry", "membership - membership level",
    "membership - membership product", "membership - join date", "approve",
    "do you want to receive a printed copy of the magazine?", "i agree",
    "car #1 - is this a historic car", "car #1 - make ", "car #1 - model", "car #1 - rego",
    "car #1 - vin number", "car #1 - year of manufacture", "car #1 - created date", "car #1 - last modified date"
]
# Kept only so older admin copy/paste attempts fail with a useful message.
OLD_MEMBER_IMPORT_HEADERS = ["UID", "SiteMemberId", "Firstname", "Lastname", "Email", "Username", "CreatedDate", "ActivatedYN", "Roles", "Address1", "Address2", "City", "State", "PostCode", "Mobile", "Phone"]
ARTICLES_MANIFEST_KEY = os.environ.get("ARTICLES_MANIFEST_KEY", "articles/index.json")
ARTICLES_PREFIX = os.environ.get("ARTICLES_PREFIX", "articles/files/")
ARTICLES_MEMBER_PREFIX = os.environ.get("ARTICLES_MEMBER_PREFIX", "articles/member-files/").strip().strip("/") + "/"
ARTICLES_INBOUND_LOCAL_PARTS = {x.strip().lower() for x in os.environ.get("ARTICLES_INBOUND_LOCAL_PARTS", "article,articles").split(",") if x.strip()}
ARTICLES_MEMBER_INBOUND_LOCAL_PARTS = {x.strip().lower() for x in os.environ.get("ARTICLES_MEMBER_INBOUND_LOCAL_PARTS", "clubarticle,clubarticles").split(",") if x.strip()}
TRIPREPORTS_INBOUND_LOCAL_PARTS = {x.strip().lower() for x in os.environ.get("TRIPREPORTS_INBOUND_LOCAL_PARTS", "tripreport,tripreports").split(",") if x.strip()}
PRESENTATIONS_INBOUND_LOCAL_PARTS = {x.strip().lower() for x in os.environ.get("PRESENTATIONS_INBOUND_LOCAL_PARTS", "presentation,presentations").split(",") if x.strip()}
MAGAZINECONTENT_INBOUND_LOCAL_PARTS = {x.strip().lower() for x in os.environ.get("MAGAZINECONTENT_INBOUND_LOCAL_PARTS", "magazinecontent,magazine-content,magazinearticles,magazinearticle").split(",") if x.strip()}
VENDORCONTENT_INBOUND_LOCAL_PARTS = {x.strip().lower() for x in os.environ.get("VENDORCONTENT_INBOUND_LOCAL_PARTS", "vendorcontent,vendor-content,vendorcontents").split(",") if x.strip()}
MAGAZINES_INBOUND_LOCAL_PARTS = {x.strip().lower() for x in os.environ.get("MAGAZINES_INBOUND_LOCAL_PARTS", "magazine,magazines").split(",") if x.strip()}
MAGAZINES_MANIFEST_KEY = os.environ.get("MAGAZINES_MANIFEST_KEY", "magazines/index.json")
MAGAZINES_PREFIX = os.environ.get("MAGAZINES_PREFIX", "magazines/files/").strip().strip("/") + "/"
EVENTS_PDF_PREFIX = os.environ.get("EVENTS_PDF_PREFIX", "events/pdfs/")
EVENTS_IMAGE_PREFIX = os.environ.get("EVENTS_IMAGE_PREFIX", "events/images/").strip().strip("/") + "/"
GEOAPIFY_GEOCODING_API_KEY = os.environ.get("GEOAPIFY_GEOCODING_API_KEY", "").strip()
GEOAPIFY_GEOCODING_URL = os.environ.get("GEOAPIFY_GEOCODING_URL", "https://api.geoapify.com/v1/geocode/search").strip() or "https://api.geoapify.com/v1/geocode/search"
OPENAI_API_KEY_PARAM = os.environ.get("OPENAI_API_KEY_PARAM", "").strip()
OPENAI_MODEL_PARAM = os.environ.get("OPENAI_MODEL_PARAM", "").strip()
OPENAI_API_KEY_FALLBACK = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL_FALLBACK = os.environ.get("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
OPENAI_RESPONSES_URL = os.environ.get("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses").strip() or "https://api.openai.com/v1/responses"
OPENAI_WEB_SEARCH_ENABLED = os.environ.get("OPENAI_WEB_SEARCH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
OPENAI_WEB_SEARCH_CONTEXT_SIZE = os.environ.get("OPENAI_WEB_SEARCH_CONTEXT_SIZE", "low").strip().lower() or "low"
ENABLE_LROC_MONTHLY_MEETINGS = os.environ.get("ENABLE_LROC_MONTHLY_MEETINGS", "true").strip().lower() in {"1", "true", "yes", "on"}
CHIME_MEETINGS_ENABLED = os.environ.get("CHIME_MEETINGS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
CHIME_MEDIA_REGION = os.environ.get("CHIME_MEDIA_REGION", os.environ.get("AWS_REGION", "ap-southeast-2")).strip() or "ap-southeast-2"
CHIME_LAUNCH_POSITION_IDS = {re.sub(r"[^a-z0-9]+", "-", str(x or "").strip().lower()).strip("-") for x in os.environ.get("CHIME_LAUNCH_POSITION_IDS", "president,vice-president,secretary,treasurer").split(",") if str(x).strip()}
CHIME_DEFAULT_MEETING_TITLE = os.environ.get("CHIME_DEFAULT_MEETING_TITLE", "LROC online meeting").strip() or "LROC online meeting"
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "").strip().rstrip("/")
EMAIL_STATE_TABLE = os.environ.get("EMAIL_STATE_TABLE", "")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "").strip()
SES_REPLY_TO_EMAIL = os.environ.get("SES_REPLY_TO_EMAIL", "").strip()
SES_CONFIGURATION_SET = os.environ.get("SES_CONFIGURATION_SET", "").strip()
WEBMAIL_ENABLED = os.environ.get("WEBMAIL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
WEBMAIL_INBOUND_DOMAIN = os.environ.get("WEBMAIL_INBOUND_DOMAIN", "").strip().lower()
WEBMAIL_MAIL_BUCKET = os.environ.get("WEBMAIL_MAIL_BUCKET", BUCKET).strip() or BUCKET
WEBMAIL_INBOUND_PREFIX = os.environ.get("WEBMAIL_INBOUND_PREFIX", "webmail/inbound/").strip().strip("/") + "/"
WEBMAIL_ATTACHMENT_PREFIX = os.environ.get("WEBMAIL_ATTACHMENT_PREFIX", "webmail/attachments/").strip().strip("/") + "/"
WEBMAIL_SENT_PREFIX = os.environ.get("WEBMAIL_SENT_PREFIX", "webmail/sent/").strip().strip("/") + "/"
WEBMAIL_SUBMISSION_PREFIX = os.environ.get("WEBMAIL_SUBMISSION_PREFIX", "webmail/submissions/").strip().strip("/") + "/"
WEBMAIL_REQUIRE_ATTACHMENT_SCAN = os.environ.get("WEBMAIL_REQUIRE_ATTACHMENT_SCAN", os.environ.get("WM_SCAN", "false")).strip().lower() in {"1", "true", "yes", "on"}
WEBMAIL_TRUST_SES_VIRUS_SCAN = os.environ.get("WEBMAIL_TRUST_SES_VIRUS_SCAN", "true").strip().lower() in {"1", "true", "yes", "on"}
WEBMAIL_BACKEND_BUILD = "3.1.7-scan-normalise"
WEBMAIL_MALWARE_SCAN_TAG_KEY = os.environ.get("WEBMAIL_MALWARE_SCAN_TAG_KEY", "GuardDutyMalwareScanStatus").strip() or "GuardDutyMalwareScanStatus"
WEBMAIL_MALWARE_SCAN_CLEAN_VALUES = {x.strip().upper() for x in os.environ.get("WEBMAIL_MALWARE_SCAN_CLEAN_VALUES", "NO_THREATS_FOUND").split(",") if x.strip()}
WEBMAIL_MALWARE_SCAN_BLOCK_VALUES = {x.strip().upper() for x in os.environ.get("WEBMAIL_MALWARE_SCAN_BLOCK_VALUES", "THREATS_FOUND,UNSUPPORTED,ACCESS_DENIED,FAILED").split(",") if x.strip()}
WEBMAIL_UNMATCHED_MAILBOX_ADDRESS = os.environ.get("WEBMAIL_UNMATCHED_MAILBOX_ADDRESS", "").strip().lower()
WEBMAIL_UNMATCHED_POSITION_IDS_RAW = os.environ.get("WEBMAIL_UNMATCHED_POSITION_IDS", "president,webmaster")
WEBMAIL_SPAM_RETENTION_DAYS = max(1, int(os.environ.get("WEBMAIL_SPAM_RETENTION_DAYS", "30")))
WEBMAIL_MAX_ATTACHMENT_BYTES = max(1, int(os.environ.get("WEBMAIL_MAX_ATTACHMENT_BYTES", str(50 * 1024 * 1024))))
WEBMAIL_MAX_TOTAL_ATTACHMENT_BYTES = max(1, int(os.environ.get("WEBMAIL_MAX_TOTAL_ATTACHMENT_BYTES", str(50 * 1024 * 1024))))
WEBMAIL_CLUB_LOGO_URL = os.environ.get("WEBMAIL_CLUB_LOGO_URL", "").strip()
ENABLE_ARTICLE_NOTIFICATIONS = os.environ.get("ENABLE_ARTICLE_NOTIFICATIONS", "false").strip().lower() in {"1", "true", "yes", "on"}
ENABLE_EVENT_REMINDERS = os.environ.get("ENABLE_EVENT_REMINDERS", "false").strip().lower() in {"1", "true", "yes", "on"}
SYSTEM_EMAIL_MODE = os.environ.get("SYSTEM_EMAIL_MODE", "test").strip().lower() or "test"
if SYSTEM_EMAIL_MODE not in {"off", "test", "live"}:
    SYSTEM_EMAIL_MODE = "test"
SYSTEM_EMAIL_TEST_RECIPIENTS = {str(x or "").strip().lower() for x in os.environ.get("SYSTEM_EMAIL_TEST_RECIPIENTS", "").split(",") if str(x or "").strip()}
SYSTEM_EMAIL_REQUIRE_COGNITO_PRESENCE = os.environ.get("SYSTEM_EMAIL_REQUIRE_COGNITO_PRESENCE", "true").strip().lower() in {"1", "true", "yes", "on"}
CLUB_TIME_ZONE = os.environ.get("CLUB_TIME_ZONE", "Australia/Sydney").strip() or "Australia/Sydney"
EVENT_REMINDER_LOOKAHEAD_DAYS = int(os.environ.get("EVENT_REMINDER_LOOKAHEAD_DAYS", "2"))
ENABLE_VEHICLE_REGISTRATION_PUSH_REMINDERS = os.environ.get("ENABLE_VEHICLE_REGISTRATION_PUSH_REMINDERS", "true").strip().lower() in {"1", "true", "yes", "on"}
VEHICLE_REGISTRATION_REMINDER_MONTHS_BEFORE = max(1, int(os.environ.get("VEHICLE_REGISTRATION_REMINDER_MONTHS_BEFORE", "1")))
VEHICLE_REGISTRATION_FINAL_NOTICE_MONTHS_AFTER = max(1, int(os.environ.get("VEHICLE_REGISTRATION_FINAL_NOTICE_MONTHS_AFTER", "3")))
VEHICLE_REGISTRATION_FINAL_NOTICE_TEXT = os.environ.get(
    "VEHICLE_REGISTRATION_FINAL_NOTICE_TEXT",
    "This vehicle appears to have been unregistered for 3 months. You may need a new pink slip for historic registration, or for classic registration, a new blue slip before re-registering. Registration plates must be surrendered to the Motor Registry office if registration is not renewed within 3 months of expiry.",
).strip()
CHAT_TABLE = os.environ.get("CHAT_TABLE", "").strip()
CHAT_MEMBER_GROUPS = {g.strip() for g in os.environ.get("CHAT_MEMBER_GROUPS", "members,committee,admins,webmaster").split(",") if g.strip()}
CHAT_COMMITTEE_GROUPS = {g.strip() for g in os.environ.get("CHAT_COMMITTEE_GROUPS", "committee,admins,webmaster").split(",") if g.strip()}
CHAT_ADMIN_GROUPS = {g.strip() for g in os.environ.get("CHAT_ADMIN_GROUPS", "admins,webmaster").split(",") if g.strip()}
CHAT_MODERATOR_GROUPS = {g.strip() for g in os.environ.get("CHAT_MODERATOR_GROUPS", "committee,admins,webmaster").split(",") if g.strip()}
MAX_CHAT_MESSAGE_LENGTH = max(1, int(os.environ.get("MAX_CHAT_MESSAGE_LENGTH", "1200")))
MAX_CHAT_HISTORY_LIMIT = max(1, min(200, int(os.environ.get("MAX_CHAT_HISTORY_LIMIT", "80"))))
MAX_CHAT_ROOM_TITLE_LENGTH = max(8, int(os.environ.get("MAX_CHAT_ROOM_TITLE_LENGTH", "80")))
MAX_CHAT_ROOM_DESCRIPTION_LENGTH = max(0, int(os.environ.get("MAX_CHAT_ROOM_DESCRIPTION_LENGTH", "240")))
CHAT_NOTIFICATION_QUEUE_URL = os.environ.get("CHAT_NOTIFICATION_QUEUE_URL", "").strip()
CHAT_ATTACHMENTS_PREFIX = os.environ.get("CHAT_ATTACHMENTS_PREFIX", "chat/attachments/").strip().strip("/") + "/"
CHAT_ATTACHMENT_MAX_BYTES = max(1, int(os.environ.get("CHAT_ATTACHMENT_MAX_BYTES", str(5 * 1024 * 1024))))
CHAT_EVENT_INVITE_TTL_DAYS = max(1, int(os.environ.get("CHAT_EVENT_INVITE_TTL_DAYS", "7")))
CHAT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
HISTORIC_REGO_POSITION_IDS = {"historic-vehicle-registration", "historic-registration", "historic-rego", "historic-vehicle-rego", "historic-registrar"}
HISTORIC_REGO_MAX_IMAGES = max(1, min(25, int(os.environ.get("HISTORIC_REGO_MAX_IMAGES", "12"))))
HISTORIC_REGO_MAX_IMAGE_BYTES = max(1, int(os.environ.get("HISTORIC_REGO_MAX_IMAGE_BYTES", str(2 * 1024 * 1024))))
HISTORIC_REGO_MAX_TOTAL_IMAGE_BYTES = max(1, int(os.environ.get("HISTORIC_REGO_MAX_TOTAL_IMAGE_BYTES", str(30 * 1024 * 1024))))
HISTORIC_REGO_CERTIFICATE_MAX_BYTES = max(1, int(os.environ.get("HISTORIC_REGO_CERTIFICATE_MAX_BYTES", str(10 * 1024 * 1024))))
HISTORIC_REGO_EMAIL_ATTACHMENT_MAX_BYTES = max(1, int(os.environ.get("HISTORIC_REGO_EMAIL_ATTACHMENT_MAX_BYTES", str(35 * 1024 * 1024))))
HISTORIC_REGO_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
HISTORIC_REGO_CERTIFICATE_TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
HISTORIC_REGO_PHOTO_SLOTS = ["front", "rear", "left_side", "right_side", "engine_bay", "dashboard", "interior_seatbelts"]
HISTORIC_REGO_PHOTO_SLOT_LABELS = {"front": "Front", "rear": "Rear", "left_side": "Left-hand side", "right_side": "Right-hand side", "engine_bay": "Engine bay", "dashboard": "Dashboard", "interior_seatbelts": "Interior seating and seatbelts", "extra": "Extra", "certificate": "Vehicle inspection certificate"}
HISTORIC_REGO_QUEUE_POSITION_IDS = HISTORIC_REGO_POSITION_IDS | {"president", "vice-president", "secretary", "treasurer"}
HISTORIC_REGO_STORAGE_PREFIX = os.environ.get("HISTORIC_REGO_STORAGE_PREFIX", (PREFIX.rstrip("/") + "/historic-registration/")).strip().strip("/") + "/"
MEETING_MINUTES_PREFIX = os.environ.get("MEETING_MINUTES_PREFIX", f"{PREFIX.rstrip('/')}/meeting-minutes/").strip().strip("/") + "/"
MEETING_AGENDA_SERVICE_LOCAL_PART = os.environ.get("MEETING_AGENDA_SERVICE_LOCAL_PART", "meetingagenda").strip().lower() or "meetingagenda"
ENABLE_HISTORIC_REGISTRATION_REMINDERS = os.environ.get("ENABLE_HISTORIC_REGISTRATION_REMINDERS", "true").strip().lower() in {"1", "true", "yes", "on"}
HISTORIC_REGO_UPDATE_REMINDER_MONTHS_AFTER = max(1, int(os.environ.get("HISTORIC_REGO_UPDATE_REMINDER_MONTHS_AFTER", "1")))
HISTORIC_REGO_RENEWAL_NOTICE_TEXT = os.environ.get(
    "HISTORIC_REGO_RENEWAL_NOTICE_TEXT",
    "Your Historic / Classic registration renewal is approaching. Please use the LROC Vehicle Registration page to submit your inspection certificate and the required vehicle photos to the Historic Registrar.",
).strip()

CHAT_BLOCKED_ATTACHMENT_EXTENSIONS = {
    ".ade", ".adp", ".apk", ".app", ".bat", ".bin", ".cmd", ".com", ".cpl", ".dll", ".dmg", ".exe",
    ".gadget", ".hta", ".ins", ".iso", ".jar", ".js", ".jse", ".lib", ".lnk", ".msi", ".msp",
    ".mst", ".pif", ".ps1", ".psm1", ".scr", ".sh", ".sys", ".vb", ".vbe", ".vbs", ".ws", ".wsc", ".wsf"
}

DEFAULT_VEHICLE_DATA: Dict[str, Any] = {
    "version": 1,
    "fuel_types": ["Petrol", "Diesel", "LPG", "Hybrid", "Electric", "Other"],
    "makes": {
        "Land Rover": {
            "models": {
                "Series 1": {"variants": ["80\"", "86\"", "88\"", "107\"", "109\""]},
                "Series 2": {"variants": ["88\"", "109\""]},
                "Series 2a": {"variants": ["88\"", "109\""]},
                "Series 3": {"variants": ["88\"", "109\""]},
                "Defender": {"variants": ["90", "110", "130", "6x6"]},
                "Freelander": {"variants": []},
                "Freelander 2": {"variants": []},
                "Discovery": {"variants": []},
                "Perentie": {"variants": []},
            }
        },
        "Range Rover": {
            "models": {
                "Classic": {"variants": []},
                "P38": {"variants": []},
                "Late Model": {"variants": []},
            }
        },
    },
}


DEFAULT_EVENT_DATA: Dict[str, Any] = {
    "version": 1,
    "event_types": {
        "Social": {"ratings": []},
        "Touring": {"ratings": []},
        "4WD": {"ratings": ["Easy", "Medium", "Hard", "Extreme"]},
    },
}



def response(status: int, body: Dict[str, Any] | List[Any] | str) -> Dict[str, Any]:
    payload = body if isinstance(body, str) else json.dumps(body)
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": payload,
    }


def parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def get_query_params(event: Dict[str, Any]) -> Dict[str, str]:
    params = event.get("queryStringParameters") or {}
    if params:
        return {str(k): str(v) for k, v in params.items() if v is not None}
    raw = event.get("rawQueryString") or ""
    if not raw:
        return {}
    parsed = parse_qs(raw, keep_blank_values=True)
    return {k: v[-1] for k, v in parsed.items() if v}


def get_claims(event: Dict[str, Any]) -> Dict[str, Any]:
    return (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}


def get_groups(claims: Dict[str, Any]) -> set[str]:
    raw = claims.get("cognito:groups") or claims.get("groups") or []
    if isinstance(raw, list):
        return {str(x).strip() for x in raw if str(x).strip()}
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
        if not text:
            return set()
        parts = re.split(r"[\s,]+", text)
        return {p.strip() for p in parts if p.strip()}
    return set()


def ensure_member(event: Dict[str, Any]) -> Dict[str, Any]:
    claims = get_claims(event)
    groups = get_groups(claims)
    if not groups.intersection(ALLOWED_GROUPS):
        raise PermissionError("The signed-in user is not in an allowed member group.")
    return claims


def is_admin(claims: Dict[str, Any]) -> bool:
    return bool(get_groups(claims).intersection(ADMIN_GROUPS))


def require_admin(claims: Dict[str, Any]) -> None:
    if not is_admin(claims):
        raise PermissionError("Only committee/admin members can manage membership metadata.")


def require_metadata_table() -> None:
    if not MEMBER_METADATA_TABLE:
        raise RuntimeError("MEMBER_METADATA_TABLE is not configured.")


def require_user_pool() -> None:
    if not USER_POOL_ID:
        raise RuntimeError("USER_POOL_ID is not configured.")


def require_chat_table() -> None:
    if not CHAT_TABLE:
        raise RuntimeError("CHAT_TABLE is not configured.")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_precise() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def require_email_state_table() -> None:
    if not EMAIL_STATE_TABLE:
        raise RuntimeError("EMAIL_STATE_TABLE is not configured.")


def require_ses_sender() -> None:
    if not SES_FROM_EMAIL:
        raise RuntimeError("SES_FROM_EMAIL is not configured.")


def clean_header_address(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", str(value or "")).strip()


def lroc_from_header(address: str | None = None) -> str:
    addr = clean_header_address(address or SES_FROM_EMAIL)
    if not addr:
        raise RuntimeError("SES sender address is not configured.")
    if "<" in addr and ">" in addr:
        return addr
    return f"LROC <{addr}>"


def send_email_via_ses(to_addresses: List[str], subject: str, text_body: str, html_body: str | None = None, *, bcc_addresses: List[str] | None = None, from_email: str | None = None, reply_to: str | None = None) -> Dict[str, Any]:
    require_ses_sender()
    to_list = [str(x or "").strip() for x in (to_addresses or []) if str(x or "").strip()]
    bcc_list = [str(x or "").strip() for x in (bcc_addresses or []) if str(x or "").strip()]
    if not to_list and not bcc_list:
        raise ValueError("At least one recipient email address is required.")
    subject = str(subject or "").strip() or "LROC email"
    text_body = str(text_body or "").strip() or "This is an automated email from LROC."
    content: Dict[str, Any] = {
        "Simple": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": text_body, "Charset": "UTF-8"}},
        }
    }
    if html_body and str(html_body).strip():
        content["Simple"]["Body"]["Html"] = {"Data": str(html_body), "Charset": "UTF-8"}
    destination: Dict[str, Any] = {}
    if to_list:
        destination["ToAddresses"] = to_list
    if bcc_list:
        destination["BccAddresses"] = bcc_list
    kwargs: Dict[str, Any] = {
        "FromEmailAddress": lroc_from_header(from_email),
        "Destination": destination,
        "Content": content,
    }
    reply = clean_header_address(reply_to or SES_REPLY_TO_EMAIL or from_email or "")
    if reply:
        kwargs["ReplyToAddresses"] = [reply]
    if SES_CONFIGURATION_SET:
        kwargs["ConfigurationSetName"] = SES_CONFIGURATION_SET
    return sesv2.send_email(**kwargs)


def send_raw_email_via_ses(to_addresses: List[str], raw_message: bytes, *, from_email: str | None = None, reply_to: str | None = None) -> Dict[str, Any]:
    require_ses_sender()
    to_list = [str(x or "").strip() for x in (to_addresses or []) if str(x or "").strip()]
    if not to_list:
        raise ValueError("At least one recipient email address is required.")
    kwargs: Dict[str, Any] = {
        "FromEmailAddress": lroc_from_header(from_email),
        "Destination": {"ToAddresses": to_list},
        "Content": {"Raw": {"Data": raw_message}},
    }
    reply = clean_header_address(reply_to or SES_REPLY_TO_EMAIL or from_email or "")
    if reply:
        kwargs["ReplyToAddresses"] = [reply]
    if SES_CONFIGURATION_SET:
        kwargs["ConfigurationSetName"] = SES_CONFIGURATION_SET
    return sesv2.send_email(**kwargs)


EMAIL_SUPPRESSION_REASONS = {"bounce", "complaint", "unsubscribed", "manual"}


def normalise_email_address(value: str) -> str:
    return str(value or "").strip().lower()


def valid_email_address(value: str) -> bool:
    email = normalise_email_address(value)
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def ses_email_available() -> bool:
    return bool(SES_FROM_EMAIL)


def safe_send_email_via_ses(to_addresses: List[str], subject: str, text_body: str, html_body: str | None = None, *, bcc_addresses: List[str] | None = None, from_email: str | None = None, reply_to: str | None = None) -> Dict[str, Any]:
    """Best-effort email sender for scheduled/member convenience notices.

    Core transactional paths can still call send_email_via_ses directly when
    failure should stop the request.  Scheduler-driven reminders must not fail a
    whole daily run just because SES has not been enabled yet.
    """
    if not ses_email_available():
        return {"sent": False, "skipped": True, "reason": "ses_not_configured"}
    try:
        result = send_email_via_ses(to_addresses, subject, text_body, html_body, bcc_addresses=bcc_addresses, from_email=from_email, reply_to=reply_to)
        return {"sent": True, "message_id": str(result.get("MessageId") or "")}
    except Exception as exc:
        return {"sent": False, "skipped": True, "reason": "send_failed", "error": str(exc)[:500]}


def member_email_from_metadata(member: Dict[str, Any], claims: Dict[str, Any] | None = None) -> str:
    claims = claims or {}
    candidates = [
        member.get("email"),
        member.get("email_raw"),
        claims.get("email"),
    ]
    for candidate in candidates:
        email = normalise_email_address(candidate or "")
        if valid_email_address(email):
            return email
    return ""


def member_has_cognito_presence(member: Dict[str, Any]) -> bool:
    sub = str(member.get("sub") or member.get("member_sub") or member.get("user_sub") or "").strip()
    cognito_sub = str(member.get("cognito_sub") or "").strip()
    cognito_username = str(member.get("cognito_username") or "").strip()
    imported = bool(member.get("imported_member")) or sub.startswith(IMPORTED_MEMBER_SUB_PREFIX)
    if cognito_sub or (cognito_username and not cognito_username.startswith(IMPORTED_MEMBER_SUB_PREFIX)):
        return True
    return bool(sub and not imported and not sub.startswith(IMPORTED_MEMBER_SUB_PREFIX))


def system_email_guard_status(recipient: Dict[str, Any], *, context: str = "system") -> Dict[str, Any]:
    email = normalise_email_address(recipient.get("email") or "")
    if not email:
        return {"allowed": False, "reason": "missing_email"}
    if SYSTEM_EMAIL_MODE == "off":
        return {"allowed": False, "reason": "system_email_mode_off"}
    if SYSTEM_EMAIL_MODE == "test" and email not in SYSTEM_EMAIL_TEST_RECIPIENTS:
        return {"allowed": False, "reason": "system_email_test_mode", "mode": SYSTEM_EMAIL_MODE}
    if SYSTEM_EMAIL_REQUIRE_COGNITO_PRESENCE and email not in SYSTEM_EMAIL_TEST_RECIPIENTS and not member_has_cognito_presence(recipient):
        return {"allowed": False, "reason": "no_cognito_presence", "mode": SYSTEM_EMAIL_MODE}
    return {"allowed": True, "reason": "allowed", "mode": SYSTEM_EMAIL_MODE}


def system_email_guard_summary() -> Dict[str, Any]:
    return {
        "mode": SYSTEM_EMAIL_MODE,
        "test_recipient_count": len(SYSTEM_EMAIL_TEST_RECIPIENTS),
        "require_cognito_presence": bool(SYSTEM_EMAIL_REQUIRE_COGNITO_PRESENCE),
    }


def member_number_from_metadata(member: Dict[str, Any]) -> str:
    return str(member.get("member_number") or member.get("site_member_id") or "").strip()


def simple_html_email(title: str, paragraphs: List[str], rows: List[Tuple[str, str]] | None = None, footer: str = "") -> str:
    row_html = ""
    if rows:
        row_html = "<table style='border-collapse:collapse;width:100%;font-size:14px;margin:16px 0'>" + "".join(
            f"<tr><th style='text-align:left;padding:7px 10px;border-bottom:1px solid #e5e7eb;width:190px'>{html.escape(label)}</th><td style='padding:7px 10px;border-bottom:1px solid #e5e7eb'>{html.escape(value or 'Not supplied')}</td></tr>"
            for label, value in rows
        ) + "</table>"
    paras = "".join(f"<p>{html.escape(str(part or '')).replace(chr(10), '<br>')}</p>" for part in paragraphs if str(part or '').strip())
    footer_html = f"<p style='margin-top:20px;color:#6b7280;font-size:12px'>{html.escape(footer)}</p>" if footer else ""
    return (
        "<div style='font-family:Arial,sans-serif;line-height:1.55;color:#111827'>"
        "<div style='border-bottom:3px solid #7f1d1d;padding-bottom:12px;margin-bottom:18px'>"
        "<strong style='font-size:18px;color:#7f1d1d'>LROC</strong><br>"
        "<span>Land Rover Owners Club of Australia Inc</span>"
        "</div>"
        f"<h2 style='color:#143b2d;margin:0 0 12px'>{html.escape(title)}</h2>"
        f"{paras}{row_html}{footer_html}"
        "</div>"
    )


def email_state_key(email: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": f"EMAIL#{normalise_email_address(email)}"}, "sk": {"S": "SUPPRESSION"}}


def get_email_suppression(email: str) -> Dict[str, Any] | None:
    email = normalise_email_address(email)
    if not email or not EMAIL_STATE_TABLE:
        return None
    resp = ddb.get_item(TableName=EMAIL_STATE_TABLE, Key=email_state_key(email), ConsistentRead=True)
    item = resp.get("Item")
    return item_to_python(item) if item else None


def is_email_suppressed(email: str) -> bool:
    item = get_email_suppression(email)
    if not item:
        return False
    return str(item.get("status") or "suppressed").strip().lower() != "cleared"


def suppress_email_address(email: str, reason: str, *, source: str = "system", details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    require_email_state_table()
    email = normalise_email_address(email)
    if not valid_email_address(email):
        raise ValueError("A valid email address is required.")
    reason = str(reason or "manual").strip().lower()
    if reason not in EMAIL_SUPPRESSION_REASONS:
        reason = "manual"
    now = utc_now()
    existing = get_email_suppression(email) or {}
    payload = {
        "pk": f"EMAIL#{email}",
        "sk": "SUPPRESSION",
        "email": email,
        "status": "suppressed",
        "reason": reason,
        "source": str(source or "system"),
        "first_seen_at": existing.get("first_seen_at") or now,
        "last_seen_at": now,
        "updated_at": now,
    }
    if details:
        payload["details"] = details
    ddb.put_item(TableName=EMAIL_STATE_TABLE, Item=python_to_item(payload))
    return payload


def clear_email_suppression(email: str, *, cleared_by: str = "admin") -> Dict[str, Any]:
    require_email_state_table()
    email = normalise_email_address(email)
    if not valid_email_address(email):
        raise ValueError("A valid email address is required.")
    now = utc_now()
    payload = {
        "pk": f"EMAIL#{email}",
        "sk": "SUPPRESSION",
        "email": email,
        "status": "cleared",
        "reason": "cleared",
        "source": "admin",
        "cleared_by": str(cleared_by or "admin"),
        "cleared_at": now,
        "updated_at": now,
    }
    ddb.put_item(TableName=EMAIL_STATE_TABLE, Item=python_to_item(payload))
    return payload


def filter_sendable_recipients(recipients: List[Dict[str, Any]], *, apply_system_guard: bool = False, context: str = "system") -> Dict[str, Any]:
    sendable: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for recipient in recipients:
        email = normalise_email_address(recipient.get("email") or "")
        if not email or email in seen:
            continue
        seen.add(email)
        suppression = get_email_suppression(email)
        if suppression and str(suppression.get("status") or "suppressed").lower() != "cleared":
            skipped.append({
                "email": email,
                "name": str(recipient.get("name") or ""),
                "reason": str(suppression.get("reason") or "suppressed"),
                "status": str(suppression.get("status") or "suppressed"),
            })
            continue
        item = dict(recipient)
        item["email"] = email
        if apply_system_guard:
            guard = system_email_guard_status(item, context=context)
            if not guard.get("allowed"):
                skipped.append({
                    "email": email,
                    "name": str(item.get("name") or ""),
                    "reason": str(guard.get("reason") or "system_email_guard"),
                    "status": "skipped",
                    "mode": str(guard.get("mode") or SYSTEM_EMAIL_MODE),
                })
                continue
        sendable.append(item)
    return {"sendable": sendable, "skipped": skipped}


def handle_ses_feedback_notification(message: Dict[str, Any]) -> Dict[str, Any]:
    notification_type = str(message.get("notificationType") or message.get("eventType") or "").strip().lower()
    suppressed: List[Dict[str, str]] = []
    if notification_type == "bounce":
        bounce = message.get("bounce") or {}
        for recipient in bounce.get("bouncedRecipients") or []:
            email = normalise_email_address(recipient.get("emailAddress") or recipient.get("email") or "")
            if not email:
                continue
            item = suppress_email_address(email, "bounce", source="ses", details={
                "bounce_type": str(bounce.get("bounceType") or ""),
                "bounce_subtype": str(bounce.get("bounceSubType") or ""),
                "diagnostic_code": str(recipient.get("diagnosticCode") or ""),
            })
            suppressed.append({"email": email, "reason": str(item.get("reason") or "bounce")})
    elif notification_type == "complaint":
        complaint = message.get("complaint") or {}
        for recipient in complaint.get("complainedRecipients") or []:
            email = normalise_email_address(recipient.get("emailAddress") or recipient.get("email") or "")
            if not email:
                continue
            item = suppress_email_address(email, "complaint", source="ses", details={
                "complaint_feedback_type": str(complaint.get("complaintFeedbackType") or ""),
            })
            suppressed.append({"email": email, "reason": str(item.get("reason") or "complaint")})
    return {"notification_type": notification_type, "suppressed": suppressed, "suppressed_count": len(suppressed)}


def handle_sns_event(event: Dict[str, Any]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for record in event.get("Records") or []:
        sns = record.get("Sns") or record.get("sns") or {}
        raw = sns.get("Message") or sns.get("message") or "{}"
        try:
            message = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            message = {"raw": str(raw)}
        results.append(handle_ses_feedback_notification(message if isinstance(message, dict) else {"raw": str(message)}))
    return response(200, {"message": "SES feedback processed.", "results": results})


def normalise_position_id(value: Any, fallback: str = "") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not text and fallback:
        text = re.sub(r"[^a-z0-9]+", "-", fallback.strip().lower()).strip("-")
    return text[:64]


def position_key(position_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": POSITION_PK}, "sk": {"S": f"POSITION#{normalise_position_id(position_id)}"}}


def club_email_domain() -> str:
    for value in (WEBMAIL_INBOUND_DOMAIN, urlparse(SITE_BASE_URL).hostname or '', SES_REPLY_TO_EMAIL, SES_FROM_EMAIL):
        text = normalise_email_address(value) if '@' in str(value or '') else str(value or '').strip().lower()
        if '@' in text:
            text = text.rsplit('@', 1)[-1]
        if text and valid_email_address(f"club@{text}"):
            return text
    return "lroc.com.au"


def default_positions() -> List[Dict[str, Any]]:
    domain = club_email_domain()
    return [
        {"position_id": "president", "position_name": "President", "email_address": f"president@{domain}", "is_committee_position": True, "sort_order": 10, "active": True},
        {"position_id": "vice-president", "position_name": "Vice President", "email_address": f"vicepresident@{domain}", "is_committee_position": True, "sort_order": 20, "active": True},
        {"position_id": "secretary", "position_name": "Secretary", "email_address": f"secretary@{domain}", "is_committee_position": True, "sort_order": 30, "active": True},
        {"position_id": "treasurer", "position_name": "Treasurer", "email_address": f"treasurer@{domain}", "is_committee_position": True, "sort_order": 40, "active": True},
        {"position_id": "publicity-officer", "position_name": "Publicity Officer", "email_address": f"publicity@{domain}", "is_committee_position": True, "sort_order": 50, "active": True},
        {"position_id": "historic-registrar", "position_name": "Historic Registrar", "email_address": f"rego@{domain}", "is_committee_position": False, "sort_order": 70, "active": True},
        {"position_id": "meetingagenda", "position_name": "Meeting Agenda", "email_address": f"{MEETING_AGENDA_SERVICE_LOCAL_PART}@{domain}", "is_committee_position": False, "sort_order": 80, "active": True},
        {"position_id": "committee-member", "position_name": "Committee Member", "email_address": "", "is_committee_position": True, "sort_order": 90, "active": True},
    ]


def list_club_positions(include_defaults: bool = True) -> List[Dict[str, Any]]:
    require_metadata_table()
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": {"S": POSITION_PK}, ":prefix": {"S": "POSITION#"}},
    )
    stored_items = [item_to_python(item) for item in resp.get("Items") or []]
    if not include_defaults:
        items = stored_items
    else:
        # Always merge built-in club roles with stored role definitions. The old
        # logic only returned defaults when DynamoDB had no position records at
        # all, so adding one custom/stored role could accidentally hide defaults
        # like President/Webmaster from Webmail and role assignment pickers.
        # Stored records still win so admins can rename, disable, sort, or change
        # email addresses deliberately.
        by_id: Dict[str, Dict[str, Any]] = {
            normalise_position_id(p.get("position_id") or p.get("position_name") or ""): dict(p)
            for p in default_positions()
        }
        for item in stored_items:
            pid = normalise_position_id(item.get("position_id") or item.get("position_name") or "")
            if not pid:
                continue
            merged = dict(by_id.get(pid, {}))
            merged.update(item)
            merged["position_id"] = pid
            by_id[pid] = merged
        items = list(by_id.values())
    items.sort(key=lambda x: (int(x.get("sort_order") or 999), str(x.get("position_name") or "").lower()))
    return items


def get_club_position(position_id: str) -> Dict[str, Any] | None:
    pid = normalise_position_id(position_id)
    if not pid:
        return None
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=position_key(pid), ConsistentRead=True)
    item = resp.get("Item")
    if item:
        return item_to_python(item)
    for position in default_positions():
        if position["position_id"] == pid:
            return position
    return None


def save_club_position(payload: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_metadata_table()
    name = str(payload.get("position_name") or payload.get("name") or "").strip()
    pid = normalise_position_id(payload.get("position_id") or "", name)
    if not pid or not name:
        raise ValueError("Position name is required.")
    email = normalise_email_address(payload.get("email_address") or "")
    if email and not valid_email_address(email):
        raise ValueError("Position email address must be valid or blank.")
    now = utc_now()
    item = {
        "pk": POSITION_PK,
        "sk": f"POSITION#{pid}",
        "position_id": pid,
        "position_name": name,
        "email_address": email,
        "is_committee_position": bool(payload.get("is_committee_position", True)),
        "active": bool(payload.get("active", True)),
        "sort_order": int(payload.get("sort_order") or 999),
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or "admin"),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return item


def delete_club_position(position_id: str) -> Dict[str, Any]:
    require_metadata_table()
    pid = normalise_position_id(position_id)
    if not pid:
        raise ValueError("position_id is required.")
    ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=position_key(pid))
    return {"position_id": pid, "deleted": True}


def list_positions_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    return response(200, {"items": list_club_positions()})


def save_position_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    item = save_club_position(parse_body(event), claims)
    return response(200, {"message": f"Position saved: {item['position_name']}", "item": item})


def delete_position_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    item = delete_club_position(str(body.get("position_id") or ""))
    return response(200, {"message": "Position deleted.", "item": item})


def clean_vehicle_text(value: Any, max_len: int = 96) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:max_len]


def clean_vehicle_date(value: Any, field_name: str = "date") -> str:
    text = clean_vehicle_text(value, 10)
    if not text:
        return ""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        raise ValueError(f"{field_name} must be YYYY-MM-DD or blank.")
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{field_name} must be a valid date or blank.")
    return text


def default_vehicle_data() -> Dict[str, Any]:
    return deepcopy(DEFAULT_VEHICLE_DATA)


def normalise_vehicle_data(data: Dict[str, Any] | None) -> Dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    raw_makes = source.get("makes") if isinstance(source.get("makes"), dict) else {}
    makes: Dict[str, Any] = {}
    for make_name, make_data in raw_makes.items():
        make_label = clean_vehicle_text(make_name, 64)
        if not make_label:
            continue
        raw_models = {}
        if isinstance(make_data, dict) and isinstance(make_data.get("models"), dict):
            raw_models = make_data.get("models") or {}
        models: Dict[str, Any] = {}
        for model_name, model_data in raw_models.items():
            model_label = clean_vehicle_text(model_name, 64)
            if not model_label:
                continue
            raw_variants = []
            if isinstance(model_data, dict) and isinstance(model_data.get("variants"), list):
                raw_variants = model_data.get("variants") or []
            variants: List[str] = []
            seen_variants: set[str] = set()
            for variant in raw_variants:
                variant_label = clean_vehicle_text(variant, 64)
                variant_key = variant_label.lower()
                if variant_label and variant_key not in seen_variants:
                    variants.append(variant_label)
                    seen_variants.add(variant_key)
            models[model_label] = {"variants": variants}
        makes[make_label] = {"models": models}
    if not makes:
        makes = deepcopy(DEFAULT_VEHICLE_DATA["makes"])
    raw_fuel_types = source.get("fuel_types") if isinstance(source.get("fuel_types"), list) else []
    fuel_types: List[str] = []
    seen_fuel_types: set[str] = set()
    for fuel_type in raw_fuel_types:
        fuel_label = clean_vehicle_text(fuel_type, 64)
        fuel_key = fuel_label.lower()
        if fuel_label and fuel_key not in seen_fuel_types:
            fuel_types.append(fuel_label)
            seen_fuel_types.add(fuel_key)
    if not fuel_types:
        fuel_types = deepcopy(DEFAULT_VEHICLE_DATA["fuel_types"])
    return {
        "version": int(source.get("version") or 1),
        "updated_at": clean_vehicle_text(source.get("updated_at") or "", 32),
        "updated_by": clean_vehicle_text(source.get("updated_by") or "", 128),
        "fuel_types": fuel_types,
        "makes": makes,
    }


def load_vehicle_data() -> Dict[str, Any]:
    defaults = normalise_vehicle_data(default_vehicle_data())
    if not SITE_BUCKET or not VEHICLE_DATA_KEY:
        return defaults
    try:
        resp = s3.get_object(Bucket=SITE_BUCKET, Key=VEHICLE_DATA_KEY)
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        return normalise_vehicle_data(payload)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code") or "")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return defaults
        raise
    except Exception:
        return defaults


def save_vehicle_data(payload: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    data = normalise_vehicle_data(payload)
    data["updated_at"] = utc_now()
    data["updated_by"] = str(claims.get("email") or claims.get("sub") or "admin")
    s3.put_object(
        Bucket=SITE_BUCKET,
        Key=VEHICLE_DATA_KEY,
        Body=json.dumps(data, indent=2).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="no-store",
    )
    if SITE_DISTRIBUTION_ID:
        try:
            cloudfront.create_invalidation(
                DistributionId=SITE_DISTRIBUTION_ID,
                InvalidationBatch={
                    "Paths": {"Quantity": 1, "Items": [f"/{VEHICLE_DATA_KEY}"]},
                    "CallerReference": f"vehicle-data-{datetime.now(timezone.utc).timestamp()}",
                },
            )
        except Exception:
            pass
    return data


def member_vehicle_key(sub: str, vehicle_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": member_pk(sub)}, "sk": {"S": f"VEHICLE#{vehicle_id}"}}


def clean_vehicle_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.match(r"^[A-Za-z0-9_-]{6,96}$", text) else ""


def new_vehicle_id() -> str:
    return "veh_" + secrets.token_urlsafe(12).replace("-", "_")



def normalise_vehicle_status(value: Any) -> str:
    text = clean_vehicle_text(value, 32).lower().replace(" ", "_").replace("-", "_")
    if text in {"disposed", "inactive", "no_longer_owned", "sold", "scrapped", "written_off"}:
        return "disposed"
    return "active"


def parse_vehicle_expiry_date(value: Any) -> Any:
    text = clean_vehicle_text(value, 10)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def normalise_vehicle_registration_type(value: Any, *, historic_classic: Any = None) -> str:
    text = clean_vehicle_text(value, 24).lower().replace(" ", "_").replace("-", "_")
    if text in {"historic", "classic", "full"}:
        return text
    return "historic" if bool(historic_classic) else "full"


def normalise_classic_scheme_body(value: Any) -> str:
    text = clean_vehicle_text(value, 12).upper().replace(" ", "")
    return text if text in {"CMC", "ACMC"} else ""


def vehicle_record_file_summary(value: Any, *, include_url: bool = False) -> Dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    key = str(data.get("key") or "").strip()
    out = {
        "file_id": str(data.get("file_id") or ""),
        "filename": clean_vehicle_text(data.get("filename"), 160),
        "content_type": clean_vehicle_text(data.get("content_type"), 120),
        "size_bytes": int(data.get("size_bytes") or 0),
        "key": key,
        "uploaded_at": clean_vehicle_text(data.get("uploaded_at"), 40),
        "uploaded_by": clean_vehicle_text(data.get("uploaded_by"), 120),
    }
    if include_url and key.startswith(HISTORIC_REGO_STORAGE_PREFIX):
        out["download_url"] = historic_rego_presigned_download(out, inline=True)
    return out if key else {}


def vehicle_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    vehicle_id = str(item.get("vehicle_id") or str(item.get("sk") or "").replace("VEHICLE#", "", 1)).strip()
    status = normalise_vehicle_status(item.get("vehicle_status") or item.get("status") or "active")
    reminders_enabled = item.get("registration_reminders_enabled")
    if reminders_enabled is None:
        reminders_enabled = status != "disposed"
    return {
        "vehicle_id": vehicle_id,
        "make": clean_vehicle_text(item.get("make"), 64),
        "model": clean_vehicle_text(item.get("model"), 64),
        "variant": clean_vehicle_text(item.get("variant"), 64),
        "fuel_type": clean_vehicle_text(item.get("fuel_type"), 64),
        "specific_build": clean_vehicle_text(item.get("specific_build"), 160),
        "year": clean_vehicle_text(item.get("year"), 16),
        "rego_number": clean_vehicle_text(item.get("rego_number"), 32),
        "registration_expiry_date": clean_vehicle_text(item.get("registration_expiry_date"), 10),
        "historic_classic": bool(item.get("historic_classic")),
        "registration_type": normalise_vehicle_registration_type(item.get("registration_type"), historic_classic=item.get("historic_classic")),
        "classic_scheme_body": normalise_classic_scheme_body(item.get("classic_scheme_body")),
        "classic_form_file": vehicle_record_file_summary(item.get("classic_form_file")),
        "declaration_form_file": vehicle_record_file_summary(item.get("declaration_form_file")),
        "vin_serial_number": clean_vehicle_text(item.get("vin_serial_number"), 80),
        "vehicle_status": status,
        "disposed_at": clean_vehicle_text(item.get("disposed_at"), 32),
        "disposed_reason": clean_vehicle_text(item.get("disposed_reason"), 64),
        "registration_reminders_enabled": bool(reminders_enabled),
        "registration_reminder_status": clean_vehicle_text(item.get("registration_reminder_status"), 40),
        "registration_next_reminder_date": clean_vehicle_text(item.get("registration_next_reminder_date"), 10),
        "registration_last_reminder_sent_at": clean_vehicle_text(item.get("registration_last_reminder_sent_at"), 32),
        "registration_reminder_count": int(item.get("registration_reminder_count") or 0),
        "registration_final_notice_sent_at": clean_vehicle_text(item.get("registration_final_notice_sent_at"), 32),
        "registration_reminders_stopped_reason": clean_vehicle_text(item.get("registration_reminders_stopped_reason"), 80),
        "registration_last_response_at": clean_vehicle_text(item.get("registration_last_response_at"), 32),
        "created_at": clean_vehicle_text(item.get("created_at"), 32),
        "updated_at": clean_vehicle_text(item.get("updated_at"), 32),
    }


def validate_vehicle_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    year = clean_vehicle_text(body.get("year"), 16)
    if year and not re.match(r"^\d{4}$", year):
        raise ValueError("Year must be a four digit year or blank.")
    registration_type = normalise_vehicle_registration_type(body.get("registration_type"), historic_classic=body.get("historic_classic"))
    return {
        "make": clean_vehicle_text(body.get("make"), 64),
        "model": clean_vehicle_text(body.get("model"), 64),
        "variant": clean_vehicle_text(body.get("variant"), 64),
        "fuel_type": clean_vehicle_text(body.get("fuel_type"), 64),
        "specific_build": clean_vehicle_text(body.get("specific_build"), 160),
        "year": year,
        "rego_number": clean_vehicle_text(body.get("rego_number"), 32),
        "registration_expiry_date": clean_vehicle_date(body.get("registration_expiry_date"), "registration_expiry_date"),
        "registration_type": registration_type,
        "historic_classic": registration_type in {"historic", "classic"},
        "classic_scheme_body": normalise_classic_scheme_body(body.get("classic_scheme_body")),
        "vin_serial_number": clean_vehicle_text(body.get("vin_serial_number"), 80),
    }


def list_member_vehicles(sub: str) -> List[Dict[str, Any]]:
    require_metadata_table()
    vehicles: List[Dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": member_pk(sub)}, ":prefix": {"S": "VEHICLE#"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.query(**kwargs)
        vehicles.extend(vehicle_summary(item_to_python(item)) for item in resp.get("Items") or [])
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    vehicles.sort(key=lambda item: (str(item.get("vehicle_status") or "active") != "active", str(item.get("make") or "").lower(), str(item.get("model") or "").lower(), str(item.get("year") or ""), str(item.get("rego_number") or "").lower(), str(item.get("created_at") or "")))
    return vehicles


def get_member_vehicle_item(sub: str, vehicle_id: str) -> Dict[str, Any] | None:
    vid = clean_vehicle_id(vehicle_id)
    if not vid:
        return None
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=member_vehicle_key(sub, vid), ConsistentRead=True)
    if not resp.get("Item"):
        return None
    return item_to_python(resp["Item"])


def get_member_vehicle(sub: str, vehicle_id: str) -> Dict[str, Any] | None:
    item = get_member_vehicle_item(sub, vehicle_id)
    return vehicle_summary(item) if item else None


def reset_vehicle_registration_reminder_state(item: Dict[str, Any], *, enable: bool = True) -> None:
    item["registration_reminders_enabled"] = bool(enable)
    item["registration_reminder_status"] = ""
    item["registration_next_reminder_date"] = ""
    item["registration_last_reminder_sent_at"] = ""
    item["registration_reminder_count"] = 0
    item["registration_final_notice_sent_at"] = ""
    item["registration_reminders_stopped_reason"] = ""


def save_member_vehicle(sub: str, body: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_metadata_table()
    vehicle_id = clean_vehicle_id(body.get("vehicle_id")) or new_vehicle_id()
    existing = get_member_vehicle_item(sub, vehicle_id) or {}
    now = utc_now()
    payload = validate_vehicle_payload(body)
    existing_expiry = clean_vehicle_text(existing.get("registration_expiry_date"), 10)
    new_expiry = clean_vehicle_text(payload.get("registration_expiry_date"), 10)
    item = {
        "pk": member_pk(sub),
        "sk": f"VEHICLE#{vehicle_id}",
        "item_type": "vehicle",
        "member_sub": sub,
        "vehicle_id": vehicle_id,
        **payload,
        "vehicle_status": normalise_vehicle_status(existing.get("vehicle_status") or existing.get("status") or "active"),
        "disposed_at": clean_vehicle_text(existing.get("disposed_at"), 32),
        "disposed_reason": clean_vehicle_text(existing.get("disposed_reason"), 64),
        "registration_reminders_enabled": existing.get("registration_reminders_enabled") if existing.get("registration_reminders_enabled") is not None else True,
        "registration_reminder_status": clean_vehicle_text(existing.get("registration_reminder_status"), 40),
        "registration_next_reminder_date": clean_vehicle_text(existing.get("registration_next_reminder_date"), 10),
        "registration_last_reminder_sent_at": clean_vehicle_text(existing.get("registration_last_reminder_sent_at"), 32),
        "registration_reminder_count": int(existing.get("registration_reminder_count") or 0),
        "registration_final_notice_sent_at": clean_vehicle_text(existing.get("registration_final_notice_sent_at"), 32),
        "registration_reminders_stopped_reason": clean_vehicle_text(existing.get("registration_reminders_stopped_reason"), 80),
        "registration_last_response_at": clean_vehicle_text(existing.get("registration_last_response_at"), 32),
        "classic_form_file": existing.get("classic_form_file") if isinstance(existing.get("classic_form_file"), dict) else {},
        "declaration_form_file": existing.get("declaration_form_file") if isinstance(existing.get("declaration_form_file"), dict) else {},
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or "member"),
    }
    # If the member changes or adds an expiry date, restart reminder tracking.
    if new_expiry != existing_expiry:
        if item["vehicle_status"] == "disposed":
            item["registration_reminders_enabled"] = False
        else:
            reset_vehicle_registration_reminder_state(item, enable=bool(new_expiry))
    if item["vehicle_status"] == "disposed":
        item["registration_reminders_enabled"] = False
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return vehicle_summary(item)


def delete_member_vehicle(sub: str, vehicle_id: str) -> Dict[str, Any]:
    require_metadata_table()
    vid = clean_vehicle_id(vehicle_id)
    if not vid:
        raise ValueError("vehicle_id is required.")
    ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=member_vehicle_key(sub, vid))
    return {"vehicle_id": vid, "deleted": True}


MAINTENANCE_TYPES = [
    "Service", "Repair", "Inspection", "Tyres", "Fluids", "Electrical", "Suspension", "Brakes", "Registration / roadworthy", "Upgrade / modification", "Other",
]


def maintenance_log_vehicle_prefix(vehicle_id: str) -> str:
    return f"MAINTENANCE#VEHICLE#{clean_vehicle_id(vehicle_id)}#"


def clean_maintenance_cost(value: Any) -> str:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return ""
    try:
        amount = round(float(text), 2)
    except Exception:
        raise ValueError("Maintenance cost must be a valid number.")
    if amount < 0 or amount > 1000000:
        raise ValueError("Maintenance cost is outside the allowed range.")
    return f"{amount:.2f}"


def normalise_maintenance_type(value: Any) -> str:
    text = clean_vehicle_text(value, 80)
    if not text:
        return "Other"
    for option in MAINTENANCE_TYPES:
        if option.lower() == text.lower():
            return option
    return text[:80]


def maintenance_log_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "log_id": str(item.get("log_id") or str(item.get("sk") or "").split("#")[-1]).strip(),
        "vehicle_id": clean_vehicle_id(item.get("vehicle_id")),
        "vehicle_title": clean_vehicle_text(item.get("vehicle_title"), 180),
        "maintenance_date": clean_vehicle_text(item.get("maintenance_date"), 10),
        "odometer": clean_vehicle_text(item.get("odometer"), 32),
        "maintenance_type": clean_vehicle_text(item.get("maintenance_type"), 80),
        "title": clean_vehicle_text(item.get("title"), 160),
        "description": str(item.get("description") or "").strip()[:4000],
        "provider": clean_vehicle_text(item.get("provider"), 160),
        "cost": clean_vehicle_text(item.get("cost"), 32),
        "currency": clean_vehicle_text(item.get("currency") or "AUD", 12),
        "next_due_date": clean_vehicle_text(item.get("next_due_date"), 10),
        "next_due_odometer": clean_vehicle_text(item.get("next_due_odometer"), 32),
        "notes": str(item.get("notes") or "").strip()[:2000],
        "created_at": clean_vehicle_text(item.get("created_at"), 32),
        "updated_at": clean_vehicle_text(item.get("updated_at"), 32),
    }


def get_maintenance_vehicle_title(sub: str, vehicle_id: str) -> str:
    vehicle = get_member_vehicle(sub, vehicle_id)
    if not vehicle:
        return ""
    bits = [vehicle.get("year"), vehicle.get("make"), vehicle.get("model"), vehicle.get("rego_number")]
    return " ".join(str(x).strip() for x in bits if str(x or "").strip())[:180]


def validate_maintenance_payload(sub: str, body: Dict[str, Any]) -> Dict[str, Any]:
    vehicle_id = clean_vehicle_id(body.get("vehicle_id"))
    if not vehicle_id:
        raise ValueError("Vehicle is required for a maintenance log entry.")
    if not get_member_vehicle(sub, vehicle_id):
        raise ValueError("Vehicle was not found in your registry.")
    date = clean_vehicle_date(body.get("maintenance_date") or datetime.now(ZoneInfo(CLUB_TIME_ZONE)).date().isoformat(), "maintenance_date")
    title = clean_vehicle_text(body.get("title"), 160)
    description = str(body.get("description") or "").strip()[:4000]
    if not title and not description:
        raise ValueError("Add a short title or maintenance description.")
    return {
        "vehicle_id": vehicle_id,
        "vehicle_title": get_maintenance_vehicle_title(sub, vehicle_id),
        "maintenance_date": date,
        "odometer": clean_vehicle_text(body.get("odometer"), 32),
        "maintenance_type": normalise_maintenance_type(body.get("maintenance_type")),
        "title": title or description[:80],
        "description": description,
        "provider": clean_vehicle_text(body.get("provider"), 160),
        "cost": clean_maintenance_cost(body.get("cost")),
        "currency": clean_vehicle_text(body.get("currency") or "AUD", 12),
        "next_due_date": clean_vehicle_date(body.get("next_due_date"), "next_due_date") if str(body.get("next_due_date") or "").strip() else "",
        "next_due_odometer": clean_vehicle_text(body.get("next_due_odometer"), 32),
        "notes": str(body.get("notes") or "").strip()[:2000],
    }


def list_vehicle_maintenance_logs(sub: str, vehicle_id: str | None = None) -> List[Dict[str, Any]]:
    require_metadata_table()
    prefix = maintenance_log_vehicle_prefix(vehicle_id) if vehicle_id else "MAINTENANCE#VEHICLE#"
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": {"S": member_pk(sub)}, ":prefix": {"S": prefix}},
        ScanIndexForward=False,
        Limit=300,
    )
    items = [maintenance_log_summary(item_to_python(item)) for item in resp.get("Items") or []]
    items.sort(key=lambda item: (str(item.get("maintenance_date") or ""), str(item.get("updated_at") or "")), reverse=True)
    return items


def save_vehicle_maintenance_log(sub: str, body: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    payload = validate_maintenance_payload(sub, body)
    existing_id = clean_vehicle_id(body.get("log_id"))
    log_id = existing_id or uuid.uuid4().hex
    now = utc_now_precise()
    existing = {}
    if existing_id:
        existing = next((x for x in list_vehicle_maintenance_logs(sub) if x.get("log_id") == existing_id), {})
    item = {
        **payload,
        "pk": member_pk(sub),
        "sk": maintenance_log_vehicle_prefix(payload["vehicle_id"]) + log_id,
        "item_type": "vehicle_maintenance_log",
        "log_id": log_id,
        "created_at": existing.get("created_at") or now,
        "created_by": existing.get("created_by") or str(claims.get("sub") or ""),
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or ""),
    }
    if existing_id and existing.get("vehicle_id") and existing.get("vehicle_id") != payload["vehicle_id"]:
        ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": member_pk(sub)}, "sk": {"S": maintenance_log_vehicle_prefix(existing.get("vehicle_id")) + existing_id}})
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return maintenance_log_summary(item)


def delete_vehicle_maintenance_log(sub: str, log_id: str) -> Dict[str, Any]:
    clean_id = clean_vehicle_id(log_id)
    if not clean_id:
        raise ValueError("log_id is required.")
    match = next((item for item in list_vehicle_maintenance_logs(sub) if item.get("log_id") == clean_id), None)
    if match:
        ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": member_pk(sub)}, "sk": {"S": maintenance_log_vehicle_prefix(match.get("vehicle_id")) + clean_id}})
    return {"log_id": clean_id, "deleted": True}


def vehicle_maintenance_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or claims.get("cognito:username") or "").strip()
    if not sub:
        raise PermissionError("Member authentication is required.")
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "GET":
        params = get_query_params(event)
        vehicle_id = clean_vehicle_id(params.get("vehicle_id")) if params.get("vehicle_id") else None
        return response(200, {"items": list_vehicle_maintenance_logs(sub, vehicle_id), "types": MAINTENANCE_TYPES, "vehicles": list_member_vehicles(sub)})
    body = parse_body(event)
    item = save_vehicle_maintenance_log(sub, body, claims)
    return response(200, {"message": "Maintenance log entry saved.", "item": item, "items": list_vehicle_maintenance_logs(sub, item.get("vehicle_id"))})


def vehicle_maintenance_delete_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or claims.get("cognito:username") or "").strip()
    if not sub:
        raise PermissionError("Member authentication is required.")
    body = parse_body(event)
    return response(200, delete_vehicle_maintenance_log(sub, body.get("log_id")))


def save_vehicle_registration_response_audit(sub: str, vehicle: Dict[str, Any], action: str, claims: Dict[str, Any], details: Dict[str, Any] | None = None) -> None:
    try:
        now = utc_now_precise()
        item = {
            "pk": member_pk(sub),
            "sk": f"AUDIT#VEHICLE_REGISTRATION#{vehicle.get('vehicle_id') or 'unknown'}#{now}",
            "item_type": "vehicle_registration_response_audit",
            "member_sub": sub,
            "vehicle_id": str(vehicle.get("vehicle_id") or ""),
            "rego_number": str(vehicle.get("rego_number") or ""),
            "registration_expiry_date": str(vehicle.get("registration_expiry_date") or ""),
            "action": action,
            "details": details or {},
            "created_at": now,
            "created_by": str(claims.get("email") or claims.get("sub") or "member"),
        }
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    except Exception:
        pass


def update_member_vehicle_registration_response(sub: str, vehicle_id: str, action: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    require_metadata_table()
    vehicle = get_member_vehicle_item(sub, vehicle_id)
    if not vehicle:
        raise ValueError("Selected vehicle was not found in your vehicle registry.")
    action = clean_vehicle_text(action, 32).lower().replace("-", "_").replace(" ", "_")
    if action not in {"renewed", "remind_later", "disposed", "restore_active"}:
        raise ValueError("Unknown registration response.")
    now = utc_now()
    today = current_club_date()
    details: Dict[str, Any] = {}

    if action == "renewed":
        expiry = parse_vehicle_expiry_date(vehicle.get("registration_expiry_date"))
        if not expiry:
            raise ValueError("This vehicle does not have a valid registration expiry date.")
        new_expiry = add_months_to_date(expiry, 12).isoformat()
        vehicle["registration_expiry_date"] = new_expiry
        vehicle["vehicle_status"] = "active"
        vehicle["disposed_at"] = ""
        vehicle["disposed_reason"] = ""
        reset_vehicle_registration_reminder_state(vehicle, enable=True)
        vehicle["registration_last_response_at"] = now
        details = {"new_registration_expiry_date": new_expiry}
        message = f"Registration expiry updated to {new_expiry}."
    elif action == "remind_later":
        if clean_vehicle_text(vehicle.get("registration_reminders_stopped_reason"), 80) == "expired_more_than_3_months":
            raise ValueError("The final registration reminder has already been sent for this vehicle. Please update the expiry date if it has been renewed, or mark the vehicle no longer owned.")
        vehicle["vehicle_status"] = "active"
        vehicle["registration_reminders_enabled"] = True
        vehicle["registration_reminder_status"] = "pending_confirmation"
        vehicle["registration_next_reminder_date"] = add_months_to_date(today, 1).isoformat()
        vehicle["registration_last_response_at"] = now
        details = {"next_reminder_date": vehicle["registration_next_reminder_date"]}
        message = f"Okay — we will remind you again around {vehicle['registration_next_reminder_date']}."
    elif action == "disposed":
        vehicle["vehicle_status"] = "disposed"
        vehicle["disposed_at"] = now
        vehicle["disposed_reason"] = "no_longer_owned"
        vehicle["registration_reminders_enabled"] = False
        vehicle["registration_reminder_status"] = "stopped"
        vehicle["registration_next_reminder_date"] = ""
        vehicle["registration_reminders_stopped_reason"] = "disposed"
        vehicle["registration_last_response_at"] = now
        details = {"disposed_at": now}
        message = "Vehicle moved to your no-longer-owned history and registration reminders stopped."
    else:
        vehicle["vehicle_status"] = "active"
        vehicle["disposed_at"] = ""
        vehicle["disposed_reason"] = ""
        vehicle["registration_reminders_enabled"] = bool(vehicle.get("registration_expiry_date"))
        vehicle["registration_reminder_status"] = ""
        vehicle["registration_next_reminder_date"] = ""
        vehicle["registration_reminders_stopped_reason"] = ""
        vehicle["registration_last_response_at"] = now
        details = {"restored_at": now}
        message = "Vehicle restored to your active registry."

    vehicle["updated_at"] = now
    vehicle["updated_by"] = str(claims.get("email") or claims.get("sub") or "member")
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(vehicle))
    save_vehicle_registration_response_audit(sub, vehicle, action, claims, details)
    return {"message": message, "item": vehicle_summary(vehicle)}

def resolve_historic_rego_position() -> Dict[str, Any] | None:
    """Return the configured Historic Vehicle Registration role/position.

    The email address is deliberately role-driven rather than hard-coded so the
    club can change coordinators without changing website code.
    """
    positions = list_club_positions(include_defaults=True)
    best: Dict[str, Any] | None = None
    for position in positions:
        pid = normalise_position_id(position.get("position_id") or "", str(position.get("position_name") or ""))
        pname_id = normalise_position_id(position.get("position_name") or "")
        if pid in HISTORIC_REGO_POSITION_IDS or pname_id in HISTORIC_REGO_POSITION_IDS:
            best = position
            if valid_email_address(position.get("email_address") or "") and position.get("active", True) is not False:
                return position
    return best


def member_display_name_from_metadata(meta: Dict[str, Any], claims: Dict[str, Any]) -> str:
    parts = [str(meta.get("first_name") or "").strip(), str(meta.get("middle_name") or "").strip(), str(meta.get("last_name") or "").strip()]
    name = " ".join([p for p in parts if p]).strip()
    return name or str(meta.get("name") or claims.get("name") or claims.get("preferred_username") or claims.get("email") or "Member").strip()


def address_block_from_metadata(meta: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    fields = [
        str(meta.get(f"{prefix}address1") or "").strip(),
        str(meta.get(f"{prefix}address2") or "").strip(),
        str(meta.get(f"{prefix}city") or "").strip(),
        str(meta.get(f"{prefix}state") or "").strip(),
        str(meta.get(f"{prefix}postcode") or "").strip(),
        str(meta.get(f"{prefix}country") or "").strip(),
    ]
    visible = [x for x in fields if x]
    required = [fields[0], fields[2], fields[3], fields[4]]
    return {"lines": visible, "text": "\n".join(visible), "complete": all(required)}


def clean_historic_rego_notes(value: Any) -> str:
    return clean_multiline_field(value, 3000)


def clean_historic_rego_filename(value: Any, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(value or "").strip()).strip(" .")
    return (name or fallback)[:140]


def normalise_historic_rego_images(raw_images: Any) -> List[Dict[str, Any]]:
    if raw_images in (None, ""):
        return []
    if not isinstance(raw_images, list):
        raise ValueError("images must be a list.")
    if len(raw_images) > HISTORIC_REGO_MAX_IMAGES:
        raise ValueError(f"Please attach no more than {HISTORIC_REGO_MAX_IMAGES} images.")
    images: List[Dict[str, Any]] = []
    total_bytes = 0
    for idx, raw in enumerate(raw_images, start=1):
        if not isinstance(raw, dict):
            raise ValueError("Each image must be an object.")
        content_type = str(raw.get("content_type") or raw.get("contentType") or "").strip().lower()
        filename = clean_historic_rego_filename(raw.get("filename") or raw.get("name"), f"historic-rego-image-{idx}")
        if not content_type:
            guessed = mimetypes.guess_type(filename)[0] or ""
            content_type = guessed.strip().lower()
        if content_type == "image/jpg":
            content_type = "image/jpeg"
        if content_type not in HISTORIC_REGO_IMAGE_TYPES:
            raise ValueError("Historic rego images must be JPG, PNG, or WebP.")
        data = str(raw.get("data") or raw.get("base64") or "").strip()
        if "," in data and data.lower().startswith("data:"):
            data = data.split(",", 1)[1]
        data = re.sub(r"\s+", "", data)
        if not data:
            raise ValueError("Each image must include base64 data.")
        try:
            blob = base64.b64decode(data, validate=True)
        except Exception:
            raise ValueError("One of the selected images could not be decoded.")
        if len(blob) > HISTORIC_REGO_MAX_IMAGE_BYTES:
            raise ValueError(f"Each image must be under {HISTORIC_REGO_MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
        total_bytes += len(blob)
        if total_bytes > HISTORIC_REGO_MAX_TOTAL_IMAGE_BYTES:
            raise ValueError(f"Selected images are too large. Please keep the total under {HISTORIC_REGO_MAX_TOTAL_IMAGE_BYTES // (1024 * 1024)} MB.")
        ext = HISTORIC_REGO_IMAGE_TYPES[content_type]
        if not os.path.splitext(filename)[1]:
            filename = f"{filename}.{ext}"
        cid = f"historic-rego-{idx}-{hashlib.sha1(blob).hexdigest()[:12]}@lroc"
        images.append({"filename": filename, "content_type": content_type, "bytes": blob, "cid": cid, "size_bytes": len(blob)})
    return images


def historic_rego_detail_rows(member: Dict[str, Any], vehicle: Dict[str, Any], claims: Dict[str, Any]) -> List[tuple[str, str]]:
    return [
        ("Member name", member_display_name_from_metadata(member, claims)),
        ("Member number", str(member.get("member_number") or member.get("site_member_id") or "").strip()),
        ("Contact email", normalise_email_address(member.get("email") or claims.get("email") or "")),
        ("Mobile", str(member.get("mobile") or "").strip()),
        ("Phone", str(member.get("phone") or member.get("phone_number") or "").strip()),
        ("Vehicle", " ".join([str(vehicle.get("year") or "").strip(), str(vehicle.get("make") or "").strip(), str(vehicle.get("model") or "").strip(), str(vehicle.get("variant") or "").strip()]).strip()),
        ("Specific build", str(vehicle.get("specific_build") or "").strip()),
        ("Registration number", str(vehicle.get("rego_number") or "").strip()),
        ("Registration expiry", str(vehicle.get("registration_expiry_date") or "").strip()),
        ("VIN / serial", str(vehicle.get("vin_serial_number") or "").strip()),
        ("Fuel type", str(vehicle.get("fuel_type") or "").strip()),
        ("Historic / Classic", "Yes" if vehicle.get("historic_classic") else "No"),
    ]


def build_historic_rego_email(member: Dict[str, Any], vehicle: Dict[str, Any], claims: Dict[str, Any], notes: str, images: List[Dict[str, Any]], recipient: Dict[str, Any]) -> Dict[str, Any]:
    member_number = str(member.get("member_number") or member.get("site_member_id") or "").strip()
    rego = str(vehicle.get("rego_number") or "").strip()
    vehicle_title = " ".join([str(vehicle.get("year") or "").strip(), str(vehicle.get("make") or "").strip(), str(vehicle.get("model") or "").strip()]).strip() or "vehicle"
    subject_bits = ["Historic Vehicle Registration information"]
    if member_number:
        subject_bits.append(f"Member {member_number}")
    if rego:
        subject_bits.append(rego)
    subject = " - ".join(subject_bits)
    postal = address_block_from_metadata(member, "postal_")
    residential = address_block_from_metadata(member, "")
    postal_text = postal["text"] or "Not supplied"
    residential_text = residential["text"] or "Not supplied"
    rows = historic_rego_detail_rows(member, vehicle, claims)
    row_text = "\n".join(f"{label}: {value or 'Not supplied'}" for label, value in rows)
    notes_text = notes or "No extra notes supplied."
    image_text = "\n".join(f"- {img['filename']} ({img['size_bytes']} bytes)" for img in images) or "No images attached."
    text_body = (
        "Land Rover Owners Club of Australia Inc\n"
        "Historic Vehicle Registration information\n\n"
        f"Submitted at: {utc_now_precise()}\n\n"
        "Member and vehicle details\n"
        "--------------------------\n"
        f"{row_text}\n\n"
        "Postal address for declaration\n"
        "------------------------------\n"
        f"{postal_text}\n"
        + ("\nWARNING: Postal address appears incomplete.\n" if not postal["complete"] else "")
        + "\nResidential address\n"
        "-------------------\n"
        f"{residential_text}\n"
        + ("\nWARNING: Residential address appears incomplete.\n" if not residential["complete"] else "")
        + "\nMember notes\n"
        "------------\n"
        f"{notes_text}\n\n"
        "Images\n"
        "------\n"
        f"{image_text}\n"
    )
    html_rows = "".join(f"<tr><th style='text-align:left;padding:7px 10px;border-bottom:1px solid #e5e7eb;width:210px'>{html.escape(label)}</th><td style='padding:7px 10px;border-bottom:1px solid #e5e7eb'>{html.escape(value or 'Not supplied')}</td></tr>" for label, value in rows)
    def address_html(title: str, block: Dict[str, Any]) -> str:
        body = "<br>".join(html.escape(line) for line in block["lines"]) or "Not supplied"
        warn = "<p style='margin:8px 0 0;color:#9a3412;font-weight:700'>Address appears incomplete.</p>" if not block["complete"] else ""
        return f"<h3 style='color:#143b2d;margin:20px 0 8px'>{html.escape(title)}</h3><p style='margin:0'>{body}</p>{warn}"
    image_html = ""
    if images:
        image_html = "<h3 style='color:#143b2d;margin:20px 0 8px'>Images</h3>" + "".join(
            f"<figure style='margin:14px 0;padding:10px;border:1px solid #e5e7eb;border-radius:12px'><img src='cid:{html.escape(img['cid'])}' alt='{html.escape(img['filename'])}' style='max-width:100%;height:auto;border-radius:8px'><figcaption style='font-size:12px;color:#6b7280;margin-top:6px'>{html.escape(img['filename'])}</figcaption></figure>"
            for img in images
        )
    else:
        image_html = "<h3 style='color:#143b2d;margin:20px 0 8px'>Images</h3><p>No images attached.</p>"
    html_body = (
        "<div style='font-family:Arial,sans-serif;line-height:1.55;color:#111827'>"
        "<div style='border-bottom:3px solid #7f1d1d;padding-bottom:12px;margin-bottom:18px'>"
        "<strong style='font-size:18px;color:#7f1d1d'>LROC</strong><br>"
        "<span>Land Rover Owners Club of Australia Inc</span><br>"
        "<span>Historic Vehicle Registration information</span>"
        "</div>"
        f"<p><strong>Submitted at:</strong> {html.escape(utc_now_precise())}</p>"
        f"<p>This request is for <strong>{html.escape(vehicle_title)}</strong>{' / ' + html.escape(rego) if rego else ''}.</p>"
        "<h3 style='color:#143b2d;margin:20px 0 8px'>Member and vehicle details</h3>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{html_rows}</table>"
        f"{address_html('Postal address for declaration', postal)}"
        f"{address_html('Residential address', residential)}"
        "<h3 style='color:#143b2d;margin:20px 0 8px'>Member notes</h3>"
        f"<p>{html.escape(notes_text).replace(chr(10), '<br>')}</p>"
        f"{image_html}"
        "</div>"
    )
    return {"subject": subject, "text": text_body, "html": html_body}


def send_historic_rego_raw_email(to_email: str, subject: str, text_body: str, html_body: str, images: List[Dict[str, Any]], reply_to: str = "") -> Dict[str, Any]:
    from_addr = lroc_from_header(SES_FROM_EMAIL)
    root = MIMEMultipart("related")
    root["Subject"] = subject
    root["From"] = from_addr
    root["To"] = to_email
    reply = clean_header_address(reply_to or SES_REPLY_TO_EMAIL or SES_FROM_EMAIL)
    if reply:
        root["Reply-To"] = reply
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    root.attach(alt)
    for img in images:
        subtype = HISTORIC_REGO_IMAGE_TYPES.get(img["content_type"], "jpeg")
        if subtype == "jpg":
            subtype = "jpeg"
        part = MIMEBase("image", subtype)
        part.set_payload(img["bytes"])
        encoders.encode_base64(part)
        part.add_header("Content-ID", f"<{img['cid']}>")
        part.add_header("Content-Disposition", "inline", filename=img["filename"])
        root.attach(part)
    return send_raw_email_via_ses([to_email], root.as_bytes(), from_email=SES_FROM_EMAIL, reply_to=reply)


def build_historic_rego_confirmation_email(member: Dict[str, Any], vehicle: Dict[str, Any], coordinator_email: str, coordinator_name: str, message_id: str) -> Dict[str, str]:
    vehicle_title = vehicle_reminder_title(vehicle)
    subject = f"Historic Registration details sent - {vehicle_title}"
    paragraphs = [
        f"Your Historic Vehicle Registration renewal details for {vehicle_title} have been sent to the Historic Registration coordinator.",
        "The coordinator will review the supplied vehicle information and images and contact you if anything else is needed.",
    ]
    rows = [
        ("Vehicle", vehicle_title),
        ("Registration number", str(vehicle.get("rego_number") or "").strip()),
        ("Registration expiry", str(vehicle.get("registration_expiry_date") or "").strip()),
        ("Coordinator", coordinator_name or "Historic Vehicle Registration"),
        ("Coordinator email", coordinator_email),
        ("SES message ID", message_id),
    ]
    text = "Land Rover Owners Club of Australia Inc\n\n" + "\n\n".join(paragraphs) + "\n\n" + "\n".join(f"{label}: {value or 'Not supplied'}" for label, value in rows)
    html_body = simple_html_email(subject, paragraphs, rows)
    return {"subject": subject, "text": text, "html": html_body}


def notify_member_historic_rego_sent(sub: str, member: Dict[str, Any], vehicle: Dict[str, Any], coordinator_email: str, coordinator_name: str, message_id: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"push_queued": False, "email_sent": False, "email_skipped_reason": ""}
    vehicle_title = vehicle_reminder_title(vehicle)
    try:
        result["push_queued"] = enqueue_direct_push_notification(
            sub,
            "Historic Rego details sent",
            f"Registration renewal details for {vehicle_title} have been sent to the Historic Registration coordinator.",
            data={
                "url": f"/profile.html#vehicles",
                "kind": "historic_rego_submission_confirmation",
                "vehicle_id": str(vehicle.get("vehicle_id") or ""),
            },
            tag=f"historic-rego-sent-{vehicle.get('vehicle_id') or 'vehicle'}",
        )
    except Exception:
        result["push_queued"] = False
    email_to = member_email_from_metadata(member)
    if not email_to:
        result["email_skipped_reason"] = "member_email_not_configured"
    else:
        mail = build_historic_rego_confirmation_email(member, vehicle, coordinator_email, coordinator_name, message_id)
        sent = safe_send_email_via_ses([email_to], mail["subject"], mail["text"], mail["html"])
        result["email_sent"] = bool(sent.get("sent"))
        if not result["email_sent"]:
            result["email_skipped_reason"] = str(sent.get("reason") or "send_failed")
    return result


def save_historic_rego_submission_audit(sub: str, vehicle: Dict[str, Any], recipient: str, notes: str, images: List[Dict[str, Any]], message_id: str, claims: Dict[str, Any]) -> None:
    try:
        now = utc_now_precise()
        safe_now = re.sub(r"[^0-9A-Za-z]+", "", now)
        item = {
            "pk": member_pk(sub),
            "sk": f"HISTORIC_REGO#{safe_now}#{vehicle.get('vehicle_id') or ''}",
            "item_type": "historic_rego_submission",
            "member_sub": sub,
            "vehicle_id": str(vehicle.get("vehicle_id") or ""),
            "vehicle_snapshot": vehicle,
            "recipient_email": recipient,
            "notes_preview": notes[:500],
            "image_count": len(images),
            "image_filenames": [str(img.get("filename") or "") for img in images],
            "message_id": message_id,
            "created_at": now,
            "created_by": str(claims.get("email") or claims.get("sub") or "member"),
        }
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    except Exception:
        pass


def member_vehicle_historic_rego_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    body = parse_body(event)
    vehicle_id = clean_vehicle_id(body.get("vehicle_id"))
    if not vehicle_id:
        raise ValueError("vehicle_id is required.")
    vehicle = get_member_vehicle(sub, vehicle_id)
    if not vehicle:
        raise ValueError("Selected vehicle was not found in your vehicle register.")
    if not vehicle.get("historic_classic"):
        raise ValueError("Only vehicles marked Historic / Classic can be sent to Historic Vehicle Registration.")
    position = resolve_historic_rego_position()
    if not position:
        raise ValueError("Historic Vehicle Registration role is not configured yet. Please contact the club.")
    to_email = normalise_email_address(position.get("email_address") or "")
    if not valid_email_address(to_email) or position.get("active", True) is False:
        raise ValueError("Historic Vehicle Registration role email is not configured yet. Please contact the club.")
    if not ses_email_available():
        raise ValueError("Historic Vehicle Registration email sending is not configured yet. Please contact the club.")
    member = get_member_metadata(sub)
    notes = clean_historic_rego_notes(body.get("notes") or "")
    images = normalise_historic_rego_images(body.get("images") or [])
    mail = build_historic_rego_email(member, vehicle, claims, notes, images, position)
    reply_to = normalise_email_address(member.get("email") or claims.get("email") or "") or SES_REPLY_TO_EMAIL
    result = send_historic_rego_raw_email(to_email, mail["subject"], mail["text"], mail["html"], images, reply_to=reply_to)
    message_id = str(result.get("MessageId") or "")
    save_historic_rego_submission_audit(sub, vehicle, to_email, notes, images, message_id, claims)
    confirmation = notify_member_historic_rego_sent(
        sub,
        member,
        vehicle,
        to_email,
        str(position.get("position_name") or "Historic Vehicle Registration"),
        message_id,
    )
    return response(200, {
        "message": "Historic Vehicle Registration information sent.",
        "to_position": str(position.get("position_name") or "Historic Vehicle Registration"),
        "to_email": to_email,
        "message_id": message_id,
        "image_count": len(images),
        "member_confirmation": confirmation,
    })



# ---------------------------------------------------------------------------
# Historic / Classic Vehicle Registration submission workflow (v2.5.6)
# ---------------------------------------------------------------------------

def historic_rego_safe_segment(value: Any, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-_")
    return (text or fallback)[:100]


def historic_rego_current_key(sub: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": member_pk(sub)}, "sk": {"S": "HISTORIC_REGISTRATION#ACTIVE"}}


def historic_rego_file_key(sub: str, file_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": member_pk(sub)}, "sk": {"S": f"HISTORIC_REGISTRATION_FILE#{historic_rego_safe_segment(file_id, 'file')}"}}


def historic_rego_queue_key(request_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": "HISTORIC_REGISTRATION#QUEUE"}, "sk": {"S": f"REQUEST#{historic_rego_safe_segment(request_id, 'request')}"}}


def historic_rego_audit_sk(now: str, request_id: str, version: int) -> str:
    safe_now = re.sub(r"[^0-9A-Za-z]+", "", now)
    return f"HISTORIC_REGISTRATION_AUDIT#{safe_now}#{historic_rego_safe_segment(request_id, 'request')}#v{int(version or 1)}"


def historic_rego_file_id_for_key(key: str) -> str:
    return hashlib.sha1(str(key or "").encode("utf-8")).hexdigest()[:20]


def historic_rego_filename(value: Any, fallback: str = "attachment") -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(value or "").strip()).strip(" .")
    return (name or fallback)[:160]


def historic_rego_file_kind(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in {"photo", "certificate"} else "photo"


def historic_rego_normalise_slot(value: Any, *, allow_extra: bool = True) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"lh_side": "left_side", "left": "left_side", "rhs": "right_side", "rh_side": "right_side", "right": "right_side", "engine": "engine_bay", "bay": "engine_bay", "dash": "dashboard", "interior": "interior_seatbelts", "seatbelts": "interior_seatbelts", "seating": "interior_seatbelts", "interior_seating": "interior_seatbelts", "inspection": "certificate", "cert": "certificate"}
    text = aliases.get(text, text)
    allowed = set(HISTORIC_REGO_PHOTO_SLOTS) | {"certificate"}
    if allow_extra:
        allowed.add("extra")
    return text if text in allowed else ""


def historic_rego_content_type(filename: str, content_type: Any) -> str:
    ctype = str(content_type or "").strip().lower()
    if ctype == "image/jpg":
        ctype = "image/jpeg"
    if not ctype or ctype == "application/octet-stream":
        ctype = (mimetypes.guess_type(filename)[0] or "application/octet-stream").lower()
        if ctype == "image/jpg":
            ctype = "image/jpeg"
    return ctype[:120]


def historic_rego_make_upload_key(sub: str, file_id: str, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if len(ext) > 12 or not re.match(r"^\.[a-z0-9]+$", ext or ""):
        ext = ""
    return f"{HISTORIC_REGO_STORAGE_PREFIX}{historic_rego_safe_segment(sub, 'member')}/{historic_rego_safe_segment(file_id, 'file')}/{historic_rego_safe_segment(os.path.splitext(filename)[0], 'attachment')}{ext}"


def create_historic_registration_upload_url(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    body = parse_body(event)
    kind = historic_rego_file_kind(body.get("file_type") or body.get("kind"))
    filename = historic_rego_filename(body.get("filename") or body.get("name"), "historic-registration-file")
    content_type = historic_rego_content_type(filename, body.get("content_type") or body.get("contentType"))
    size = int(body.get("size") or 0)
    if kind == "photo":
        if content_type not in HISTORIC_REGO_IMAGE_TYPES:
            raise ValueError("Vehicle photos must be JPG, PNG, or WebP.")
        if size and size > HISTORIC_REGO_MAX_IMAGE_BYTES:
            raise ValueError(f"Vehicle photos must be no larger than {HISTORIC_REGO_MAX_IMAGE_BYTES // (1024 * 1024)} MB each.")
    else:
        if content_type not in HISTORIC_REGO_CERTIFICATE_TYPES:
            raise ValueError("Inspection certificates must be PDF, JPG, PNG, or WebP.")
        if size and size > HISTORIC_REGO_CERTIFICATE_MAX_BYTES:
            raise ValueError(f"Inspection certificates must be no larger than {HISTORIC_REGO_CERTIFICATE_MAX_BYTES // (1024 * 1024)} MB.")
    file_id = secrets.token_urlsafe(12)
    key = historic_rego_make_upload_key(sub, file_id, filename)
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type, "ServerSideEncryption": "AES256"},
        ExpiresIn=UPLOAD_EXPIRY,
        HttpMethod="PUT",
    )
    return response(200, {"upload_url": url, "key": key, "file_id": file_id, "filename": filename, "content_type": content_type, "max_bytes": HISTORIC_REGO_MAX_IMAGE_BYTES if kind == "photo" else HISTORIC_REGO_CERTIFICATE_MAX_BYTES})


def historic_rego_get_s3_file_record(sub: str, ref: Dict[str, Any]) -> Dict[str, Any]:
    key = str(ref.get("key") or ref.get("s3_key") or "").strip()
    if not key.startswith(f"{HISTORIC_REGO_STORAGE_PREFIX}{historic_rego_safe_segment(sub, 'member')}/"):
        raise ValueError("Invalid historic registration file reference.")
    filename = historic_rego_filename(ref.get("filename") or os.path.basename(key), "historic-registration-file")
    content_type = historic_rego_content_type(filename, ref.get("content_type") or ref.get("contentType"))
    file_type = historic_rego_file_kind(ref.get("file_type") or ref.get("kind"))
    slot = historic_rego_normalise_slot(ref.get("slot") or ref.get("label") or ("certificate" if file_type == "certificate" else "extra"))
    if file_type == "certificate":
        slot = "certificate"
        if content_type not in HISTORIC_REGO_CERTIFICATE_TYPES:
            raise ValueError("Inspection certificate must be PDF, JPG, PNG, or WebP.")
    else:
        if content_type not in HISTORIC_REGO_IMAGE_TYPES:
            raise ValueError("Vehicle photos must be JPG, PNG, or WebP.")
        if slot == "certificate":
            slot = "extra"
    try:
        head = s3.head_object(Bucket=BUCKET, Key=key)
    except ClientError as exc:
        raise ValueError(f"Uploaded file was not found: {filename}") from exc
    size = int(head.get("ContentLength") or 0)
    if size <= 0:
        raise ValueError(f"Uploaded file is empty: {filename}")
    if file_type == "photo" and size > HISTORIC_REGO_MAX_IMAGE_BYTES:
        raise ValueError(f"{filename} is larger than {HISTORIC_REGO_MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
    if file_type == "certificate" and size > HISTORIC_REGO_CERTIFICATE_MAX_BYTES:
        raise ValueError(f"{filename} is larger than {HISTORIC_REGO_CERTIFICATE_MAX_BYTES // (1024 * 1024)} MB.")
    file_id = str(ref.get("file_id") or "").strip() or historic_rego_file_id_for_key(key)
    return {
        "file_id": historic_rego_safe_segment(file_id, "file"),
        "source": "stored" if str(ref.get("source") or "").lower() == "stored" else "new",
        "file_type": file_type,
        "slot": slot,
        "label": HISTORIC_REGO_PHOTO_SLOT_LABELS.get(slot, slot.replace("_", " ").title()),
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size,
        "key": key,
        "uploaded_at": utc_now_precise(),
    }


def historic_rego_save_file_record(sub: str, record: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    existing = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=historic_rego_file_key(sub, record["file_id"]), ConsistentRead=True).get("Item")
    now = utc_now_precise()
    item = item_to_python(existing) if existing else {}
    item.update({
        "pk": member_pk(sub),
        "sk": f"HISTORIC_REGISTRATION_FILE#{record['file_id']}",
        "item_type": "historic_registration_file",
        "member_sub": sub,
        "file_id": record["file_id"],
        "file_type": record["file_type"],
        "slot": record["slot"],
        "label": record.get("label") or HISTORIC_REGO_PHOTO_SLOT_LABELS.get(record["slot"], record["slot"]),
        "filename": record["filename"],
        "content_type": record["content_type"],
        "size_bytes": int(record.get("size_bytes") or 0),
        "key": record["key"],
        "created_at": item.get("created_at") or now,
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or "member"),
    })
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return item


def historic_rego_presigned_download(file_record: Dict[str, Any], *, inline: bool = True) -> str:
    key = str(file_record.get("key") or "").strip()
    if not key.startswith(HISTORIC_REGO_STORAGE_PREFIX):
        return ""
    filename = historic_rego_filename(file_record.get("filename") or os.path.basename(key), "historic-registration-file")
    disposition = "inline" if inline else "attachment"
    try:
        return s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET, "Key": key, "ResponseContentDisposition": f'{disposition}; filename="{filename}"'},
            ExpiresIn=DOWNLOAD_EXPIRY,
            HttpMethod="GET",
        )
    except Exception:
        return ""


def historic_rego_file_summary(item: Dict[str, Any], *, include_url: bool = False) -> Dict[str, Any]:
    out = {
        "file_id": str(item.get("file_id") or ""),
        "file_type": str(item.get("file_type") or "photo"),
        "slot": str(item.get("slot") or "extra"),
        "label": str(item.get("label") or HISTORIC_REGO_PHOTO_SLOT_LABELS.get(str(item.get("slot") or "extra"), "Extra")),
        "filename": str(item.get("filename") or ""),
        "content_type": str(item.get("content_type") or ""),
        "size_bytes": int(item.get("size_bytes") or 0),
        "key": str(item.get("key") or ""),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "source": str(item.get("source") or "stored"),
    }
    if include_url:
        out["download_url"] = historic_rego_presigned_download(item, inline=True)
        if str(out["content_type"]).startswith("image/"):
            out["thumbnail_url"] = out["download_url"]
    return out


def historic_rego_list_member_files(sub: str, *, include_urls: bool = False) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": member_pk(sub)}, ":prefix": {"S": "HISTORIC_REGISTRATION_FILE#"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.query(**kwargs)
        items.extend(historic_rego_file_summary(item_to_python(item), include_url=include_urls) for item in resp.get("Items") or [])
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    items.sort(key=lambda x: (str(x.get("file_type") or ""), str(x.get("slot") or ""), str(x.get("updated_at") or "")), reverse=True)
    return items


def historic_rego_vehicle_is_eligible(vehicle: Dict[str, Any]) -> bool:
    try:
        year = int(str(vehicle.get("year") or "").strip()[:4])
    except Exception:
        return False
    return year > 1800 and year <= current_club_date().year - 30 and normalise_vehicle_status(vehicle.get("vehicle_status") or "active") != "disposed"


def historic_rego_vehicle_title(vehicle: Dict[str, Any]) -> str:
    return " ".join([str(vehicle.get("year") or "").strip(), str(vehicle.get("make") or "").strip(), str(vehicle.get("model") or "").strip(), str(vehicle.get("variant") or "").strip()]).strip() or "Vehicle not listed"


def historic_rego_summarise_request(item: Dict[str, Any], *, include_urls: bool = False) -> Dict[str, Any]:
    files = item.get("files") if isinstance(item.get("files"), list) else []
    out = {
        "request_id": str(item.get("request_id") or ""),
        "member_sub": str(item.get("member_sub") or ""),
        "member_name": str(item.get("member_name") or ""),
        "member_email": str(item.get("member_email") or ""),
        "member_number": str(item.get("member_number") or ""),
        "status": str(item.get("status") or "submitted"),
        "version": int(item.get("version") or 1),
        "subject_prefix": str(item.get("subject_prefix") or ""),
        "member_message": str(item.get("member_message") or ""),
        "vehicle_id": str(item.get("vehicle_id") or ""),
        "manual_vehicle": item.get("manual_vehicle") if isinstance(item.get("manual_vehicle"), dict) else {},
        "vehicle_snapshot": item.get("vehicle_snapshot") if isinstance(item.get("vehicle_snapshot"), dict) else {},
        "membership_status": str(item.get("membership_status") or ""),
        "financial_status": str(item.get("financial_status") or ""),
        "mailing_address": str(item.get("mailing_address") or ""),
        "mobile": str(item.get("mobile") or ""),
        "submitted_at": str(item.get("submitted_at") or item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "processed_at": str(item.get("processed_at") or ""),
        "processed_by": str(item.get("processed_by") or ""),
        "processed_note": str(item.get("processed_note") or ""),
        "files": [historic_rego_file_summary(f, include_url=include_urls) for f in files],
    }
    if include_urls and isinstance(out.get("vehicle_snapshot"), dict):
        vehicle = dict(out["vehicle_snapshot"])
        vehicle["classic_form_file"] = vehicle_record_file_summary(vehicle.get("classic_form_file"), include_url=True)
        vehicle["declaration_form_file"] = vehicle_record_file_summary(vehicle.get("declaration_form_file"), include_url=True)
        out["vehicle_snapshot"] = vehicle
    return out


def historic_rego_get_current_request(sub: str) -> Dict[str, Any] | None:
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=historic_rego_current_key(sub), ConsistentRead=True)
    return item_to_python(resp["Item"]) if resp.get("Item") else None


def historic_rego_member_position_ids(member: Dict[str, Any]) -> set[str]:
    ids = {normalise_position_id(member.get("committee_position_id") or member.get("official_position_id") or "")}
    for value in member.get("assigned_role_ids") or []:
        ids.add(normalise_position_id(value))
    for value in member.get("assigned_role_names") or []:
        ids.add(normalise_position_id(value))
    return {x for x in ids if x}


def historic_rego_claim_groups(claims: Dict[str, Any]) -> set[str]:
    raw = claims.get("cognito:groups") or claims.get("groups") or []
    if isinstance(raw, str):
        raw = re.split(r"[\s,]+", raw.strip("[] ")) if raw else []
    return {str(x or "").strip() for x in raw if str(x or "").strip()}


def historic_rego_is_officer(claims: Dict[str, Any], member: Dict[str, Any] | None = None) -> bool:
    groups = historic_rego_claim_groups(claims)
    if groups.intersection({"admins"}):
        return True
    sub = str(claims.get("sub") or "").strip()
    member = member or (get_member_metadata(sub) if sub else {})
    return bool(historic_rego_member_position_ids(member).intersection(HISTORIC_REGO_QUEUE_POSITION_IDS))


def require_historic_rego_officer(claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    member = get_member_metadata(sub) if sub else {}
    if not historic_rego_is_officer(claims, member):
        raise PermissionError("Historic Registration queue access is restricted to the Historic Registrar and authorised office bearers.")
    return member


def historic_rego_list_queue(*, include_urls: bool = False) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": "HISTORIC_REGISTRATION#QUEUE"}, ":prefix": {"S": "REQUEST#"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.query(**kwargs)
        for raw in resp.get("Items") or []:
            item = item_to_python(raw)
            if str(item.get("status") or "submitted") not in {"processed", "closed", "cancelled"}:
                items.append(historic_rego_summarise_request(item, include_urls=include_urls))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    items.sort(key=lambda x: str(x.get("updated_at") or x.get("submitted_at") or ""), reverse=True)
    return items


def historic_rego_resolve_recipients(member: Dict[str, Any]) -> Dict[str, Any]:
    position = resolve_historic_rego_position() or {}
    domain = club_email_domain()
    service_email = normalise_email_address(position.get("email_address") or f"rego@{domain}")
    if not valid_email_address(service_email):
        service_email = f"rego@{domain}"
    private_emails: List[str] = []
    last_key = None
    target_ids = set(HISTORIC_REGO_POSITION_IDS)
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "FilterExpression": "#sk = :profile",
            "ExpressionAttributeNames": {"#sk": "sk"},
            "ExpressionAttributeValues": {":profile": {"S": "PROFILE"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.scan(**kwargs)
        for raw in resp.get("Items") or []:
            meta = normalise_membership_metadata(item_to_python(raw))
            if str(meta.get("account_status") or "active") == "deleted":
                continue
            if historic_rego_member_position_ids(meta).intersection(target_ids):
                email = member_email_from_metadata(meta)
                if email and email not in private_emails and email != service_email:
                    private_emails.append(email)
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return {"position": position, "service_email": service_email, "private_emails": private_emails[:5], "position_name": str(position.get("position_name") or "Historic Registrar")}


def historic_rego_manual_vehicle_payload(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    payload = {
        "make": clean_vehicle_text(raw.get("make"), 64),
        "model": clean_vehicle_text(raw.get("model"), 64),
        "variant": clean_vehicle_text(raw.get("variant"), 64),
        "fuel_type": clean_vehicle_text(raw.get("fuel_type"), 64),
        "specific_build": clean_vehicle_text(raw.get("specific_build"), 160),
        "year": clean_vehicle_text(raw.get("year"), 16),
        "vin_serial_number": clean_vehicle_text(raw.get("vin_serial_number"), 80),
        "rego_number": "",
        "registration_expiry_date": "",
        "registration_type": normalise_vehicle_registration_type(raw.get("registration_type") or "historic"),
        "historic_classic": normalise_vehicle_registration_type(raw.get("registration_type") or "historic") in {"historic", "classic"},
    }
    if not payload["make"] or not payload["model"] or not payload["year"]:
        raise ValueError("For a vehicle not yet in your registry, make, model, and year are required.")
    if not re.match(r"^\d{4}$", payload["year"]):
        raise ValueError("Vehicle year must be a four digit year.")
    if int(payload["year"]) > current_club_date().year - 30:
        raise ValueError("Historic / Classic registration submissions require a vehicle that is at least 30 years old.")
    return payload


def historic_rego_validate_files(sub: str, raw_files: Any, claims: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(raw_files, list):
        raise ValueError("files must be a list.")
    if len(raw_files) > HISTORIC_REGO_MAX_IMAGES + 1:
        raise ValueError("Please attach the certificate, six required photos, and no more than five extra photos.")
    files: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for ref in raw_files:
        if not isinstance(ref, dict):
            raise ValueError("Each file must be an object.")
        rec = historic_rego_get_s3_file_record(sub, ref)
        if rec["key"] in seen_keys:
            continue
        seen_keys.add(rec["key"])
        saved = historic_rego_save_file_record(sub, rec, claims)
        saved["source"] = "stored" if str(ref.get("source") or "").lower() == "stored" else "new"
        files.append(saved)
    slots = {str(f.get("slot") or "") for f in files if str(f.get("file_type") or "") == "photo"}
    missing = [HISTORIC_REGO_PHOTO_SLOT_LABELS[s] for s in HISTORIC_REGO_PHOTO_SLOTS if s not in slots]
    if missing:
        raise ValueError("Missing required vehicle photos: " + ", ".join(missing) + ".")
    if not any(str(f.get("file_type") or "") == "certificate" or str(f.get("slot") or "") == "certificate" for f in files):
        raise ValueError("Vehicle inspection certificate is required.")
    return files


def historic_rego_request_vehicle(sub: str, body: Dict[str, Any], claims: Dict[str, Any]) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
    vehicle_id = clean_vehicle_id(body.get("vehicle_id") or "")
    manual = {}
    if vehicle_id:
        vehicle = get_member_vehicle(sub, vehicle_id)
        if not vehicle:
            raise ValueError("Selected vehicle was not found in your vehicle registry.")
        if not historic_rego_vehicle_is_eligible(vehicle):
            raise ValueError("Selected vehicle must be at least 30 years old and active in your vehicle registry.")
        return vehicle_id, vehicle, manual
    manual = historic_rego_manual_vehicle_payload(body.get("manual_vehicle") or {})
    saved = save_member_vehicle(sub, manual, claims)
    return str(saved.get("vehicle_id") or ""), saved, manual


def historic_rego_mail_rows(member: Dict[str, Any], vehicle: Dict[str, Any], financial_text: str) -> List[tuple[str, str]]:
    postal = address_block_from_metadata(member, "postal_")
    residential = address_block_from_metadata(member, "")
    return [
        ("Member name", member_display_name_from_metadata(member, {})),
        ("Member number", str(member.get("member_number") or member.get("site_member_id") or "").strip()),
        ("Financial status", financial_text),
        ("Contact email", member_email_from_metadata(member)),
        ("Mobile", str(member.get("mobile") or "").strip()),
        ("Phone", str(member.get("phone") or member.get("phone_number") or "").strip()),
        ("Current mailing address", postal["text"] or residential["text"] or "Not supplied"),
        ("Vehicle", historic_rego_vehicle_title(vehicle)),
        ("Make", str(vehicle.get("make") or "").strip()),
        ("Model", str(vehicle.get("model") or "").strip()),
        ("Variant", str(vehicle.get("variant") or "").strip()),
        ("Specific build", str(vehicle.get("specific_build") or "").strip()),
        ("Year", str(vehicle.get("year") or "").strip()),
        ("Registration number", str(vehicle.get("rego_number") or "").strip()),
        ("Registration expiry", str(vehicle.get("registration_expiry_date") or "").strip()),
        ("VIN / chassis", str(vehicle.get("vin_serial_number") or "").strip()),
        ("Registration type", normalise_vehicle_registration_type(vehicle.get("registration_type"), historic_classic=vehicle.get("historic_classic")).title()),
        ("Classic body", normalise_classic_scheme_body(vehicle.get("classic_scheme_body")) or "Not applicable"),
        ("Historic / Classic on file", "Yes" if vehicle.get("historic_classic") else "No"),
    ]


def build_historic_registration_request_email(request: Dict[str, Any], recipients: Dict[str, Any]) -> Dict[str, Any]:
    member = request.get("member_snapshot") if isinstance(request.get("member_snapshot"), dict) else {}
    vehicle = request.get("vehicle_snapshot") if isinstance(request.get("vehicle_snapshot"), dict) else {}
    files = request.get("files") if isinstance(request.get("files"), list) else []
    message = str(request.get("member_message") or "").strip() or "No additional message supplied."
    updated = int(request.get("version") or 1) > 1
    subject_prefix = "UPDATED Historic / Classic Registration Request" if updated else "Historic / Classic Registration Request"
    member_name = str(request.get("member_name") or member_display_name_from_metadata(member, {}))
    member_number = str(request.get("member_number") or member.get("site_member_id") or "").strip()
    vehicle_title = historic_rego_vehicle_title(vehicle)
    subject_bits = [subject_prefix, member_name]
    if member_number:
        subject_bits.append(f"Member {member_number}")
    subject_bits.append(vehicle_title)
    subject = " - ".join([x for x in subject_bits if x])[:240]
    financial_text = str(request.get("financial_status") or "Unknown")
    rows = historic_rego_mail_rows(member, vehicle, financial_text)
    text_rows = "\n".join(f"{k}: {v or 'Not supplied'}" for k, v in rows)
    file_rows = "\n".join(f"- {HISTORIC_REGO_PHOTO_SLOT_LABELS.get(str(f.get('slot') or ''), str(f.get('label') or 'File'))}: {f.get('filename')} ({int(f.get('size_bytes') or 0)} bytes)" for f in files)
    text = (
        "Land Rover Owners Club of Australia Inc\n"
        f"{subject_prefix}\n\n"
        f"Submitted at: {request.get('updated_at') or request.get('submitted_at')}\n"
        f"Request ID: {request.get('request_id')}\n\n"
        "Member message\n--------------\n"
        f"{message}\n\n"
        "Member, mailing and vehicle details\n-----------------------------------\n"
        f"{text_rows}\n\n"
        "Attached files\n--------------\n"
        f"{file_rows or 'No files attached.'}\n"
    )
    logo = WEBMAIL_CLUB_LOGO_URL or (public_url("assets/lroc-logo.png") if SITE_BASE_URL else "")
    html_rows = "".join(f"<tr><th style='text-align:left;vertical-align:top;padding:7px 10px;border-bottom:1px solid #e5e7eb;width:220px'>{html.escape(k)}</th><td style='padding:7px 10px;border-bottom:1px solid #e5e7eb;white-space:pre-wrap'>{html.escape(v or 'Not supplied')}</td></tr>" for k, v in rows)
    html_files = "".join(f"<li><strong>{html.escape(HISTORIC_REGO_PHOTO_SLOT_LABELS.get(str(f.get('slot') or ''), str(f.get('label') or 'File')))}</strong>: {html.escape(str(f.get('filename') or 'file'))} ({int(f.get('size_bytes') or 0)} bytes)</li>" for f in files)
    html_body = (
        "<div style='font-family:Arial,sans-serif;line-height:1.55;color:#111827'>"
        "<div style='border-bottom:4px solid #143b2d;padding-bottom:12px;margin-bottom:18px;display:flex;gap:14px;align-items:center'>"
        + (f"<img src='{html.escape(logo)}' alt='LROC' style='height:54px;width:auto'>" if logo else "")
        + f"<div><strong style='font-size:19px;color:#143b2d'>LROC</strong><br><span>{html.escape(subject_prefix)}</span></div></div>"
        + ("<p style='padding:10px 12px;border-radius:10px;background:#fff7ed;border:1px solid #fed7aa'><strong>Updated submission:</strong> this replaces the previous open request from this member.</p>" if updated else "")
        + f"<p><strong>Submitted at:</strong> {html.escape(str(request.get('updated_at') or request.get('submitted_at') or ''))}<br><strong>Request ID:</strong> {html.escape(str(request.get('request_id') or ''))}</p>"
        + "<h3 style='color:#143b2d;margin:20px 0 8px'>Member message</h3>"
        + f"<p style='white-space:pre-wrap'>{html.escape(message)}</p>"
        + "<h3 style='color:#143b2d;margin:20px 0 8px'>Member, mailing and vehicle details</h3>"
        + f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{html_rows}</table>"
        + "<h3 style='color:#143b2d;margin:20px 0 8px'>Attached files</h3>"
        + f"<ul>{html_files or '<li>No files attached.</li>'}</ul>"
        + "</div>"
    )
    return {"subject": subject, "text": text, "html": html_body}


def send_historic_registration_raw_email(to_email: str, cc_emails: List[str], subject: str, text_body: str, html_body: str, files: List[Dict[str, Any]], reply_to: str = "") -> Dict[str, Any]:
    from_addr = lroc_from_header(SES_FROM_EMAIL)
    to_clean = normalise_email_address(to_email)
    cc_clean = []
    for email in cc_emails or []:
        clean = normalise_email_address(email)
        if valid_email_address(clean) and clean != to_clean and clean not in cc_clean:
            cc_clean.append(clean)
    root = MIMEMultipart("mixed")
    root["Subject"] = clean_header_address(subject)
    root["From"] = from_addr
    root["To"] = to_clean
    if cc_clean:
        root["Cc"] = ", ".join(cc_clean)
    reply = clean_header_address(reply_to or SES_REPLY_TO_EMAIL or SES_FROM_EMAIL)
    if reply:
        root["Reply-To"] = reply
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    root.attach(alt)
    total_bytes = 0
    attached = 0
    for f in files:
        key = str(f.get("key") or "").strip()
        if not key.startswith(HISTORIC_REGO_STORAGE_PREFIX):
            continue
        size = int(f.get("size_bytes") or 0)
        if total_bytes + size > HISTORIC_REGO_EMAIL_ATTACHMENT_MAX_BYTES:
            continue
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        blob = obj["Body"].read()
        total_bytes += len(blob)
        maintype, subtype = (str(f.get("content_type") or "application/octet-stream").split("/", 1) + ["octet-stream"])[:2]
        part = MIMEBase(maintype or "application", subtype or "octet-stream")
        part.set_payload(blob)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=historic_rego_filename(f.get("filename"), "historic-registration-file"))
        root.attach(part)
        attached += 1
    all_dest = [to_clean] + cc_clean
    result = send_raw_email_via_ses(all_dest, root.as_bytes(), from_email=SES_FROM_EMAIL, reply_to=reply)
    result["attached_count"] = attached
    result["attached_bytes"] = total_bytes
    return result


def save_historic_registration_request_item(request: Dict[str, Any]) -> None:
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**request, "pk": member_pk(request["member_sub"]), "sk": "HISTORIC_REGISTRATION#ACTIVE"}))
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**request, "pk": "HISTORIC_REGISTRATION#QUEUE", "sk": f"REQUEST#{request['request_id']}"}))


def historic_registration_submit_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    if not ses_email_available():
        raise ValueError("Historic Registration email sending is not configured yet. Please contact the club.")
    body = parse_body(event)
    member = get_member_metadata(sub)
    vehicle_id, vehicle, manual = historic_rego_request_vehicle(sub, body, claims)
    requested_registration_type = normalise_vehicle_registration_type(body.get("registration_type"), historic_classic=vehicle.get("historic_classic"))
    if vehicle_id:
        vehicle_item = get_member_vehicle_item(sub, vehicle_id) or {}
        if vehicle_item:
            vehicle_item["registration_type"] = requested_registration_type
            vehicle_item["historic_classic"] = requested_registration_type in {"historic", "classic"}
            vehicle_item["updated_at"] = utc_now()
            vehicle_item["updated_by"] = str(claims.get("email") or claims.get("sub") or "member")
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(vehicle_item))
            vehicle = vehicle_summary(vehicle_item)
            if manual:
                manual["registration_type"] = requested_registration_type
                manual["historic_classic"] = requested_registration_type in {"historic", "classic"}
    files = historic_rego_validate_files(sub, body.get("files") or [], claims)
    current = historic_rego_get_current_request(sub) or {}
    is_update = bool(current and str(current.get("status") or "submitted") not in {"processed", "closed", "cancelled"})
    request_id = str(current.get("request_id") or f"hreg_{secrets.token_hex(10)}") if is_update else f"hreg_{secrets.token_hex(10)}"
    version = int(current.get("version") or 0) + 1 if is_update else 1
    now = utc_now_precise()
    financial = member_is_financial_for_historic_registration(member, current_club_date())
    financial_text = "Financial" if financial is True else ("Not financial" if financial is False else "Unknown")
    postal = address_block_from_metadata(member, "postal_")
    residential = address_block_from_metadata(member, "")
    member_email = member_email_from_metadata(member, claims)
    request = {
        "item_type": "historic_registration_request",
        "request_id": request_id,
        "member_sub": sub,
        "member_name": member_display_name_from_metadata(member, claims),
        "member_email": member_email,
        "member_number": str(member.get("member_number") or member.get("site_member_id") or "").strip(),
        "membership_status": str(member.get("membership_status") or "").strip(),
        "financial_status": financial_text,
        "mailing_address": postal["text"] or residential["text"],
        "mobile": str(member.get("mobile") or "").strip(),
        "vehicle_id": vehicle_id,
        "manual_vehicle": manual,
        "vehicle_snapshot": vehicle,
        "member_snapshot": member,
        "member_message": clean_historic_rego_notes(body.get("message") or body.get("notes") or ""),
        "files": [historic_rego_file_summary(f, include_url=False) for f in files],
        "status": "submitted",
        "version": version,
        "subject_prefix": "UPDATED" if is_update else "NEW",
        "created_at": current.get("created_at") or now,
        "submitted_at": current.get("submitted_at") or now,
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or "member"),
        "processed_at": "",
        "processed_by": "",
        "processed_note": "",
    }
    recipients = historic_rego_resolve_recipients(member)
    if not valid_email_address(recipients["service_email"]):
        raise ValueError("rego@ address could not be determined. Please contact the club.")
    mail = build_historic_registration_request_email(request, recipients)
    cc_emails = list(recipients.get("private_emails") or [])
    if member_email:
        cc_emails.append(member_email)
    send_result = send_historic_registration_raw_email(recipients["service_email"], cc_emails, mail["subject"], mail["text"], mail["html"], files, reply_to=member_email or SES_REPLY_TO_EMAIL)
    request["rego_email"] = recipients["service_email"]
    request["rego_private_emails"] = recipients.get("private_emails") or []
    request["member_cc_email"] = member_email
    request["message_id"] = str(send_result.get("MessageId") or "")
    request["attached_count"] = int(send_result.get("attached_count") or 0)
    request["attached_bytes"] = int(send_result.get("attached_bytes") or 0)
    save_historic_registration_request_item(request)
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**request, "pk": member_pk(sub), "sk": historic_rego_audit_sk(now, request_id, version), "item_type": "historic_registration_audit", "audit_action": "resubmitted" if is_update else "submitted"}))
    return response(200, {"message": "Historic / Classic Registration request submitted." if not is_update else "Historic / Classic Registration request updated and re-sent.", "request": historic_rego_summarise_request(request, include_urls=True), "updated_existing_request": is_update})


def historic_registration_state_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    member = get_member_metadata(sub)
    vehicles = [v for v in list_member_vehicles(sub) if historic_rego_vehicle_is_eligible(v)]
    current = historic_rego_get_current_request(sub)
    officer = historic_rego_is_officer(claims, member)
    out = {
        "vehicles": vehicles,
        "stored_files": historic_rego_list_member_files(sub, include_urls=True),
        "active_request": historic_rego_summarise_request(current, include_urls=True) if current and str(current.get("status") or "submitted") not in {"processed", "closed", "cancelled"} else None,
        "is_officer": officer,
        "photo_slots": [{"slot": slot, "label": HISTORIC_REGO_PHOTO_SLOT_LABELS[slot]} for slot in HISTORIC_REGO_PHOTO_SLOTS],
        "max_photo_bytes": HISTORIC_REGO_MAX_IMAGE_BYTES,
        "max_certificate_bytes": HISTORIC_REGO_CERTIFICATE_MAX_BYTES,
    }
    if officer:
        out["queue"] = historic_rego_list_queue(include_urls=True)
    return response(200, out)



def historic_registration_vehicle_form_upload_url_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_historic_rego_officer(claims)
    body = parse_body(event)
    request_id = historic_rego_safe_segment(body.get("request_id"), "")
    if not request_id:
        raise ValueError("request_id is required.")
    request = item_to_python(ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=historic_rego_queue_key(request_id), ConsistentRead=True).get("Item") or {})
    if not request:
        raise ValueError("Registration request was not found.")
    form_type = clean_vehicle_text(body.get("form_type"), 32).lower()
    if form_type not in {"classic_form", "declaration_form"}:
        raise ValueError("form_type must be classic_form or declaration_form.")
    filename = historic_rego_filename(body.get("filename") or "vehicle-form.pdf", "vehicle-form.pdf")
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    content_type = historic_rego_content_type(filename, body.get("content_type") or "application/pdf")
    if content_type != "application/pdf":
        raise ValueError("Vehicle record forms must be PDF files.")
    size = int(body.get("size") or 0)
    if size and size > HISTORIC_REGO_CERTIFICATE_MAX_BYTES:
        raise ValueError(f"Vehicle record forms must be no larger than {HISTORIC_REGO_CERTIFICATE_MAX_BYTES // (1024 * 1024)} MB.")
    member_sub = str(request.get("member_sub") or "").strip()
    file_id = secrets.token_urlsafe(12)
    key = historic_rego_make_upload_key(member_sub, file_id, filename)
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type, "ServerSideEncryption": "AES256"},
        ExpiresIn=UPLOAD_EXPIRY,
        HttpMethod="PUT",
    )
    return response(200, {"upload_url": url, "key": key, "file_id": file_id, "filename": filename, "content_type": content_type, "form_type": form_type})


def historic_rego_validate_vehicle_form_file(member_sub: str, ref: Any, form_type: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(ref, dict) or not ref.get("key"):
        return {}
    key = str(ref.get("key") or "").strip()
    if not key.startswith(f"{HISTORIC_REGO_STORAGE_PREFIX}{historic_rego_safe_segment(member_sub, 'member')}/"):
        raise ValueError("Invalid vehicle form file reference.")
    filename = historic_rego_filename(ref.get("filename") or os.path.basename(key), "vehicle-form.pdf")
    content_type = historic_rego_content_type(filename, ref.get("content_type") or "application/pdf")
    if content_type != "application/pdf":
        raise ValueError("Vehicle record forms must be PDF files.")
    try:
        head = s3.head_object(Bucket=BUCKET, Key=key)
    except ClientError as exc:
        raise ValueError(f"Uploaded form was not found: {filename}") from exc
    size = int(head.get("ContentLength") or 0)
    if size <= 0:
        raise ValueError(f"Uploaded form is empty: {filename}")
    if size > HISTORIC_REGO_CERTIFICATE_MAX_BYTES:
        raise ValueError(f"{filename} is larger than {HISTORIC_REGO_CERTIFICATE_MAX_BYTES // (1024 * 1024)} MB.")
    return {
        "file_id": historic_rego_safe_segment(ref.get("file_id") or historic_rego_file_id_for_key(key), "file"),
        "form_type": form_type,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size,
        "key": key,
        "uploaded_at": utc_now_precise(),
        "uploaded_by": str(claims.get("email") or claims.get("sub") or "officer"),
    }


def historic_registration_vehicle_record_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_historic_rego_officer(claims)
    body = parse_body(event)
    request_id = historic_rego_safe_segment(body.get("request_id"), "")
    if not request_id:
        raise ValueError("request_id is required.")
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=historic_rego_queue_key(request_id), ConsistentRead=True)
    if not resp.get("Item"):
        raise ValueError("Registration request was not found.")
    request = item_to_python(resp["Item"])
    member_sub = str(request.get("member_sub") or "").strip()
    vehicle_id = clean_vehicle_id(request.get("vehicle_id") or "")
    if not member_sub or not vehicle_id:
        raise ValueError("This request is not linked to a saved member vehicle record.")
    item = get_member_vehicle_item(member_sub, vehicle_id) or {}
    if not item:
        raise ValueError("Vehicle record was not found.")
    reg_type = normalise_vehicle_registration_type(body.get("registration_type"), historic_classic=item.get("historic_classic"))
    item["registration_type"] = reg_type
    item["historic_classic"] = reg_type in {"historic", "classic"}
    item["classic_scheme_body"] = normalise_classic_scheme_body(body.get("classic_scheme_body")) if reg_type == "classic" else ""
    classic_form = historic_rego_validate_vehicle_form_file(member_sub, body.get("classic_form_file"), "classic_form", claims)
    declaration_form = historic_rego_validate_vehicle_form_file(member_sub, body.get("declaration_form_file"), "declaration_form", claims)
    if classic_form:
        item["classic_form_file"] = classic_form
    if declaration_form:
        item["declaration_form_file"] = declaration_form
    item["updated_at"] = utc_now()
    item["updated_by"] = str(claims.get("email") or claims.get("sub") or "officer")
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    vehicle = vehicle_summary(item)
    request["vehicle_snapshot"] = vehicle
    request["updated_at"] = utc_now_precise()
    save_historic_registration_request_item(request)
    vehicle_urls = dict(vehicle)
    vehicle_urls["classic_form_file"] = vehicle_record_file_summary(item.get("classic_form_file"), include_url=True)
    vehicle_urls["declaration_form_file"] = vehicle_record_file_summary(item.get("declaration_form_file"), include_url=True)
    return response(200, {"message": "Vehicle registration record updated.", "vehicle": vehicle_urls})


def build_historic_registration_processed_email(request: Dict[str, Any], note: str, officer: Dict[str, Any]) -> Dict[str, str]:
    vehicle = request.get("vehicle_snapshot") if isinstance(request.get("vehicle_snapshot"), dict) else {}
    title = historic_rego_vehicle_title(vehicle)
    address = str(request.get("mailing_address") or "your current mailing address").strip()
    subject = f"Historic / Classic Registration processed - {title}"
    paragraphs = [
        f"Your Historic / Classic registration documents for {title} have been processed by the club.",
        f"The documents will be mailed to: {address}",
    ]
    if note:
        paragraphs.append(f"Registrar note: {note}")
    rows = [
        ("Request ID", str(request.get("request_id") or "")),
        ("Vehicle", title),
        ("Mailing address", address),
        ("Processed by", member_display_name_from_metadata(officer, {})),
        ("Processed at", utc_now_precise()),
    ]
    text = "Land Rover Owners Club of Australia Inc\n\n" + "\n\n".join(paragraphs) + "\n\n" + "\n".join(f"{k}: {v}" for k, v in rows)
    return {"subject": subject, "text": text, "html": simple_html_email(subject, paragraphs, rows)}


def historic_registration_process_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    officer = require_historic_rego_officer(claims)
    body = parse_body(event)
    request_id = historic_rego_safe_segment(body.get("request_id"), "")
    if not request_id:
        raise ValueError("request_id is required.")
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=historic_rego_queue_key(request_id), ConsistentRead=True)
    if not resp.get("Item"):
        raise ValueError("Registration request was not found.")
    request = item_to_python(resp["Item"])
    now = utc_now_precise()
    note = clean_multiline_field(body.get("note") or "", 1000)
    request["status"] = "processed"
    request["processed_at"] = now
    request["processed_by"] = str(claims.get("email") or claims.get("sub") or "officer")
    request["processed_note"] = note
    request["updated_at"] = now
    save_historic_registration_request_item(request)
    member_email = normalise_email_address(request.get("member_email") or "")
    email_sent = False
    if valid_email_address(member_email) and ses_email_available():
        mail = build_historic_registration_processed_email(request, note, officer)
        sent = safe_send_email_via_ses([member_email], mail["subject"], mail["text"], mail["html"])
        email_sent = bool(sent.get("sent"))
        request["processed_member_message_id"] = str(sent.get("message_id") or "")
        save_historic_registration_request_item(request)
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**request, "pk": member_pk(str(request.get("member_sub") or "")), "sk": historic_rego_audit_sk(now, request_id, int(request.get("version") or 1)), "item_type": "historic_registration_audit", "audit_action": "processed"}))
    return response(200, {"message": "Registration request marked as processed." + (" Member email sent." if email_sent else " Member email was not sent automatically."), "request": historic_rego_summarise_request(request, include_urls=True), "email_sent": email_sent})

def import_vehicle_key_text(vehicle: Dict[str, Any]) -> str:
    parts = [
        str(vehicle.get("vin_serial_number") or "").strip().upper(),
        str(vehicle.get("rego_number") or "").strip().upper(),
        str(vehicle.get("make") or "").strip().casefold(),
        str(vehicle.get("model") or "").strip().casefold(),
        str(vehicle.get("year") or "").strip(),
    ]
    return "|".join(parts)


def deterministic_import_vehicle_id(member_number: str, vehicle: Dict[str, Any]) -> str:
    strong = str(vehicle.get("vin_serial_number") or vehicle.get("rego_number") or import_vehicle_key_text(vehicle)).strip().upper()
    digest = hashlib.sha1(f"{member_number}|{strong}".encode("utf-8")).hexdigest()[:16]
    return f"import_car1_{digest}"


def find_matching_member_vehicle_id(sub: str, vehicle: Dict[str, Any]) -> str:
    vin = str(vehicle.get("vin_serial_number") or "").strip().upper()
    rego = str(vehicle.get("rego_number") or "").strip().upper()
    fallback_key = import_vehicle_key_text(vehicle)
    for existing in list_member_vehicles(sub):
        existing_id = str(existing.get("vehicle_id") or "").strip()
        if not existing_id:
            continue
        if vin and str(existing.get("vin_serial_number") or "").strip().upper() == vin:
            return existing_id
        if rego and str(existing.get("rego_number") or "").strip().upper() == rego:
            return existing_id
        if not vin and not rego and import_vehicle_key_text(existing) == fallback_key:
            return existing_id
    return ""


def save_imported_member_vehicle(sub: str, member_number: str, vehicle: Dict[str, Any], claims: Dict[str, Any], batch_id: str) -> Dict[str, Any]:
    require_metadata_table()
    if not vehicle:
        return {"saved": False}
    vehicle_id = find_matching_member_vehicle_id(sub, vehicle) or deterministic_import_vehicle_id(member_number, vehicle)
    existing = get_member_vehicle(sub, vehicle_id)
    now = utc_now()
    item = {
        "pk": member_pk(sub),
        "sk": f"VEHICLE#{vehicle_id}",
        "item_type": "vehicle",
        "member_sub": sub,
        "member_number": str(member_number or ""),
        "vehicle_id": vehicle_id,
        "make": clean_vehicle_text(vehicle.get("make"), 64),
        "model": clean_vehicle_text(vehicle.get("model"), 64),
        "variant": clean_vehicle_text(vehicle.get("variant"), 64),
        "fuel_type": clean_vehicle_text(vehicle.get("fuel_type"), 64),
        "specific_build": clean_vehicle_text(vehicle.get("specific_build"), 160),
        "year": clean_vehicle_text(vehicle.get("year"), 16),
        "rego_number": clean_vehicle_text(vehicle.get("rego_number"), 32),
        "historic_classic": bool(vehicle.get("historic_classic")),
        "vin_serial_number": clean_vehicle_text(vehicle.get("vin_serial_number"), 80),
        "source": "member-form-data-import",
        "source_import_batch_id": batch_id,
        "source_vehicle_slot": str(vehicle.get("source_vehicle_slot") or "car #1"),
        "source_created_date": clean_text_field(vehicle.get("source_created_date"), 32),
        "source_last_modified_date": clean_text_field(vehicle.get("source_last_modified_date"), 32),
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or "member-import"),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return {"saved": True, "vehicle_id": vehicle_id, "updated": bool(existing), "summary": vehicle_summary(item)}


def member_vehicle_options_route(_event: Dict[str, Any], _claims: Dict[str, Any]) -> Dict[str, Any]:
    return response(200, load_vehicle_data())


def admin_vehicle_options_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    return response(200, load_vehicle_data())


def save_admin_vehicle_options_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    data = save_vehicle_data(body.get("vehicle_data") if isinstance(body.get("vehicle_data"), dict) else body, claims)
    return response(200, {"message": "Vehicle data saved.", "vehicle_data": data})


def list_member_vehicles_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    return response(200, {"items": list_member_vehicles(sub)})


def save_member_vehicle_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    item = save_member_vehicle(sub, parse_body(event), claims)
    return response(200, {"message": "Vehicle saved.", "item": item})


def delete_member_vehicle_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    body = parse_body(event)
    item = delete_member_vehicle(sub, str(body.get("vehicle_id") or ""))
    return response(200, {"message": "Vehicle deleted.", "item": item})


def member_vehicle_registration_response_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    body = parse_body(event)
    result = update_member_vehicle_registration_response(
        sub,
        str(body.get("vehicle_id") or ""),
        str(body.get("action") or ""),
        claims,
    )
    return response(200, result)



def clean_part_number(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())[:80]


def normalise_part_alias(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())[:80]


def split_part_values(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[\n,;]+", str(value or ""))
    out: List[str] = []
    seen: set[str] = set()
    for item in raw:
        part = clean_part_number(item)
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return out[:30]


def clean_part_reference(value: Any) -> str:
    # Cross-reference entries often contain a brand plus a part number, e.g.
    # "TIMKEN NP449291/NP420308". Preserve meaningful internal spacing instead
    # of treating every reference as a compact OE-style part number. Also repair
    # older saved values where an earlier normaliser mashed common brand prefixes
    # into the part number, e.g. "TIMKENNP449291" -> "TIMKEN NP449291".
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(
        r"\b(TIMKEN|SKF|NSK|NTN|KOYO|GKN|INA|FAG|BEARMACH|BRITPART|ALLMAKES)(?=[A-Z0-9])",
        r"\1 ",
        text,
        flags=re.IGNORECASE,
    )
    return text[:160]


def split_part_reference_values(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = value
    else:
        # Cross-reference text often legitimately contains commas inside one
        # reference line, for example:
        # "TIMKEN NP449291/NP420308, LM603049(CONE)/LM603011(CUP)".
        # Split only on new lines / semicolons / pipes so spaces and commas survive
        # the admin editor -> DynamoDB -> editor round trip.
        raw = re.split(r"[\n;|]+", str(value or ""))
    out: List[str] = []
    seen: set[str] = set()
    for item in raw:
        ref = clean_part_reference(item)
        key = normalise_part_alias(ref)
        if ref and key and key not in seen:
            seen.add(key)
            out.append(ref)
    return out[:40]



def clean_vin_family_key(value: Any) -> str:
    # For 17-character Land Rover VINs, the first 7 characters identify a useful
    # vehicle family/build key for parts applicability, e.g. SALLDHM.
    text = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if len(text) >= 17 and text.startswith("SAL"):
        text = text[:7]
    return text[:7] if len(text) >= 7 else text


def split_vin_family_values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\s,;|]+", str(value or ""))
    seen = set()
    out: List[str] = []
    for item in raw_items:
        key = clean_vin_family_key(item)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out[:40]


def clean_part_text(value: Any, max_len: int = 1200) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text[:max_len]


def part_record_key(part_number: str) -> Dict[str, Dict[str, str]]:
    part = clean_part_number(part_number)
    return {"pk": {"S": LANDROVER_PARTS_PK}, "sk": {"S": f"PART#{normalise_part_alias(part)}"}}


def normalise_landrover_part_record(data: Dict[str, Any], claims: Dict[str, Any] | None = None) -> Dict[str, Any]:
    part_number = clean_part_number(data.get("part_number"))
    if not part_number:
        raise ValueError("Part number is required.")
    record = {
        "pk": LANDROVER_PARTS_PK,
        "sk": f"PART#{normalise_part_alias(part_number)}",
        "record_type": "landrover_part",
        "part_number": part_number,
        "canonical_part_number": clean_part_number(data.get("canonical_part_number") or part_number),
        "description": clean_part_text(data.get("description"), 240),
        "component": clean_part_text(data.get("component"), 160),
        "model_family": clean_part_text(data.get("model_family"), 160),
        "year_range": clean_part_text(data.get("year_range"), 80),
        "applicability": clean_part_text(data.get("applicability"), 700),
        "position": clean_part_text(data.get("position"), 120),
        "vin_family_keys": split_vin_family_values(data.get("vin_family_keys")),
        "verified_response": clean_part_text(data.get("verified_response"), 1400),
        "notes": clean_part_text(data.get("notes"), 1200),
        "source_url": str(data.get("source_url") or "").strip()[:700],
        "supersedes": split_part_values(data.get("supersedes")),
        "superseded_by": split_part_values(data.get("superseded_by")),
        "equivalent_numbers": split_part_reference_values(data.get("equivalent_numbers")),
        "keywords": [x.lower() for x in re.split(r"[\n,;]+", str(data.get("keywords") or "")) if x.strip()][:40],
        "published": bool(data.get("published", True)),
        "last_verified": clean_part_text(data.get("last_verified"), 40) or utc_now()[:10],
    }
    if claims:
        record["updated_by"] = str(claims.get("email") or claims.get("sub") or "admin")
        record["updated_at"] = utc_now()
    return record


def landrover_part_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    summary = {k: item.get(k) for k in [
        "part_number", "canonical_part_number", "description", "component", "model_family", "year_range",
        "applicability", "position", "vin_family_keys", "verified_response", "notes", "source_url", "supersedes",
        "superseded_by", "equivalent_numbers", "keywords", "published", "last_verified", "updated_at", "updated_by"
    ] if k in item}
    if "equivalent_numbers" in summary:
        summary["equivalent_numbers"] = split_part_reference_values(summary.get("equivalent_numbers"))
    return summary


def list_landrover_parts(include_unpublished: bool = False) -> List[Dict[str, Any]]:
    require_metadata_table()
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": LANDROVER_PARTS_PK}},
    )
    items = [item_to_python(item) for item in resp.get("Items", [])]
    while resp.get("LastEvaluatedKey"):
        resp = ddb.query(
            TableName=MEMBER_METADATA_TABLE,
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": {"S": LANDROVER_PARTS_PK}},
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(item_to_python(item) for item in resp.get("Items", []))
    summaries = [landrover_part_summary(item) for item in items if include_unpublished or bool(item.get("published", True))]
    return sorted(summaries, key=lambda x: (str(x.get("model_family") or ""), str(x.get("component") or ""), str(x.get("part_number") or "")))


def part_alias_set(part: Dict[str, Any]) -> set[str]:
    values = [part.get("part_number"), part.get("canonical_part_number")]
    values += part.get("supersedes") or []
    values += part.get("superseded_by") or []
    values += part.get("equivalent_numbers") or []
    return {normalise_part_alias(v) for v in values if normalise_part_alias(v)}


def vehicle_search_text(vehicle: Dict[str, Any] | None) -> str:
    if not vehicle:
        return ""
    return " ".join(str(vehicle.get(k) or "") for k in ["year", "make", "model", "variant", "specific_build", "fuel_type", "vin_serial_number"]).lower()


def part_lookup_terms(text: Any) -> set[str]:
    words = [w.lower() for w in re.findall(r"[a-z0-9]+", str(text or "").lower())]
    terms: set[str] = set()
    for word in words:
        if not word:
            continue
        terms.add(word)
        if len(word) > 4 and word.endswith("s"):
            terms.add(word[:-1])
        if len(word) > 5 and word.endswith("ies"):
            terms.add(word[:-3] + "y")
    for idx in range(len(words) - 1):
        pair = f"{words[idx]} {words[idx + 1]}"
        terms.add(pair)
        if pair.endswith("s") and len(pair) > 6:
            terms.add(pair[:-1])
    for idx in range(len(words) - 2):
        tri = f"{words[idx]} {words[idx + 1]} {words[idx + 2]}"
        terms.add(tri)
        if tri.endswith("s") and len(tri) > 8:
            terms.add(tri[:-1])
    return {term for term in terms if len(term) >= 3}


def meaningful_part_terms(terms: set[str]) -> set[str]:
    generic = {
        "part", "parts", "number", "numbers", "part number", "parts number", "part no", "number for",
        "what", "which", "need", "want", "find", "please", "vehicle", "car", "land", "rover",
        "my", "the", "for", "and", "with", "all", "front", "rear", "left", "right", "near", "side",
        "driver", "passenger", "assembly", "kit", "oe", "oem", "sku", "superseded", "supersession",
        "bearing", "bearings", "seal", "seals", "pump", "pumps"
    }
    return {term for term in (terms or set()) if term not in generic and len(term) >= 3}


def specific_component_terms(terms: set[str]) -> set[str]:
    meaningful = meaningful_part_terms(terms)
    # Keep multi-word component phrases first. Single words are useful only when
    # they are not generic component nouns. This stops "swivel pin bearing" from
    # matching a "wheel bearing" record merely through the word "bearing".
    specific = {term for term in meaningful if " " in term}
    specific.update(term for term in meaningful if term not in {"bearing", "bearings", "seal", "seals", "pump", "pumps"})
    return specific


def has_part_intent_match(issue_terms: set[str], keyword_terms: set[str], component_terms: set[str], description_terms: set[str]) -> bool:
    # A verified parts record must match the requested component/intent, not merely the selected vehicle.
    issue_specific = specific_component_terms(issue_terms)
    record_specific = specific_component_terms(keyword_terms | component_terms | description_terms)
    if not issue_specific or not record_specific:
        return False
    if issue_specific & record_specific:
        return True
    synonyms = {
        "coolant pump": {"water pump"},
        "water pump": {"coolant pump"},
        "wheel bearing": {"hub bearing"},
        "hub bearing": {"wheel bearing"},
        "swivel pin bearing": {"swivel bearing", "swivel pin"},
        "swivel bearing": {"swivel pin bearing", "swivel pin"},
    }
    for term in issue_specific:
        related = synonyms.get(term, set())
        if related & record_specific:
            return True
    for term in record_specific:
        related = synonyms.get(term, set())
        if related & issue_specific:
            return True
    return False


def vehicle_vin_family_key(vehicle: Dict[str, Any] | None) -> str:
    if not vehicle:
        return ""
    return clean_vin_family_key(vehicle.get("vin_serial_number") or vehicle.get("vin") or vehicle.get("chassis") or "")


def vehicle_year_matches_part(vehicle: Dict[str, Any] | None, part: Dict[str, Any]) -> bool:
    try:
        vehicle_year = int(str((vehicle or {}).get("year") or "").strip()[:4])
        year_range = str(part.get("year_range") or "")
        nums = [int(x) for x in re.findall(r"(?:19|20)\d{2}", year_range)]
        if len(nums) >= 2:
            return min(nums) <= vehicle_year <= max(nums)
        if nums:
            return vehicle_year in nums
    except Exception:
        pass
    return False


def part_vehicle_applicability_match(part: Dict[str, Any], vehicle: Dict[str, Any] | None) -> bool:
    # Prefer VIN family keys when admins have supplied them, but do not hide
    # otherwise-valid club verified part records just because a member selected a
    # vehicle with a VIN. Many useful LROC records are model/year/applicability
    # scoped rather than VIN-family scoped.
    vin_key = vehicle_vin_family_key(vehicle)
    record_keys = set(split_vin_family_values(part.get("vin_family_keys")))
    app_text = " ".join(str(part.get(k) or "") for k in ["model_family", "applicability", "position", "year_range"]).strip()
    app_blob = re.sub(r"[^A-Z0-9]", "", app_text.upper())
    if vin_key:
        if record_keys:
            return vin_key in record_keys
        if vin_key in app_blob:
            return True
    if not app_text:
        return True
    vehicle_terms = part_lookup_terms(vehicle_search_text(vehicle))
    app_terms = part_lookup_terms(app_text)
    if vehicle_terms & app_terms:
        return True
    if vehicle_year_matches_part(vehicle, part):
        return True
    vehicle_text = re.sub(r"[^a-z0-9]+", " ", vehicle_search_text(vehicle).lower())
    app_norm = re.sub(r"[^a-z0-9]+", " ", app_text.lower()).strip()
    return bool(app_norm and app_norm in vehicle_text)


def part_record_search_text(part: Dict[str, Any]) -> str:
    chunks = [
        part.get("part_number"),
        part.get("canonical_part_number"),
        part.get("description"),
        part.get("component"),
        part.get("model_family"),
        part.get("year_range"),
        part.get("applicability"),
        part.get("position"),
        " ".join(part.get("vin_family_keys") or []),
        part.get("verified_response"),
    ]
    for field in ["supersedes", "superseded_by", "equivalent_numbers", "keywords", "vin_family_keys"]:
        value = part.get(field)
        if isinstance(value, list):
            chunks.extend(value)
        else:
            chunks.append(value)
    return " ".join(str(item or "") for item in chunks)


def find_verified_parts_for_vehicle_help(vehicle: Dict[str, Any] | None, issue: str) -> List[Dict[str, Any]]:
    issue_text = str(issue or "").lower()
    issue_key = normalise_part_alias(issue)
    issue_terms = part_lookup_terms(issue_text)
    veh_text = vehicle_search_text(vehicle)
    veh_terms = part_lookup_terms(veh_text)
    matches: List[tuple[int, Dict[str, Any]]] = []

    for part in list_landrover_parts(include_unpublished=False):
        score = 0
        aliases = part_alias_set(part)
        if any(alias and alias in issue_key for alias in aliases):
            score += 80

        keyword_terms = part_lookup_terms(" ".join(part.get("keywords") or []))
        component_terms = part_lookup_terms(part.get("component"))
        description_terms = part_lookup_terms(part.get("description"))
        record_terms = part_lookup_terms(part_record_search_text(part))
        alias_match = any(alias and alias in issue_key for alias in aliases)
        component_intent_match = has_part_intent_match(issue_terms, keyword_terms, component_terms, description_terms)

        # For parts-number questions, do not return a verified part solely because the
        # vehicle applicability matches. The requested component must also match, unless
        # the member gave an explicit part/supersession number alias.
        if is_parts_request(issue) and not alias_match and not component_intent_match:
            continue

        # If the member selected a vehicle with a VIN, the verified record must be
        # scoped to that VIN family key (first 7 VIN characters, e.g. SALLDHM) or
        # explicitly contain that key in applicability. Explicit part-number alias
        # lookups are allowed through so admins can inspect supersession records.
        if is_parts_request(issue) and not alias_match and not part_vehicle_applicability_match(part, vehicle):
            continue

        # Strongly prefer intentional admin keywords/component matches.
        score += 14 * len(meaningful_part_terms(issue_terms) & meaningful_part_terms(keyword_terms))
        score += 12 * len(meaningful_part_terms(issue_terms) & meaningful_part_terms(component_terms))
        score += 8 * len(meaningful_part_terms(issue_terms) & meaningful_part_terms(description_terms))

        # Fall back to the wider record text, but keep it lower-weight to avoid noisy matches.
        wider_overlap = issue_terms & record_terms
        score += min(18, 3 * len(wider_overlap))

        app_text = " ".join(str(part.get(k) or "") for k in ["model_family", "year_range", "applicability", "position"]).lower()
        app_terms = part_lookup_terms(app_text)
        vehicle_overlap = veh_terms & app_terms
        vin_key = vehicle_vin_family_key(vehicle)
        record_vin_keys = set(split_vin_family_values(part.get("vin_family_keys")))
        if vin_key and (vin_key in record_vin_keys or vin_key in re.sub(r"[^A-Z0-9]", "", app_text.upper())):
            score += 30
        elif not app_terms:
            score += 2
        else:
            score += min(18, 3 * len(vehicle_overlap))

        # Year ranges are common in parts records; count a selected vehicle year inside the range.
        try:
            vehicle_year = int(str((vehicle or {}).get("year") or "").strip()[:4])
            year_range = str(part.get("year_range") or "")
            nums = [int(x) for x in re.findall(r"(?:19|20)\d{2}", year_range)]
            if len(nums) >= 2 and min(nums) <= vehicle_year <= max(nums):
                score += 8
            elif nums and vehicle_year in nums:
                score += 8
        except Exception:
            pass

        # A simple part-number request like "wheel bearings" should match a published
        # "Wheel bearing" component/keyword record without needing keyword spam.
        if is_parts_request(issue) and (issue_terms & (keyword_terms | component_terms | description_terms)):
            score += 8

        if score >= 10:
            matches.append((score, part))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [part for _score, part in matches[:5]]


def format_verified_parts_lookup(parts: List[Dict[str, Any]]) -> str:
    if not parts:
        return "None supplied. Do not provide exact part numbers."
    blocks = []
    for part in parts:
        lines = [
            f"Part number: {part.get('part_number') or ''}",
            f"Canonical/current: {part.get('canonical_part_number') or part.get('part_number') or ''}",
            f"Component: {part.get('component') or ''}",
            f"Description: {part.get('description') or ''}",
            f"Applicability: {' '.join(str(part.get(k) or '') for k in ['model_family','year_range','applicability','position']).strip()}",
        ]
        if part.get("vin_family_keys"):
            lines.append("VIN family keys: " + ", ".join(part.get("vin_family_keys") or []))
        if part.get("supersedes"):
            lines.append("Supersedes/older numbers: " + ", ".join(part.get("supersedes") or []))
        if part.get("superseded_by"):
            lines.append("Superseded/falls forward to: " + ", ".join(part.get("superseded_by") or []))
        if part.get("equivalent_numbers"):
            lines.append("Equivalent/cross-reference numbers: " + ", ".join(part.get("equivalent_numbers") or []))
        if part.get("verified_response"):
            lines.append("Verified response: " + str(part.get("verified_response")))
        if part.get("source_url"):
            lines.append("Source: " + str(part.get("source_url")))
        blocks.append("\n".join(line for line in lines if line.split(":",1)[-1].strip()))
    return "\n\n".join(blocks)


def admin_landrover_parts_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    return response(200, {"items": list_landrover_parts(include_unpublished=True)})


def save_admin_landrover_part_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    item = normalise_landrover_part_record(body.get("item") if isinstance(body.get("item"), dict) else body, claims)
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return response(200, {"message": "Land Rover part saved.", "item": landrover_part_summary(item)})


def delete_admin_landrover_part_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    part_number = clean_part_number(body.get("part_number"))
    if not part_number:
        raise ValueError("Part number is required.")
    ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=part_record_key(part_number))
    return response(200, {"message": "Land Rover part deleted.", "part_number": part_number})

def clean_vehicle_help_issue(value: Any, max_len: int = 2000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text[:max_len]


def vehicle_context_for_ai(vehicle: Dict[str, Any] | None) -> str:
    if not vehicle:
        return "No registry vehicle was selected. Ask for vehicle details where they affect troubleshooting."
    labels = [
        ("Title", " ".join(str(x or "").strip() for x in [vehicle.get("year"), vehicle.get("make"), vehicle.get("model"), vehicle.get("variant")] if str(x or "").strip()) or "Untitled vehicle"),
        ("Specific build", vehicle.get("specific_build")),
        ("Fuel type", vehicle.get("fuel_type")),
        ("Registration", vehicle.get("rego_number")),
        ("Registration expiry", vehicle.get("registration_expiry_date")),
        ("VIN/serial", vehicle.get("vin_serial_number")),
    ]
    return "\n".join(f"- {label}: {value}" for label, value in labels if str(value or "").strip())


def get_ssm_parameter_value(name: str, decrypt: bool = True, default: str = "") -> str:
    name = str(name or "").strip()
    if not name:
        return default
    if name in _SSM_CACHE:
        return _SSM_CACHE[name]
    try:
        response = ssm.get_parameter(Name=name, WithDecryption=decrypt)
        value = str(response.get("Parameter", {}).get("Value") or "").strip()
        if value == "__NOT_CONFIGURED__":
            return default
        _SSM_CACHE[name] = value
        return value
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"ParameterNotFound", "AccessDeniedException", "UnrecognizedClientException"}:
            return default
        raise


def get_openai_api_key() -> str:
    return get_ssm_parameter_value(OPENAI_API_KEY_PARAM, decrypt=True, default=OPENAI_API_KEY_FALLBACK).strip()


def get_openai_model() -> str:
    return get_ssm_parameter_value(OPENAI_MODEL_PARAM, decrypt=False, default=OPENAI_MODEL_FALLBACK).strip() or "gpt-5-mini"


def extract_openai_text(payload: Dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    def pull_text(value: Any) -> List[str]:
        found: List[str] = []
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
        elif isinstance(value, dict):
            for key in ("text", "output_text", "content", "value"):
                if key in value:
                    found.extend(pull_text(value.get(key)))
        elif isinstance(value, list):
            for child in value:
                found.extend(pull_text(child))
        return found

    parts: List[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"message", "output_text"}:
            parts.extend(pull_text(item.get("content") or item.get("text")))
        else:
            parts.extend(pull_text(item.get("content")))
    if parts:
        return "\n\n".join(part for part in parts if part).strip()
    return ""


def extract_openai_sources(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """Collect URL citations/sources returned by Responses web_search."""
    seen: set[str] = set()
    sources: List[Dict[str, str]] = []

    def add_source(url: Any, title: Any = "") -> None:
        url_text = str(url or "").strip()
        if not url_text or not re.match(r"^https?://", url_text, re.I):
            return
        if url_text in seen:
            return
        seen.add(url_text)
        sources.append({
            "url": url_text[:900],
            "title": str(title or url_text).strip()[:180],
        })

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "url_citation":
                citation = value.get("url_citation") if isinstance(value.get("url_citation"), dict) else value
                add_source(citation.get("url"), citation.get("title"))
            if "url" in value and ("title" in value or "source" in value):
                add_source(value.get("url"), value.get("title") or value.get("source"))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload.get("output") or [])
    walk(payload.get("sources") or [])
    return sources[:10]


def is_parts_request(issue: str) -> bool:
    text = str(issue or "").lower()
    return any(term in text for term in [
        "part number", "part no", "part #", "parts number", "oe number", "oem number", "sku",
        "bearing number", "filter number", "seal number", "kit number", "superseded", "supersession",
        "what part", "which part", "partnumber"
    ])


def should_use_vehicle_help_web_search(issue: str, verified_parts: List[Dict[str, Any]] | None) -> bool:
    return bool(OPENAI_WEB_SEARCH_ENABLED and is_parts_request(issue) and not (verified_parts or []))


def concise_join(values: List[Any], limit: int = 5) -> str:
    cleaned = [str(v).strip() for v in values if str(v or "").strip()]
    return ", ".join(cleaned[:limit])


def verified_part_answer(part: Dict[str, Any]) -> str:
    verified = str(part.get("verified_response") or "").strip()
    if verified:
        body = verified
    else:
        part_no = str(part.get("part_number") or "").strip()
        canonical = str(part.get("canonical_part_number") or part_no).strip()
        description = str(part.get("description") or part.get("component") or "part").strip()
        applicability_parts = [
            str(part.get("model_family") or "").strip(),
            str(part.get("year_range") or "").strip(),
            str(part.get("applicability") or "").strip(),
            str(part.get("position") or "").strip(),
        ]
        applicability_parts = [x for x in applicability_parts if x]
        lines = []
        if canonical and canonical != part_no:
            lines.append(f"Verified part: {canonical} for {description}. Older/fallback number: {part_no}.")
        elif part_no:
            lines.append(f"Verified part: {part_no} for {description}.")
        else:
            lines.append(f"Verified parts record found for {description}, but no part number is recorded.")
        if applicability_parts:
            rendered_applicability = "\n  ".join(part.replace("\n", "\n  ") for part in applicability_parts)
            lines.append("Applies to:\n  " + rendered_applicability)
        supersedes = concise_join(part.get("supersedes") or [])
        if supersedes:
            lines.append(f"Supersedes/older numbers: {supersedes}.")
        superseded_by = concise_join(part.get("superseded_by") or [])
        if superseded_by:
            lines.append(f"Falls forward to newer number(s): {superseded_by}.")
        equivalents = concise_join(part.get("equivalent_numbers") or [], limit=6)
        if equivalents:
            lines.append(f"Equivalent/cross-reference numbers: {equivalents}.")
        lines.append("Verify against the vehicle hub/axle before ordering.")
        body = "\n".join(f"- {line}" for line in lines)
    if body.lower().lstrip().startswith("answer"):
        return body.strip()
    return f"Answer\n{body.strip()}"


def verified_part_list_line(part: Dict[str, Any]) -> str:
    part_no = str(part.get("part_number") or "").strip()
    canonical = str(part.get("canonical_part_number") or part_no).strip()
    description = str(part.get("description") or part.get("component") or "part").strip()
    display_number = canonical or part_no or "part number not recorded"
    if canonical and part_no and canonical != part_no:
        display_number = f"{canonical} (older/fallback: {part_no})"
    bits = [f"{description}: {display_number}"]
    applies = concise_join([part.get("model_family"), part.get("year_range"), part.get("applicability"), part.get("position")], limit=6)
    if applies:
        bits.append(f"applies to {applies}")
    supersedes = concise_join(part.get("supersedes") or [], limit=5)
    if supersedes:
        bits.append(f"supersedes {supersedes}")
    superseded_by = concise_join(part.get("superseded_by") or [], limit=5)
    if superseded_by:
        bits.append(f"falls forward to {superseded_by}")
    equivalents = concise_join(part.get("equivalent_numbers") or [], limit=5)
    if equivalents:
        bits.append(f"equivalents/cross references {equivalents}")
    return " — ".join(bits)


def direct_verified_parts_answer(parts: List[Dict[str, Any]], issue: str) -> str:
    if not parts or not is_parts_request(issue):
        return ""
    if len(parts) == 1:
        return verified_part_answer(parts[0])
    shown = parts[:12]
    lines = [
        "Answer",
        f"I found {len(parts)} verified club Land Rover Parts records matching that vehicle/search. Check exact axle/hub/build details before ordering:",
    ]
    for idx, part in enumerate(shown, start=1):
        lines.append(f"- {idx}. {verified_part_list_line(part)}.")
    if len(parts) > len(shown):
        lines.append(f"- {len(parts) - len(shown)} additional verified match(es) are stored; refine the search term or vehicle details to narrow the list.")
    return "\n".join(lines)


def call_openai_vehicle_help(vehicle: Dict[str, Any] | None, issue: str, verified_parts: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    openai_api_key = get_openai_api_key()
    openai_model = get_openai_model()
    if not openai_api_key:
        raise RuntimeError("OpenAI API key is not configured for vehicle help yet.")
    verified_parts = verified_parts or []
    parts_request = is_parts_request(issue)
    use_web_search = bool(OPENAI_WEB_SEARCH_ENABLED and parts_request and not verified_parts)
    format_instruction = (
        "For parts-number requests, return only an Answer heading. Do not include Safety, Checks, Next step, or workshop checks. Maximum 90 words and 4 bullets. "
        if parts_request else
        "For diagnostic/safety requests, use the headings Answer, Safety, Checks, Next step only where relevant. Maximum 190 words and 8 bullets total. "
    )
    system_prompt = (
        "You are a cautious Land Rover club vehicle troubleshooting assistant for LROC members. "
        "Use the selected vehicle registry context when it is supplied, especially year, model, variant, specific build, fuel type and VIN/chassis. "
        "Provide practical suggestions only, not a definitive diagnosis. Prioritise safety. "
        "Do not invent specifications, torque settings, legal requirements, workshop procedures, or exact part numbers. "
        "For parts-number questions, exact part numbers are allowed only when they appear in either the verified parts lookup supplied by this application or in the web search sources returned for this request. "
        "If a verified parts lookup is supplied, you may quote those numbers exactly and mention supersession/fall-forward or fall-back relationships from that lookup only. "
        "If web search is used for part numbers, strongly prefer UK/ROW Land Rover parts-book style sources and UK Land Rover specialist suppliers. "
        "Treat US supplier pages as low-confidence for UK/ROW Land Rovers unless the member explicitly asks for US availability, because US listings are often NAS-focused, incomplete, ambiguous, or use supplier-internal SKUs. "
        "Never present a supplier SKU, catalogue listing ID, warehouse code, kit SKU, or aftermarket stock code as an OE/Land Rover part number unless the source clearly labels it as OE/Land Rover. "
        "Clearly distinguish OE/Land Rover numbers from aftermarket brands, kits, supersessions, equivalents, and supplier SKUs. State uncertainty and tell the member to verify by VIN/chassis before ordering. "
        "If neither verified lookup nor web source supports an exact number, say that you cannot provide a reliable exact part number and explain the safest verification path. "
        "Ask for missing details only when they genuinely affect identification. "
        "Tell the member to stop driving and seek competent mechanical help for safety-critical symptoms only for diagnostic or safety requests, not for simple parts-number lookups unless the member reports an unsafe symptom. "
        "Use Australian English. "
        f"{format_instruction}"
        "Answer the member's direct question first."
    )
    verified_parts_text = format_verified_parts_lookup(verified_parts)
    search_instruction = (
        "Web search is enabled for this parts request. Search current UK/ROW Land Rover parts sources first, using the vehicle context and issue. "
        "Preferred source types are official/parts-book style Land Rover catalogues and reputable UK Land Rover specialists. "
        "Avoid US supplier pages for exact part-number authority unless no UK/ROW source is available or the member explicitly asks for US availability. "
        "If a US page is used, label it low-confidence and do not treat its internal SKU as a Land Rover/OE number. "
        "Use web-supported exact part numbers only when a source clearly identifies them as Land Rover/OE, superseded, equivalent, or aftermarket replacement numbers."
        if use_web_search else
        "Web search is not enabled for this request. Use only verified lookup numbers above; otherwise do not provide exact part numbers."
    )
    user_prompt = (
        "Vehicle registry context:\n"
        f"{vehicle_context_for_ai(vehicle)}\n\n"
        "Verified parts lookup:\n"
        f"{verified_parts_text}\n\n"
        f"{search_instruction}\n\n"
        "Member issue notes:\n"
        f"{issue}\n\n"
        "Return a concise, conservative answer suitable for a club member to review before acting. "
        "If the member asks for a part number, use only verified lookup numbers or web-search-supported numbers from UK/ROW Land Rover parts sources where possible. Do not guess or infer a number from memory. "
        "Do not confuse supplier-internal SKUs with OE/Land Rover part numbers. If a source only provides a retailer SKU, say so and do not present it as the Land Rover part number. "
        "If no verified or web-supported number is available, name the component to verify and direct them to a Land Rover parts book, VIN/chassis lookup, measured old part, or trusted supplier. "
        "If the registry context is not enough, ask for the smallest set of missing details. "
        + ("For this parts-number request, output only the Answer section. Keep it token-light. " if parts_request else "Do not include long explanations, workshop-manual detail, or more than 8 bullets.")
    )
    output_cap = 550 if use_web_search else (360 if parts_request else 600)
    request_payload: Dict[str, Any] = {
        "model": openai_model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # GPT-5 family models can spend part of this allowance on internal reasoning.
        # Parts lookups should stay short to keep API output costs down.
        "max_output_tokens": output_cap,
    }
    if use_web_search:
        context_size = OPENAI_WEB_SEARCH_CONTEXT_SIZE if OPENAI_WEB_SEARCH_CONTEXT_SIZE in {"low", "medium", "high"} else "low"
        request_payload["tools"] = [{"type": "web_search", "search_context_size": context_size}]
        request_payload["tool_choice"] = "required"
        request_payload["include"] = ["web_search_call.action.sources"]
    if openai_model.lower().startswith("gpt-5"):
        # Responses web_search does not support gpt-5 with minimal reasoning, so use low when tools are enabled.
        request_payload["reasoning"] = {"effort": "low" if use_web_search else "minimal"}
        request_payload["text"] = {"verbosity": "low"}
    req = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60 if use_web_search else 45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        friendly = ""
        try:
            parsed = json.loads(detail)
            error = parsed.get("error") or {}
            if error.get("code") == "insufficient_quota":
                friendly = "Vehicle Help is configured, but the OpenAI API account has no available quota or prepaid credit. Please check OpenAI Platform billing and project limits."
            elif error.get("type") == "rate_limit_exceeded" or exc.code == 429:
                friendly = "The OpenAI service is rate-limiting Vehicle Help requests right now. Please wait a moment and try again."
        except Exception:
            friendly = ""
        if friendly:
            raise RuntimeError(friendly) from exc
        raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc
    text = extract_openai_text(data)
    if not text:
        status = str(data.get("status") or "").strip()
        incomplete = data.get("incomplete_details") if isinstance(data.get("incomplete_details"), dict) else {}
        reason = str(incomplete.get("reason") or "").strip()
        if status == "incomplete" or reason == "max_output_tokens":
            raise RuntimeError("OpenAI did not return visible text before the output limit. Please try again with a shorter question.")
        raise RuntimeError("OpenAI returned no readable suggestion text. Please try again, or include the vehicle year, model, engine, and axle/series details.")
    return {
        "text": text,
        "sources": extract_openai_sources(data) if use_web_search else [],
        "used_web_search": use_web_search,
    }

def member_vehicle_help_suggest_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    body = parse_body(event)
    issue = clean_vehicle_help_issue(body.get("issue"))
    if len(issue) < 12:
        raise ValueError("Please provide a more detailed vehicle issue description.")
    vehicle = None
    vehicle_id = clean_vehicle_id(body.get("vehicle_id"))
    if vehicle_id:
        vehicle = get_member_vehicle(sub, vehicle_id)
        if not vehicle:
            raise ValueError("Selected vehicle was not found in your vehicle registry.")
    verified_parts = find_verified_parts_for_vehicle_help(vehicle, issue)
    direct_answer = direct_verified_parts_answer(verified_parts, issue)
    if direct_answer:
        return response(200, {
            "message": "Verified parts answer generated.",
            "generated_at": utc_now(),
            "vehicle": vehicle,
            "verified_parts": verified_parts,
            "suggestion": direct_answer,
            "sources": [p.get("source_url") for p in verified_parts if p.get("source_url")],
            "used_web_search": False,
            "used_verified_parts": True,
            "review_notice": "Verified club parts records are a planning aid; confirm against the vehicle hub/axle before ordering.",
        })
    ai_result = call_openai_vehicle_help(vehicle, issue, verified_parts)
    return response(200, {
        "message": "Vehicle help suggestions generated.",
        "generated_at": utc_now(),
        "vehicle": vehicle,
        "verified_parts": verified_parts,
        "suggestion": ai_result.get("text") or "",
        "sources": ai_result.get("sources") or [],
        "used_web_search": bool(ai_result.get("used_web_search")),
        "used_verified_parts": bool(verified_parts),
        "review_notice": "AI-generated suggestions are for planning and member discussion only; verify before acting.",
    })


def clean_event_text(value: Any, max_len: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:max_len]


def clean_event_multiline(value: Any, max_len: int = 6000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_len]


def event_slug(value: Any, fallback: str = "event") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return (text or fallback)[:80]


def normalise_event_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.match(r"^[A-Za-z0-9_-]{6,120}$", text) else ""


def new_event_id(name: Any = "") -> str:
    base = event_slug(name, "trip")
    suffix = secrets.token_urlsafe(8).replace("-", "_")
    return f"evt_{base}_{suffix}"[:120]


def event_room_id(event_id: str) -> str:
    clean = normalise_event_id(event_id) or event_slug(event_id, "event")
    return f"event-{clean}"[:160]


def event_meta_key(event_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": "EVENTS"}, "sk": {"S": f"EVENT#{event_id}"}}


def event_registration_key(event_id: str, registration_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": f"EVENT#{event_id}"}, "sk": {"S": f"REGISTRATION#{registration_id}"}}


def member_event_registration_key(sub: str, event_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": member_pk(sub)}, "sk": {"S": f"EVENTREG#{event_id}"}}


def default_event_data() -> Dict[str, Any]:
    return deepcopy(DEFAULT_EVENT_DATA)


def clean_rating_color(value: Any) -> str:
    text = str(value or "").strip()
    if re.match(r"^#[0-9a-fA-F]{6}$", text):
        return text.lower()
    return ""


def normalise_event_data(data: Dict[str, Any] | None) -> Dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    raw_types = source.get("event_types") if isinstance(source.get("event_types"), dict) else {}
    event_types: Dict[str, Any] = {}
    for type_name, type_data in raw_types.items():
        type_label = clean_event_text(type_name, 64)
        if not type_label:
            continue
        raw_ratings = []
        rating_colors: Dict[str, str] = {}
        if isinstance(type_data, dict):
            if isinstance(type_data.get("rating_colors"), dict):
                for key, val in type_data.get("rating_colors", {}).items():
                    label = clean_event_text(key, 64)
                    colour = clean_rating_color(val)
                    if label and colour:
                        rating_colors[label] = colour
            if isinstance(type_data.get("ratings"), list):
                raw_ratings = type_data.get("ratings") or []
        ratings: List[str] = []
        seen: set[str] = set()
        for rating in raw_ratings:
            colour = ""
            if isinstance(rating, dict):
                label = clean_event_text(rating.get("name") or rating.get("label") or rating.get("rating"), 64)
                colour = clean_rating_color(rating.get("color") or rating.get("colour"))
            else:
                label = clean_event_text(rating, 64)
            key = label.lower()
            if label and key not in seen:
                ratings.append(label)
                seen.add(key)
            if label and colour:
                rating_colors[label] = colour
        event_types[type_label] = {"ratings": ratings, "rating_colors": {r: rating_colors.get(r, "") for r in ratings if rating_colors.get(r, "")}}
    if not event_types:
        event_types = deepcopy(DEFAULT_EVENT_DATA["event_types"])
    return {
        "version": int(source.get("version") or 1),
        "updated_at": clean_event_text(source.get("updated_at") or "", 32),
        "updated_by": clean_event_text(source.get("updated_by") or "", 128),
        "event_types": event_types,
    }


def load_event_data() -> Dict[str, Any]:
    defaults = normalise_event_data(default_event_data())
    if not SITE_BUCKET or not EVENT_DATA_KEY:
        return defaults
    try:
        resp = s3.get_object(Bucket=SITE_BUCKET, Key=EVENT_DATA_KEY)
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        return normalise_event_data(payload)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code") or "")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return defaults
        raise
    except Exception:
        return defaults


def save_event_data(payload: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    data = normalise_event_data(payload)
    data["updated_at"] = utc_now()
    data["updated_by"] = str(claims.get("email") or claims.get("sub") or "admin")
    s3.put_object(
        Bucket=SITE_BUCKET,
        Key=EVENT_DATA_KEY,
        Body=json.dumps(data, indent=2).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="no-store",
    )
    if SITE_DISTRIBUTION_ID:
        try:
            cloudfront.create_invalidation(
                DistributionId=SITE_DISTRIBUTION_ID,
                InvalidationBatch={
                    "Paths": {"Quantity": 1, "Items": [f"/{EVENT_DATA_KEY}"]},
                    "CallerReference": f"event-data-{datetime.now(timezone.utc).timestamp()}",
                },
            )
        except Exception:
            pass
    return data




def normalise_content_payload(payload: Any, previous_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return the site content document to publish.

    The browser editor sends {"content": {...}}.  Keep this intentionally light-touch:
    content.json is already authored by the admin editor, and over-normalising here risks
    dropping future site fields.  The previous payload is accepted for SGARS/LROC parity
    and future merge hooks, but is not currently required.
    """
    if isinstance(payload, dict) and isinstance(payload.get("content"), dict):
        payload = payload.get("content")
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object containing content.")
    return deepcopy(payload)


def invalidate_site_cache(paths: List[str]) -> None:
    if not SITE_DISTRIBUTION_ID:
        return
    clean_paths: List[str] = []
    for path in paths:
        text = str(path or "").strip()
        if not text:
            continue
        clean_paths.append(text if text.startswith("/") else f"/{text}")
    if not clean_paths:
        return
    try:
        cloudfront.create_invalidation(
            DistributionId=SITE_DISTRIBUTION_ID,
            InvalidationBatch={
                "Paths": {"Quantity": len(clean_paths), "Items": clean_paths},
                "CallerReference": f"lroc-content-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
            },
        )
    except Exception as exc:
        print(f"Could not create CloudFront invalidation for site content: {exc}")


def publish_site_content(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured for content publishing.")

    raw_payload = parse_body(event)
    existing_payload: Dict[str, Any] = {}
    published_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    published_by = str(claims.get("email") or claims.get("sub") or "admin")[:256]

    try:
        existing = s3.get_object(Bucket=SITE_BUCKET, Key=SITE_CONTENT_KEY)["Body"].read()
        try:
            existing_payload = json.loads(existing.decode("utf-8")) if existing else {}
        except Exception:
            existing_payload = {}
        s3.put_object(
            Bucket=SITE_BUCKET,
            Key=f"{SITE_HISTORY_PREFIX}{stamp}-content.json",
            Body=existing,
            ContentType="application/json; charset=utf-8",
            CacheControl="no-cache, no-store, must-revalidate",
            Metadata={"published-at": published_at, "published-by": published_by},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"NoSuchKey", "404", "NotFound"}:
            raise
    except Exception as exc:
        print(f"Could not write content history copy: {exc}")

    payload = normalise_content_payload(raw_payload, existing_payload)
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    s3.put_object(
        Bucket=SITE_BUCKET,
        Key=SITE_CONTENT_KEY,
        Body=body.encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="no-cache, no-store, must-revalidate",
        Metadata={"published-at": published_at, "published-by": published_by},
    )
    invalidate_site_cache([f"/{SITE_CONTENT_KEY}", "/*"])
    return response(200, {"message": "Published site content.", "published_at": published_at, "key": SITE_CONTENT_KEY})


def default_expo_page_content() -> Dict[str, Dict[str, Any]]:
    return {'index': {'label': 'Home', 'eyebrow': '19 July 2026 · Hawkesbury Showground', 'title': 'Share the passion at the Expo', 'lead': 'Old, new, classic, modern, restored, original, modified, off-road, camping or urban — if it has a Land Rover badge or spirit, this is the day to see it, display it, explore it and talk about it.', 'body': 'Browse club displays, talk to owners, compare builds, find parts and ideas, and enjoy a relaxed winter day at Hawkesbury Showground.', 'cards': [{'icon': '🚙', 'title': 'Bring the passion', 'text': 'Defender, Discovery, Range Rover, Series, Perentie, Forward Control, restored, modified or working — the variety is the point.', 'label': '', 'url': ''},
            {'icon': '🤝', 'title': 'Meet owners and clubs', 'text': 'Talk practical upgrades, touring setup, restoration work, camping ideas and the stories behind the vehicles.', 'label': '', 'url': ''},
            {'icon': '🛠️', 'title': 'Parts, ideas and gear', 'text': 'Find useful spares, tools, accessories and trader displays while catching up with the wider Land Rover community.', 'label': '', 'url': ''}], 'downloads': []},
            'visitor-info': {'label': 'Visitors', 'eyebrow': 'Plan your day', 'title': 'Visitor information', 'lead': 'Everything visitors need to enjoy the Land Rover Owners Expo.', 'body': 'Use this page to keep public visitor guidance up to date as Expo planning develops.', 'cards': [{'icon': '🎟️', 'title': 'Entry', 'text': 'Pre-purchased ticket: $10; purchase at gate: $15; under 16s free. Ticketing remains stubbed while the microsite is prepared.', 'label': '', 'url': ''},
            {'icon': '🚙', 'title': 'What to see', 'text': 'Land Rover displays, club and owner vehicles, swap/sell and parts interest, camping, touring and restoration ideas.', 'label': '', 'url': ''},
            {'icon': '🧥', 'title': 'Bring along', 'text': 'Warm layers and weather gear, comfortable shoes, a notebook for part numbers and ideas, and your Land Rover questions.', 'label': '', 'url': ''}], 'downloads': []},
            'exhibitors': {'label': 'Exhibitors', 'eyebrow': 'Display your vehicle', 'title': 'Exhibitors', 'lead': 'Showcase your Land Rover, Range Rover, Discovery, Defender, Freelander, Evoque, military, Perentie or Forward Control and help visitors experience the breadth of the marque.', 'body': 'Use this page for exhibitor application details, arrival times, display conditions and setup notes.', 'cards': [{'icon': '🚘', 'title': 'Who should exhibit?', 'text': 'Owners with restored, original, modified, touring, camping, military, classic or modern vehicles are encouraged to take part.', 'label': '', 'url': ''},
            {'icon': '📋', 'title': 'Exhibitor info to confirm', 'text': 'Arrival and setup times, gate entry instructions, display area allocation, insurance or safety requirements and pack-down timing.', 'label': '', 'url': ''}], 'downloads': []},
            'caterers': {'label': 'Caterers', 'eyebrow': 'Food vendors', 'title': 'Caterers', 'lead': 'Food and coffee vendors help make Expo a full-day destination for families, members, exhibitors and visitors.', 'body': 'Use this page for caterer expressions of interest, vendor requirements, power/water notes and insurance conditions.', 'cards': [{'icon': '☕', 'title': 'Caterer interest', 'text': 'Food, coffee and refreshment vendors can register interest with the Expo team while site arrangements are finalised.', 'label': '', 'url': ''},
            {'icon': '🔌', 'title': 'Information needed', 'text': 'Menu style, power/water needs, vehicle or trailer footprint, insurance and permits.', 'label': '', 'url': ''},
            {'icon': '👨\u200d👩\u200d👧\u200d👦', 'title': 'Goal', 'text': 'Keep visitors fed and comfortable so they stay longer, explore more vehicles and enjoy the day.', 'label': '', 'url': ''}], 'downloads': []},
            'tickets': {'label': 'Tickets', 'eyebrow': 'Entry', 'title': 'Tickets', 'lead': 'Ticket purchase is being prepared for the new Expo microsite.', 'body': 'Publish ticketing updates here while the purchase workflow is stubbed.', 'cards': [{'icon': '🎟️', 'title': 'Planned pricing', 'text': 'Earlybird pre-purchased tickets: $10; purchase at the gate: $15; under 16s free.', 'label': '', 'url': ''},
            {'icon': '↩️', 'title': 'Refund policy', 'text': 'Refunds are planned up to 7 days before the event. Final ticketing terms will be confirmed when the production ticket flow is enabled.', 'label': '', 'url': ''}], 'downloads': []},
            'camping': {'label': 'Camping', 'eyebrow': 'Stay nearby', 'title': 'Camping', 'lead': 'Camping information for exhibitors and visitors planning to stay at or near Hawkesbury Showground.', 'body': 'Use this page for camping request forms, bump-in/bump-out timing, facilities and rules.', 'cards': [{'icon': '🏕️', 'title': 'Camping requests', 'text': 'The existing Expo planning includes a camping request form. The new microsite will link the current approved form from Downloads when finalised.', 'label': '', 'url': ''},
            {'icon': '✅', 'title': 'What to confirm', 'text': 'Arrival window, departure time, facilities, quiet hours and showground rules.', 'label': '', 'url': ''},
            {'icon': '🌙', 'title': 'Good preparation', 'text': 'Pack for winter conditions, bring suitable lighting, and follow all showground and Expo volunteer directions.', 'label': '', 'url': ''}], 'downloads': []},
            'sponsors': {'label': 'Sponsors', 'eyebrow': 'Traders and support', 'title': 'Sponsors and traders', 'lead': 'Promote Land Rover services, parts, accessories, touring gear and club-friendly businesses.', 'body': 'Use this page for sponsor packages, trader stalls, swap/sell guidance and contact details.', 'cards': [{'icon': '⭐', 'title': 'Sponsors', 'text': 'Support the event, connect with an engaged 4WD audience and help grow the Land Rover community. Sponsor package details can be added here once approved.', 'label': '', 'url': ''},
            {'icon': '🧰', 'title': 'Traders / swap / sell', 'text': 'Parts, accessories, services and practical touring gear are a natural fit. Expression-of-interest forms can be linked from Downloads when ready.', 'label': '', 'url': ''}], 'downloads': []},
            'location': {'label': 'Location', 'eyebrow': 'Map and directions', 'title': 'Location', 'lead': 'Find Hawkesbury Showground and plan your trip to the Expo.', 'body': 'Venue and navigation information for Expo visitors.', 'cards': [{'icon': '📍', 'title': 'Venue', 'text': 'Hawkesbury Showground, Racecourse Road, Clarendon NSW 2756. Final gate and parking instructions will be added as Expo planning progresses.', 'label': '', 'url': ''},
            {'icon': '🧭', 'title': 'Planning your trip', 'text': 'Check traffic before departure, follow event signage and volunteer directions, allow time for parking and entry, and bring weather-appropriate gear.', 'label': '', 'url': ''}], 'downloads': []},
            'downloads': {'label': 'Downloads', 'eyebrow': 'Forms and flyers', 'title': 'Downloads', 'lead': 'Expo forms, flyers and information sheets will be published here as planning progresses.', 'body': 'Add public PDF links or external document links here.', 'cards': [{'icon': '📄', 'title': 'Flyer', 'text': 'Public Expo flyer download link will be published here when approved.', 'label': '', 'url': ''},
            {'icon': '📝', 'title': 'Forms', 'text': 'Camping, exhibitor, caterer and trader forms can be published here as PDFs or external links.', 'label': '', 'url': ''}], 'downloads': []},
            'contact': {'label': 'Contact', 'eyebrow': 'Expo enquiries', 'title': 'Contact', 'lead': 'Contact the Expo team for visitor, exhibitor, caterer, sponsor and camping enquiries.', 'body': 'Keep the public Expo contact information current here.', 'cards': [{'icon': '✉️', 'title': 'Expo contact', 'text': 'Jon Robinson — vicepresident@lroc.com.au. Use this for exhibitor, caterer, camping, ticketing and visitor enquiries until dedicated Expo forms are published.', 'label': 'Email Expo team', 'url': 'mailto:vicepresident@lroc.com.au'},
            {'icon': '🏠', 'title': 'Club site', 'text': 'Return to the main LROC site for membership, club documents, articles, magazines, vehicle help and member features.', 'label': 'Main LROC site', 'url': '/index.html'}], 'downloads': []}}


def default_expo_content() -> Dict[str, Any]:
    return {
        "event_name": "Land Rover Owners Expo 2026",
        "hero_title": "Share the passion at the Expo",
        "hero_lead": "Old, new, classic, modern, restored, original, modified, off-road, camping or urban — if it has a Land Rover badge or spirit, this is the day to see it, display it, explore it and talk about it.",
        "event_date": "Sunday 19 July 2026",
        "event_time": "9:00 AM – 4:00 PM",
        "venue_name": "Hawkesbury Showground",
        "venue_address": "Racecourse Road, Clarendon NSW 2756",
        "venue_latitude": "-33.609232",
        "venue_longitude": "150.784358",
        "ticket_summary": "Pre-purchase $10 · Gate price $15 · Under 16s free",
        "contact_name": "Jon Robinson",
        "contact_email": "vicepresident@lroc.com.au",
        "ticket_status": "Online ticket purchase is being prepared for the Expo microsite. For now this button is a placeholder while the new site is tested.",
        "pages": default_expo_page_content(),
        "updated_at": "",
        "updated_by": "",
    }


def normalise_expo_card(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {"icon": "", "title": "", "text": "", "url": "", "label": ""}
    return {
        "icon": str(value.get("icon") or "").strip()[:20],
        "title": str(value.get("title") or "").strip()[:180],
        "text": str(value.get("text") or "").strip()[:1200],
        "url": str(value.get("url") or "").strip()[:800],
        "label": str(value.get("label") or "").strip()[:120],
    }


def normalise_expo_page(value: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    src = value if isinstance(value, dict) else {}
    page = dict(fallback)
    for key, limit in {"label": 120, "eyebrow": 160, "title": 240, "lead": 1200, "body": 5000}.items():
        if key in src:
            page[key] = str(src.get(key) or "").strip()[:limit]
    for key in ["cards", "downloads"]:
        raw = src.get(key) if isinstance(src.get(key), list) else []
        cleaned = [normalise_expo_card(x) for x in raw[:24] if isinstance(x, dict)]
        page[key] = cleaned if cleaned else [normalise_expo_card(x) for x in (fallback.get(key) or [])[:24] if isinstance(x, dict)]
    return page


def normalise_expo_content(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("content"), dict):
        payload = payload.get("content")
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object containing Expo content.")
    base = default_expo_content()
    for key in list(base.keys()):
        if key in {"updated_at", "updated_by", "pages"}:
            continue
        if key in payload:
            base[key] = str(payload.get(key) or "").strip()[:4000]
    incoming_pages = payload.get("pages") if isinstance(payload.get("pages"), dict) else {}
    pages = default_expo_page_content()
    for key, fallback in pages.items():
        pages[key] = normalise_expo_page(incoming_pages.get(key), fallback)
    base["pages"] = pages
    return base


def get_expo_content_from_s3() -> Dict[str, Any]:
    if not SITE_BUCKET:
        return default_expo_content()
    try:
        raw = s3.get_object(Bucket=SITE_BUCKET, Key=EXPO_CONTENT_KEY)["Body"].read()
        data = json.loads(raw.decode("utf-8")) if raw else {}
        return normalise_expo_content(data if isinstance(data, dict) else {})
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            return default_expo_content()
        raise
    except Exception:
        return default_expo_content()


def admin_expo_content_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "GET":
        return response(200, {"content": get_expo_content_from_s3(), "key": EXPO_CONTENT_KEY})
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured for Expo content publishing.")
    existing = b""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    published_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    published_by = str(claims.get("email") or claims.get("sub") or "admin")[:256]
    try:
        existing = s3.get_object(Bucket=SITE_BUCKET, Key=EXPO_CONTENT_KEY)["Body"].read()
        if existing:
            s3.put_object(
                Bucket=SITE_BUCKET,
                Key=f"{EXPO_CONTENT_HISTORY_PREFIX}{stamp}-content.json",
                Body=existing,
                ContentType="application/json; charset=utf-8",
                CacheControl="no-cache, no-store, must-revalidate",
                Metadata={"published-at": published_at, "published-by": published_by},
            )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"NoSuchKey", "404", "NotFound"}:
            raise
    except Exception as exc:
        print(f"Could not write Expo content history copy: {exc}")
    payload = normalise_expo_content(parse_body(event))
    payload["updated_at"] = published_at
    payload["updated_by"] = published_by
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    s3.put_object(
        Bucket=SITE_BUCKET,
        Key=EXPO_CONTENT_KEY,
        Body=body.encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="no-cache, no-store, must-revalidate",
        Metadata={"published-at": published_at, "published-by": published_by},
    )
    invalidate_site_cache([f"/{EXPO_CONTENT_KEY}", "/expo/*"])
    return response(200, {"message": "Published Expo microsite content.", "content": payload, "published_at": published_at, "key": EXPO_CONTENT_KEY})


def system_claims() -> Dict[str, Any]:
    return {
        "sub": "system",
        "email": "system@lroc.local",
        "name": "LROC System",
        "cognito:groups": ["admins", "webmaster"],
    }


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    first = datetime(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


LROC_MONTHLY_MEETING_BLURB = """Come and meet with other members in person or online. Online link sent out 2 days prior to the event by email.

Where: Ashfield RSL Golf Club

Address: 374 Liverpool Rd, Ashfield NSW 2131

Description: LROC Monthly Meeting starts at 7:30pm."""

LROC_AGM_MEETING_BLURB = """This is our AGM and our Monthly Club Meeting.
This meeting we will be holding elections for our committee and job roles within the club.
If you think you are able to assist with running the club in some way please fill out a nomination form.

Come and meet with other members in person or online. Online link sent out 2 days prior to the event by email.

Where: Ashfield RSL Golf Club

Address: 374 Liverpool Rd, Ashfield NSW 2131

Description: LROC Monthly Meeting starts at 7:30pm."""


def lroc_monthly_meeting_payload(year: int, month: int) -> Dict[str, Any]:
    meeting_dt = nth_weekday_of_month(year, month, 2, 4).replace(hour=19, minute=30)
    meeting_end = meeting_dt + timedelta(hours=2)
    month_name = calendar.month_name[month]
    is_agm = month == 11
    title = f"{month_name} {year} Monthly Meeting{' and AGM' if is_agm else ''}"
    return {
        "event_id": f"lroc-monthly-meeting-{year}-{month:02d}",
        "trip_name": title,
        "date_from": meeting_dt.strftime("%Y-%m-%dT%H:%M"),
        "date_to": meeting_end.strftime("%Y-%m-%dT%H:%M"),
        "blurb": LROC_AGM_MEETING_BLURB if is_agm else LROC_MONTHLY_MEETING_BLURB,
        "image_key": "",
        "meeting_location": {
            "name": "Ashfield RSL Golf Club",
            "address": "374 Liverpool Rd, Ashfield NSW 2131",
            "lat": "",
            "lng": "",
            "source": "club_default",
        },
        "trip_leader_member_sub": "",
        "trip_leader_name": "",
        "trip_leader_email": "",
        "trip_leader_phone": "",
        "fee_enabled": False,
        "fee_amount": "",
        "fee_currency": "AUD",
        "payment_provider": "square",
        "payment_status_mode": "stub",
        "event_type": "Social",
        "rating": "",
        "vehicle_limit": 0,
        "show_area_map": True,
        "pets_allowed": False,
        "trailers_allowed": False,
        "caravans_allowed": False,
        "public_registration_enabled": False,
        "published": True,
        "status": "active",
        "auto_generated": True,
        "auto_series": "lroc_monthly_meeting",
        "auto_year": year,
        "auto_month": month,
        "suppress_general_chat_notification": True,
        "notification_policy": {
            "future_pwa_notification": True,
            "future_email_notification": True,
            "email_days_before": 2,
            "status": "stub_future_implementation",
        },
    }


def ensure_lroc_monthly_meetings(year: int | None = None) -> Dict[str, Any]:
    if not ENABLE_LROC_MONTHLY_MEETINGS:
        return {"enabled": False, "year": year, "created": 0, "existing": 0, "items": []}
    require_metadata_table()
    year = int(year or current_club_date().year)
    created = 0
    existing = 0
    items: List[Dict[str, Any]] = []
    claims = system_claims()
    now = utc_now_precise()
    for month in range(1, 12):
        payload = lroc_monthly_meeting_payload(year, month)
        event_id = payload["event_id"]
        current = get_event_item(event_id)
        if current:
            existing += 1
            items.append(event_summary(current, include_private=True, include_counts=True))
            continue
        item = {
            "pk": "EVENTS",
            "sk": f"EVENT#{event_id}",
            "item_type": "event",
            "event_id": event_id,
            "chat_room_id": event_room_id(event_id),
            **payload,
            "created_at": now,
            "updated_at": now,
            "updated_by": "system:lroc-monthly-meetings",
        }
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
        summary = event_summary(item, include_private=True, include_counts=True)
        ensure_event_chat_room(summary, claims)
        items.append(summary)
        created += 1
    return {"enabled": True, "year": year, "created": created, "existing": existing, "items": items}


def geoapify_geocode_search(query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    if not GEOAPIFY_GEOCODING_API_KEY:
        raise RuntimeError("Geoapify geocoding API key is not configured.")
    q = clean_event_text(query, 300)
    if not q:
        raise ValueError("Search text is required.")
    limit = max(1, min(10, int(limit or 5)))
    params = {
        "text": q,
        "limit": str(limit),
        "filter": "countrycode:au",
        "apiKey": GEOAPIFY_GEOCODING_API_KEY,
    }
    base_url = GEOAPIFY_GEOCODING_URL.split("?", 1)[0].rstrip("?") or "https://api.geoapify.com/v1/geocode/search"
    url = f"{base_url}?{urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "LROC/1.0 Geoapify geocoder"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:240]
        raise RuntimeError(f"Geoapify geocoding failed with HTTP {exc.code}: {detail}")
    features = payload.get("features") if isinstance(payload, dict) else []
    results: List[Dict[str, Any]] = []
    for feature in features or []:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        geom = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
        coords = geom.get("coordinates") if isinstance(geom.get("coordinates"), list) else []
        lng = props.get("lon") if props.get("lon") not in {None, ""} else (coords[0] if len(coords) >= 2 else "")
        lat = props.get("lat") if props.get("lat") not in {None, ""} else (coords[1] if len(coords) >= 2 else "")
        if lat in {None, ""} or lng in {None, ""}:
            continue
        label = clean_event_text(props.get("formatted") or props.get("address_line1") or props.get("name") or q, 300)
        results.append({
            "label": label,
            "address": clean_event_text(props.get("formatted") or label, 300),
            "name": clean_event_text(props.get("name") or props.get("address_line1") or "", 160),
            "lat": str(lat),
            "lng": str(lng),
            "place_id": clean_event_text(props.get("place_id") or props.get("place_id_hash") or "", 120),
            "source": "geoapify",
        })
    return results



def parse_event_dt(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # Browser datetime-local values arrive as YYYY-MM-DDTHH:MM. ISO timestamps are accepted too.
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", text):
        return text
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return f"{text}T00:00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        raise ValueError("Event date/time fields must be valid ISO date/time values.")


def event_date_for_sort(event: Dict[str, Any]) -> str:
    return str(event.get("date_from") or event.get("date_to") or event.get("created_at") or "")


def validate_event_payload(body: Dict[str, Any], claims: Dict[str, Any], *, existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    title = clean_event_text(body.get("trip_name") or body.get("title") or body.get("name"), 160)
    if not title:
        raise ValueError("Trip name is required.")
    date_from = parse_event_dt(body.get("date_from") or body.get("start_at") or body.get("start"))
    date_to = parse_event_dt(body.get("date_to") or body.get("end_at") or body.get("end")) or date_from
    vehicle_limit_raw = str(body.get("vehicle_limit") or "").strip()
    vehicle_limit = 0
    if vehicle_limit_raw:
        try:
            vehicle_limit = max(0, int(vehicle_limit_raw))
        except Exception:
            raise ValueError("Vehicle limit must be a whole number or blank.")
    fee_amount = clean_event_text(body.get("fee_amount"), 32)
    location = body.get("meeting_location") if isinstance(body.get("meeting_location"), dict) else {}
    lat = clean_event_text(location.get("lat") or body.get("lat"), 32)
    lng = clean_event_text(location.get("lng") or body.get("lng"), 32)
    if lat:
        try: float(lat)
        except Exception: raise ValueError("Latitude must be numeric or blank.")
    if lng:
        try: float(lng)
        except Exception: raise ValueError("Longitude must be numeric or blank.")
    leader = body.get("trip_leader") if isinstance(body.get("trip_leader"), dict) else {}
    leader_sub = clean_event_text(body.get("trip_leader_member_sub") or leader.get("member_sub") or leader.get("sub"), 120)
    leader_name = clean_event_text(body.get("trip_leader_name") or leader.get("name"), 160)
    leader_email = normalise_email_address(body.get("trip_leader_email") or leader.get("email") or "")
    leader_phone = clean_event_text(body.get("trip_leader_phone") or leader.get("phone") or leader.get("phone_number"), 60)
    return {
        "trip_name": title,
        "date_from": date_from,
        "date_to": date_to,
        "short_description": clean_event_text(body.get("short_description") or body.get("shortDescription") or body.get("calendar_blurb") or body.get("calendarBlurb"), 600),
        "blurb": clean_event_multiline(body.get("blurb") or body.get("description"), 6000),
        "image_key": clean_event_text(body.get("image_key") or (existing or {}).get("image_key") or "", 240),
        "meeting_location": {
            "name": clean_event_text(location.get("name") or body.get("meeting_name"), 160),
            "address": clean_event_text(location.get("address") or body.get("meeting_address"), 300),
            "lat": lat,
            "lng": lng,
            "source": clean_event_text(location.get("source") or body.get("meeting_source") or "manual", 40),
            "place_id": clean_event_text(location.get("place_id") or body.get("meeting_place_id") or "", 120),
            "label": clean_event_text(location.get("label") or location.get("formatted") or body.get("meeting_label") or "", 300),
        },
        "trip_leader_member_sub": leader_sub,
        "trip_leader_name": leader_name,
        "trip_leader_email": leader_email,
        "trip_leader_phone": leader_phone,
        "fee_enabled": bool(body.get("fee_enabled")),
        "fee_amount": fee_amount,
        "fee_currency": clean_event_text(body.get("fee_currency") or "AUD", 8) or "AUD",
        "payment_provider": "square",
        "payment_status_mode": "stub",
        "event_type": clean_event_text(body.get("event_type"), 64),
        "rating": clean_event_text(body.get("rating"), 64),
        "vehicle_limit": vehicle_limit,
        "show_area_map": bool(body.get("show_area_map")),
        "pets_allowed": bool(body.get("pets_allowed")),
        "trailers_allowed": bool(body.get("trailers_allowed")),
        "caravans_allowed": bool(body.get("caravans_allowed")),
        "public_registration_enabled": bool(body.get("public_registration_enabled")),
        "published": body.get("published", True) is not False,
    }


def event_image_public_url(key: str) -> str:
    key = str(key or "").strip().lstrip("/")
    return f"/{key}" if key else ""


def count_event_registrations(event_id: str) -> Dict[str, int]:
    require_metadata_table()
    vehicle_count = 0
    people_count = 0
    registration_count = 0
    last_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": f"EVENT#{event_id}"}, ":prefix": {"S": "REGISTRATION#"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.query(**kwargs)
        for raw in resp.get("Items") or []:
            item = item_to_python(raw)
            if str(item.get("status") or "registered") != "registered":
                continue
            registration_count += 1
            people_count += max(1, int(item.get("people_count") or 1))
            if item.get("vehicle_id") or (item.get("vehicle_snapshot") or {}).get("vehicle_id"):
                vehicle_count += 1
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return {"registration_count": registration_count, "people_count": people_count, "vehicle_count": vehicle_count}


def event_summary(item: Dict[str, Any], *, include_private: bool = False, include_counts: bool = True) -> Dict[str, Any]:
    event_id = str(item.get("event_id") or str(item.get("sk") or "").replace("EVENT#", "", 1)).strip()
    out = {
        "event_id": event_id,
        "trip_name": clean_event_text(item.get("trip_name"), 160),
        "date_from": clean_event_text(item.get("date_from"), 40),
        "date_to": clean_event_text(item.get("date_to"), 40),
        "short_description": clean_event_text(item.get("short_description") or item.get("calendar_blurb"), 600),
        "blurb": clean_event_multiline(item.get("blurb"), 6000),
        "image_key": clean_event_text(item.get("image_key"), 240),
        "image_url": event_image_public_url(str(item.get("image_key") or "")),
        "meeting_location": item.get("meeting_location") if isinstance(item.get("meeting_location"), dict) else {},
        "trip_leader_name": clean_event_text(item.get("trip_leader_name"), 160),
        "fee_enabled": bool(item.get("fee_enabled")),
        "fee_amount": clean_event_text(item.get("fee_amount"), 32),
        "fee_currency": clean_event_text(item.get("fee_currency") or "AUD", 8) or "AUD",
        "payment_provider": clean_event_text(item.get("payment_provider") or "square", 32),
        "payment_status_mode": clean_event_text(item.get("payment_status_mode") or "stub", 32),
        "event_type": clean_event_text(item.get("event_type"), 64),
        "rating": clean_event_text(item.get("rating"), 64),
        "vehicle_limit": int(item.get("vehicle_limit") or 0),
        "show_area_map": bool(item.get("show_area_map")),
        "pets_allowed": bool(item.get("pets_allowed")),
        "trailers_allowed": bool(item.get("trailers_allowed")),
        "caravans_allowed": bool(item.get("caravans_allowed")),
        "public_registration_enabled": bool(item.get("public_registration_enabled")),
        "published": item.get("published", True) is not False,
        "status": clean_event_text(item.get("status") or "active", 32),
        "chat_room_id": clean_event_text(item.get("chat_room_id") or event_room_id(event_id), 160),
        "created_at": clean_event_text(item.get("created_at"), 40),
        "updated_at": clean_event_text(item.get("updated_at"), 40),
    }
    if include_private:
        out.update({
            "trip_leader_member_sub": clean_event_text(item.get("trip_leader_member_sub"), 120),
            "trip_leader_email": normalise_email_address(item.get("trip_leader_email") or ""),
            "trip_leader_phone": clean_event_text(item.get("trip_leader_phone"), 60),
            "updated_by": clean_event_text(item.get("updated_by"), 160),
            "auto_generated": bool(item.get("auto_generated")),
            "auto_series": clean_event_text(item.get("auto_series"), 80),
            "auto_year": int(item.get("auto_year") or 0),
            "auto_month": int(item.get("auto_month") or 0),
            "notification_policy": item.get("notification_policy") if isinstance(item.get("notification_policy"), dict) else {},
        })
    if include_counts and event_id:
        out.update(count_event_registrations(event_id))
        limit = int(out.get("vehicle_limit") or 0)
        out["vehicle_spaces_remaining"] = max(0, limit - int(out.get("vehicle_count") or 0)) if limit else None
    return out


def get_event_item(event_id: str) -> Dict[str, Any] | None:
    event_id = normalise_event_id(event_id)
    if not event_id:
        return None
    require_metadata_table()
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=event_meta_key(event_id), ConsistentRead=True)
    if not resp.get("Item"):
        return None
    item = item_to_python(resp["Item"])
    if str(item.get("status") or "active") == "deleted":
        return None
    return item


def list_trip_events(*, admin: bool = False) -> List[Dict[str, Any]]:
    require_metadata_table()
    try:
        ensure_lroc_monthly_meetings(current_club_date().year)
    except Exception:
        pass
    items: List[Dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": "EVENTS"}, ":prefix": {"S": "EVENT#"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.query(**kwargs)
        for raw in resp.get("Items") or []:
            item = item_to_python(raw)
            if str(item.get("status") or "active") == "deleted":
                continue
            if not admin and not bool(item.get("published", True)):
                continue
            items.append(event_summary(item, include_private=admin, include_counts=True))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    items.sort(key=lambda item: (event_date_for_sort(item), str(item.get("trip_name") or "").lower()))
    return items


def trip_event_chat_room(item: Dict[str, Any], idx: int = 0) -> Dict[str, Any] | None:
    event_id = str(item.get("event_id") or "").strip()
    if not event_id:
        return None
    start = parse_event_date_value(str(item.get("date_from") or "").split("T", 1)[0])
    live_until = (start + timedelta(days=7)) if start else (current_club_date() + timedelta(days=30))
    location = item.get("meeting_location") if isinstance(item.get("meeting_location"), dict) else {}
    parts = [str(item.get("event_type") or "").strip(), str(item.get("rating") or "").strip(), str(location.get("name") or location.get("address") or "").strip()]
    return {
        "room_id": str(item.get("chat_room_id") or event_room_id(event_id)),
        "title": str(item.get("trip_name") or "Event chat").strip() or "Event chat",
        "description": " • ".join([p for p in parts if p]),
        "room_kind": "event",
        "required_any_groups": sorted(CHAT_MEMBER_GROUPS),
        "default_joined": False,
        "active": bool(item.get("published", True)),
        "event_date": start.isoformat() if start else str(item.get("date_from") or ""),
        "live_until": live_until.isoformat(),
        "created_at": str(item.get("created_at") or utc_now_precise()),
        "sort_order": 1000 + idx,
    }


def ensure_event_chat_room(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any] | None:
    try:
        room = trip_event_chat_room(event)
        if not room:
            return None
        room["created_by"] = str(claims.get("sub") or "")
        room["created_by_label"] = get_member_display_label(claims)
        return save_chat_room_meta(room)
    except Exception:
        return None


def announce_event_change(event: Dict[str, Any], claims: Dict[str, Any], *, created: bool = False) -> None:
    try:
        room_id = str(event.get("chat_room_id") or event_room_id(event.get("event_id") or ""))
        title = str(event.get("trip_name") or "Club event")
        start = str(event.get("date_from") or "")
        action = "New trip added" if created else "Trip updated"
        body = f"{action}: {title}"
        if start:
            body += f"\nDate/time: {start}"
        if event.get("event_type") or event.get("rating"):
            body += f"\nRating: {' / '.join([str(event.get('event_type') or '').strip(), str(event.get('rating') or '').strip()]).strip(' /')}"
        body += f"\n[[join:{room_id}|Open this event chat]]"
        message = append_chat_message("general-chat", body, system=True, system_label="Event", message_type="event_announcement", event_room_id=room_id, notify_members=True)
        enqueue_chat_notification({"room_id": "general-chat", "title": "General", "room_kind": "default"}, message)
        if not created:
            append_chat_message(room_id, f"Trip details updated: {title}. Please check the Events page for the latest details.", system=True, system_label="Event", message_type="event_update")
    except Exception:
        pass


def save_trip_event(body: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_metadata_table()
    event_id = normalise_event_id(body.get("event_id")) or new_event_id(body.get("trip_name") or body.get("title"))
    existing = get_event_item(event_id)
    now = utc_now_precise()
    payload = validate_event_payload(body, claims, existing=existing)
    item = {
        "pk": "EVENTS",
        "sk": f"EVENT#{event_id}",
        "item_type": "event",
        "event_id": event_id,
        "chat_room_id": str((existing or {}).get("chat_room_id") or event_room_id(event_id)),
        **payload,
        "status": "active",
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or "admin"),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    summary = event_summary(item, include_private=True, include_counts=True)
    ensure_event_chat_room(summary, claims)
    announce_event_change(summary, claims, created=not bool(existing))
    return summary


def delete_trip_event(event_id: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    require_metadata_table()
    item = get_event_item(event_id)
    if not item:
        raise ValueError("Event not found.")
    item["status"] = "deleted"
    item["published"] = False
    item["deleted_at"] = utc_now_precise()
    item["deleted_by"] = str(claims.get("email") or claims.get("sub") or "admin")
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    try:
        room_id = str(item.get("chat_room_id") or event_room_id(event_id))
        meta = get_chat_room_meta_item(room_id) or {}
        if meta:
            meta["active"] = False
            meta["closed_at"] = utc_now_precise()
            meta["closed_by"] = str(claims.get("email") or claims.get("sub") or "admin")
            save_chat_room_meta(meta)
        append_chat_message("general-chat", f"Trip removed: {item.get('trip_name') or event_id}.", system=True, system_label="Event", message_type="event_deleted")
    except Exception:
        pass
    return {"event_id": event_id, "deleted": True}


def create_event_image_upload_url(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    body = parse_body(event)
    event_id = normalise_event_id(body.get("event_id")) or new_event_id(body.get("trip_name") or "trip")
    filename = clean_event_text(body.get("filename") or "event-image.jpg", 160)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Event images must be JPG, PNG, or WebP.")
    content_type = str(body.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream").strip()
    key = f"{EVENTS_IMAGE_PREFIX}{event_id}/{secrets.token_urlsafe(8)}{ext}"
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": SITE_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=UPLOAD_EXPIRY,
    )
    return response(200, {"event_id": event_id, "upload_url": url, "key": key, "public_url": f"/{key}"})


def public_events_route(_event: Dict[str, Any]) -> Dict[str, Any]:
    return response(200, {"items": list_trip_events(admin=False), "event_data": load_event_data()})


def admin_events_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    return response(200, {"items": list_trip_events(admin=True), "event_data": load_event_data()})


def save_admin_event_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    saved = save_trip_event(parse_body(event), claims)
    return response(200, {"message": "Trip/event saved.", "item": saved})


def save_admin_event_short_descriptions_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    require_metadata_table()
    body = parse_body(event)
    raw_items = body.get("items") if isinstance(body.get("items"), list) else []
    updated: List[Dict[str, Any]] = []
    now = utc_now_precise()
    for raw in raw_items[:80]:
        if not isinstance(raw, dict):
            continue
        event_id = normalise_event_id(raw.get("event_id") or raw.get("eventId"))
        if not event_id:
            continue
        item = get_event_item(event_id)
        if not item or item.get("status") == "deleted":
            continue
        item["short_description"] = clean_event_text(raw.get("short_description") or raw.get("shortDescription") or raw.get("description"), 600)
        item["updated_at"] = now
        item["updated_by"] = str(claims.get("email") or claims.get("sub") or "admin")
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
        updated.append(event_summary(item, include_private=True, include_counts=False))
    return response(200, {"message": f"Updated {len(updated)} event short description(s).", "items": updated})


def delete_admin_event_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    deleted = delete_trip_event(str(body.get("event_id") or ""), claims)
    return response(200, {"message": "Trip/event deleted.", "item": deleted})


def admin_event_data_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    return response(200, load_event_data())


def save_admin_event_data_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    data = save_event_data(body.get("event_data") if isinstance(body.get("event_data"), dict) else body, claims)
    return response(200, {"message": "Event data saved.", "event_data": data})


def admin_geocode_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    query = str(body.get("text") or body.get("query") or "").strip()
    limit = int(body.get("limit") or 5)
    if not GEOAPIFY_GEOCODING_API_KEY:
        return response(200, {
            "items": [],
            "configured": False,
            "message": "Address search is not configured. Add geoapify_maptiles_api_key or geoapify_geocoding_api_key in Terraform, or use Search in maps and enter coordinates manually."
        })
    return response(200, {"items": geoapify_geocode_search(query, limit=limit), "configured": True})


def seed_lroc_meetings_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    year = int(body.get("year") or current_club_date().year)
    result = ensure_lroc_monthly_meetings(year)
    return response(200, {"message": f"LROC monthly meetings checked for {year}. Created {result.get('created', 0)} missing event(s).", **result})


def registration_summary(item: Dict[str, Any], *, include_private: bool = False) -> Dict[str, Any]:
    out = {
        "registration_id": clean_event_text(item.get("registration_id"), 120),
        "event_id": clean_event_text(item.get("event_id"), 120),
        "member_sub": clean_event_text(item.get("member_sub"), 120),
        "registrant_name": clean_event_text(item.get("registrant_name"), 160),
        "people_count": max(1, int(item.get("people_count") or 1)),
        "vehicle_id": clean_event_text(item.get("vehicle_id"), 120),
        "vehicle_snapshot": item.get("vehicle_snapshot") if isinstance(item.get("vehicle_snapshot"), dict) else {},
        "status": clean_event_text(item.get("status") or "registered", 32),
        "payment_required": bool(item.get("payment_required")),
        "payment_status": clean_event_text(item.get("payment_status") or "not_required", 64),
        "refund_status": clean_event_text(item.get("refund_status") or "not_applicable", 64),
        "created_at": clean_event_text(item.get("created_at"), 40),
        "updated_at": clean_event_text(item.get("updated_at"), 40),
        "cancelled_at": clean_event_text(item.get("cancelled_at"), 40),
    }
    if include_private:
        out["registrant_email"] = normalise_email_address(item.get("registrant_email") or "")
    return out


def registration_id_for_member(sub: str, event_id: str) -> str:
    digest = hashlib.sha1(f"{sub}:{event_id}".encode("utf-8")).hexdigest()[:16]
    return f"reg_{digest}"


def get_member_event_registration(sub: str, event_id: str) -> Dict[str, Any] | None:
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=member_event_registration_key(sub, event_id), ConsistentRead=True)
    if not resp.get("Item"):
        return None
    mirror = item_to_python(resp["Item"])
    registration_id = str(mirror.get("registration_id") or registration_id_for_member(sub, event_id))
    resp2 = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=event_registration_key(event_id, registration_id), ConsistentRead=True)
    if not resp2.get("Item"):
        return None
    return item_to_python(resp2["Item"])


def list_event_attendees(event_id: str, *, include_private: bool = False) -> List[Dict[str, Any]]:
    require_metadata_table()
    event_id = normalise_event_id(event_id)
    if not event_id:
        raise ValueError("event_id is required.")
    items: List[Dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": f"EVENT#{event_id}"}, ":prefix": {"S": "REGISTRATION#"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.query(**kwargs)
        for raw in resp.get("Items") or []:
            item = item_to_python(raw)
            if str(item.get("status") or "registered") == "registered":
                items.append(registration_summary(item, include_private=include_private))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    items.sort(key=lambda item: str(item.get("registrant_name") or "").lower())
    return items


def save_event_registration(event_id: str, body: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_metadata_table()
    event_id = normalise_event_id(event_id or body.get("event_id"))
    if not event_id:
        raise ValueError("event_id is required.")
    event_item = get_event_item(event_id)
    if not event_item or not bool(event_item.get("published", True)):
        raise ValueError("That event is not available for registration.")
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    people_count = max(1, min(99, int(body.get("people_count") or 1)))
    vehicle_id = clean_vehicle_id(body.get("vehicle_id"))
    vehicle_snapshot: Dict[str, Any] = {}
    if vehicle_id:
        vehicle = get_member_vehicle(sub, vehicle_id)
        if not vehicle:
            raise ValueError("Selected vehicle was not found in your vehicle register.")
        vehicle_snapshot = dict(vehicle)
    counts = count_event_registrations(event_id)
    existing = get_member_event_registration(sub, event_id)
    existing_active_vehicle = bool(existing and str(existing.get("status") or "registered") == "registered" and existing.get("vehicle_id"))
    new_active_vehicle = bool(vehicle_id)
    if new_active_vehicle and not existing_active_vehicle:
        limit = int(event_item.get("vehicle_limit") or 0)
        if limit and counts.get("vehicle_count", 0) >= limit:
            raise ValueError("This trip has reached its vehicle limit.")
    registration_id = str((existing or {}).get("registration_id") or registration_id_for_member(sub, event_id))
    now = utc_now_precise()
    registrant_name = clean_event_text(claims.get("name") or claims.get("preferred_username") or claims.get("email") or "Member", 160)
    payload = {
        "pk": f"EVENT#{event_id}",
        "sk": f"REGISTRATION#{registration_id}",
        "item_type": "event_registration",
        "registration_id": registration_id,
        "event_id": event_id,
        "member_sub": sub,
        "registrant_name": registrant_name,
        "registrant_email": normalise_email_address(claims.get("email") or ""),
        "people_count": people_count,
        "vehicle_id": vehicle_id,
        "vehicle_snapshot": vehicle_snapshot,
        "status": "registered",
        "payment_required": bool(event_item.get("fee_enabled")),
        "payment_status": "not_implemented" if bool(event_item.get("fee_enabled")) else "not_required",
        "refund_status": "not_applicable",
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
        "cancelled_at": "",
    }
    mirror = {
        "pk": member_pk(sub),
        "sk": f"EVENTREG#{event_id}",
        "item_type": "member_event_registration",
        "event_id": event_id,
        "registration_id": registration_id,
        "status": "registered",
        "updated_at": now,
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(payload))
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(mirror))
    try:
        append_chat_message(str(event_item.get("chat_room_id") or event_room_id(event_id)), f"{registrant_name} registered for this trip.", system=True, system_label="Registration", message_type="event_registration")
    except Exception:
        pass
    return registration_summary(payload, include_private=True)


def cancel_event_registration(event_id: str, claims: Dict[str, Any]) -> Dict[str, Any]:
    require_metadata_table()
    event_id = normalise_event_id(event_id)
    if not event_id:
        raise ValueError("event_id is required.")
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    existing = get_member_event_registration(sub, event_id)
    if not existing or str(existing.get("status") or "") != "registered":
        raise ValueError("You are not currently registered for this event.")
    now = utc_now_precise()
    existing["status"] = "cancelled"
    existing["cancelled_at"] = now
    existing["updated_at"] = now
    if bool(existing.get("payment_required")):
        existing["refund_status"] = "refund_not_implemented"
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(existing))
    mirror = {
        "pk": member_pk(sub),
        "sk": f"EVENTREG#{event_id}",
        "item_type": "member_event_registration",
        "event_id": event_id,
        "registration_id": str(existing.get("registration_id") or ""),
        "status": "cancelled",
        "updated_at": now,
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(mirror))
    try:
        item = get_event_item(event_id) or {}
        append_chat_message(str(item.get("chat_room_id") or event_room_id(event_id)), f"{existing.get('registrant_name') or 'A member'} cancelled their registration.", system=True, system_label="Registration", message_type="event_registration_cancelled")
    except Exception:
        pass
    return registration_summary(existing, include_private=True)


def member_event_registration_status(sub: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for item in events:
        event_id = str(item.get("event_id") or "")
        if not event_id:
            continue
        try:
            reg = get_member_event_registration(sub, event_id)
            if reg:
                result[event_id] = registration_summary(reg, include_private=True)
        except Exception:
            pass
    return result


def list_member_events_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    items = list_trip_events(admin=False)
    sub = str(claims.get("sub") or "").strip()
    return response(200, {"items": items, "event_data": load_event_data(), "registrations": member_event_registration_status(sub, items)})


def register_member_event_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    item = save_event_registration(str(body.get("event_id") or ""), body, claims)
    return response(200, {"message": "Registration saved.", "item": item})


def cancel_member_event_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    item = cancel_event_registration(str(body.get("event_id") or ""), claims)
    return response(200, {"message": "Registration cancelled. Refund processing is not implemented yet.", "item": item})


def member_event_attendees_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    event_id = (get_query_params(event).get("event_id") or "").strip()
    if not event_id:
        body = parse_body(event)
        event_id = str(body.get("event_id") or "")
    if not normalise_event_id(event_id):
        raise ValueError("event_id is required.")
    include_private = is_admin(claims)
    return response(200, {"items": list_event_attendees(event_id, include_private=include_private)})


def get_current_member_summary(claims: Dict[str, Any]) -> Dict[str, Any]:
    lookup = str(claims.get("sub") or claims.get("email") or claims.get("cognito:username") or "").strip()
    if lookup:
        try:
            return resolve_user_summary(lookup)
        except Exception:
            pass
    return {"sub": str(claims.get("sub") or ""), "email": str(claims.get("email") or ""), "name": str(claims.get("name") or claims.get("preferred_username") or claims.get("email") or ""), "callsign": str(claims.get("callsign") or ""), "display_callsign": str(claims.get("callsign") or ""), "committee_position_id": ""}


def sender_context_from_claims(claims: Dict[str, Any], from_position_id: str = "") -> Dict[str, Any]:
    groups = get_groups(claims)
    if not groups.intersection(EMAIL_AUTHOR_GROUPS):
        raise PermissionError("Only committee, admin, or webmaster users can send club email.")
    summary = get_current_member_summary(claims)
    position = get_club_position(summary.get("committee_position_id") or "")
    selected_position = get_club_position(from_position_id) if from_position_id else None
    sender_email = normalise_email_address(summary.get("email") or claims.get("email") or "")
    from_address = normalise_email_address((selected_position or {}).get("email_address") or sender_email or SES_FROM_EMAIL)
    if not valid_email_address(from_address):
        from_address = normalise_email_address(SES_FROM_EMAIL)
    position_name = str((position or {}).get("position_name") or "").strip()
    name = str(summary.get("name") or sender_email or "LROC").strip()
    callsign = ""
    signoff_name = name
    position_line = f"{position_name} LROC" if position_name else "LROC"
    return {"name": name, "callsign": callsign, "signoff_name": signoff_name, "position_line": position_line, "from_email": from_address, "reply_to": from_address}


def secretary_sender_context() -> Dict[str, Any]:
    positions = list_club_positions()
    secretary = next((p for p in positions if str(p.get("position_name") or "").strip().lower() == "secretary"), None)
    secretary_id = str((secretary or {}).get("position_id") or "secretary")
    member = None
    try:
        for item in list_member_summaries(""):
            if str(item.get("committee_position_id") or "") == secretary_id and str(item.get("account_status") or "active") != "deleted":
                member = item
                break
    except Exception:
        member = None
    from_address = normalise_email_address((secretary or {}).get("email_address") or SES_REPLY_TO_EMAIL or SES_FROM_EMAIL)
    name = str((member or {}).get("name") or "LROC Secretary").strip()
    callsign = ""
    signoff_name = name
    return {"name": name, "callsign": callsign, "signoff_name": signoff_name, "position_line": "Secretary LROC", "from_email": from_address, "reply_to": from_address}


def recipient_name(recipient: Dict[str, Any]) -> str:
    return str(recipient.get("name") or recipient.get("email") or "Member").strip()


def email_unsubscribe_text() -> str:
    address = clean_header_address(SES_REPLY_TO_EMAIL or f"secretary@{club_email_domain()}")
    return f"To unsubscribe from non-essential LROC emails, reply to this message or email {address} with UNSUBSCRIBE in the subject."


def wrap_member_email(subject: str, message: str, recipient: Dict[str, Any], sender: Dict[str, Any]) -> Dict[str, str]:
    subject = str(subject or "").strip()
    body = str(message or "").strip()
    if not subject:
        raise ValueError("Subject is required.")
    if not body:
        raise ValueError("Message body is required.")
    dear = recipient_name(recipient)
    signoff = f"73's,\n{sender.get('signoff_name') or 'LROC'}"
    position_line = str(sender.get("position_line") or "").strip()
    if position_line:
        signoff += f"\n{position_line}"
    unsubscribe = email_unsubscribe_text()
    text = f"Land Rover Owners Club of Australia Inc\n\nDear {dear},\n\n{body}\n\n{signoff}\n\n---\n{unsubscribe}\n"
    paras = "".join(f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in re.split(r"\n\s*\n", body) if part.strip())
    html_body = (
        '<div style="font-family:Arial,sans-serif;line-height:1.55;color:#111827">'
        '<div style="border-bottom:3px solid #7f1d1d;padding-bottom:12px;margin-bottom:18px">'
        '<strong style="font-size:18px;color:#7f1d1d">LROC</strong><br>'
        '<span>Land Rover Owners Club of Australia Inc</span>'
        '</div>'
        f'<p>Dear {html.escape(dear)},</p>'
        f'{paras}'
        f"<p>73's,<br>{html.escape(str(sender.get('signoff_name') or 'LROC'))}"
        + (f"<br>{html.escape(position_line)}" if position_line else "")
        + '</p><hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0">'
        f'<p style="font-size:12px;color:#6b7280">{html.escape(unsubscribe)}</p>'
        '</div>'
    )
    return {"subject": subject, "text": text, "html": html_body}

def chunked(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def public_url(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return SITE_BASE_URL or ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if SITE_BASE_URL:
        return f"{SITE_BASE_URL}/{raw.lstrip('/')}"
    return raw if raw.startswith("/") else f"/{raw}"


def format_chat_member_label(name: str, callsign: str) -> str:
    clean_name = str(name or "").strip()
    clean_callsign = str(callsign or "").strip()
    if clean_name and clean_callsign:
        return f"{clean_name} ({clean_callsign})"
    return clean_name or clean_callsign or ""


def resolve_uploader_display(claims: Dict[str, Any]) -> tuple[str, str]:
    uploader_id = str(claims.get("sub") or claims.get("email") or claims.get("cognito:username") or "member").strip()
    display_name = ""
    if uploader_id and uploader_id != "member":
        try:
            summary = resolve_user_summary(uploader_id)
            display_name = format_chat_member_label(
                summary.get("name") or summary.get("preferred_username") or summary.get("email") or summary.get("cognito_username") or "",
                summary.get("display_callsign") or summary.get("callsign") or "",
            ) or str(summary.get("email") or "").strip()
        except Exception:
            display_name = ""
    if not display_name:
        display_name = format_chat_member_label(
            str(claims.get("name") or claims.get("preferred_username") or claims.get("cognito:username") or claims.get("email") or "").strip(),
            str(claims.get("callsign") or "").strip(),
        ) or (
            str(claims.get("name") or "").strip()
            or str(claims.get("preferred_username") or "").strip()
            or str(claims.get("cognito:username") or "").strip()
            or str(claims.get("email") or "").strip()
            or "LROC Member"
        )
    return uploader_id, display_name


# ---------------------------------------------------------------------------
# Article library, event info PDFs, and SES event reminders
# Ported/adapted from the working SGARS SES implementation and adjusted for
# LROC naming, event storage, and member metadata.
# ---------------------------------------------------------------------------

def article_slug(value: Any, fallback: str = "article") -> str:
    return event_slug(value, fallback)


def load_articles_manifest() -> Dict[str, Any]:
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    try:
        resp = s3.get_object(Bucket=SITE_BUCKET, Key=ARTICLES_MANIFEST_KEY)
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("articles"), list):
            return payload
    except ClientError as exc:
        error_code = (exc.response.get("Error") or {}).get("Code")
        if error_code not in {"NoSuchKey", "404", "NotFound"}:
            raise
    return {"articles": []}


def save_articles_manifest(manifest: Dict[str, Any]) -> None:
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    s3.put_object(
        Bucket=SITE_BUCKET,
        Key=ARTICLES_MANIFEST_KEY,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="no-store",
    )
    if SITE_DISTRIBUTION_ID:
        try:
            cloudfront.create_invalidation(
                DistributionId=SITE_DISTRIBUTION_ID,
                InvalidationBatch={
                    "Paths": {"Quantity": 2, "Items": [f"/{ARTICLES_MANIFEST_KEY}", "/articles.html"]},
                    "CallerReference": f"articles-{datetime.now(timezone.utc).timestamp()}",
                },
            )
        except Exception:
            pass


def normalise_article_visibility(value: Any = "", members_only: Any = None) -> str:
    text = str(value or "").strip().lower()
    if members_only is True or text in {"members", "member", "club", "club-members", "members-only", "private"}:
        return "members"
    return "public"


def article_is_members_only(item: Dict[str, Any]) -> bool:
    return normalise_article_visibility(item.get("visibility"), item.get("members_only")) == "members"


def article_storage_bucket_for_visibility(visibility: str) -> str:
    return BUCKET if normalise_article_visibility(visibility) == "members" else SITE_BUCKET


def article_prefix_for_visibility(visibility: str) -> str:
    return ARTICLES_MEMBER_PREFIX if normalise_article_visibility(visibility) == "members" else ARTICLES_PREFIX


def article_public_payload(item: Dict[str, Any], authenticated: bool = False) -> Dict[str, Any]:
    payload = enrich_article_entry(item)
    visibility = normalise_article_visibility(payload.get("visibility"), payload.get("members_only"))
    payload["visibility"] = visibility
    payload["members_only"] = visibility == "members"
    if visibility == "members" and not authenticated:
        payload.pop("url", None)
        payload.pop("key", None)
    return payload


def load_magazines_manifest() -> Dict[str, Any]:
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    try:
        resp = s3.get_object(Bucket=SITE_BUCKET, Key=MAGAZINES_MANIFEST_KEY)
        payload = json.loads(resp["Body"].read().decode("utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("magazines"), list):
            return payload
    except ClientError as exc:
        error_code = (exc.response.get("Error") or {}).get("Code")
        if error_code not in {"NoSuchKey", "404", "NotFound"}:
            raise
    return {"magazines": []}


def save_magazines_manifest(manifest: Dict[str, Any]) -> None:
    s3.put_object(Bucket=SITE_BUCKET, Key=MAGAZINES_MANIFEST_KEY, Body=json.dumps(manifest, indent=2).encode("utf-8"), ContentType="application/json; charset=utf-8", CacheControl="no-store")
    if SITE_DISTRIBUTION_ID:
        try:
            cloudfront.create_invalidation(DistributionId=SITE_DISTRIBUTION_ID, InvalidationBatch={"Paths": {"Quantity": 2, "Items": [f"/{MAGAZINES_MANIFEST_KEY}", "/magazines.html"]}, "CallerReference": f"magazines-{datetime.now(timezone.utc).timestamp()}"})
        except Exception:
            pass


def list_public_magazines() -> Dict[str, Any]:
    manifest = load_magazines_manifest()
    items = [item for item in manifest.get("magazines") or [] if isinstance(item, dict)]
    items.sort(key=lambda item: str(item.get("published_at") or item.get("uploaded_at") or ""), reverse=True)
    return response(200, {"items": items, "magazines": items})


def require_magazine_upload_role(claims: Dict[str, Any]) -> None:
    boxes = webmail_accessible_mailboxes(claims)
    has_role = any(bool(box.get("owned") or box.get("preferred")) for box in boxes)
    if not (has_role or is_admin(claims)):
        raise PermissionError("A club role is required to upload magazines.")


def create_magazine_upload_url(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_magazine_upload_role(claims)
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    body = parse_body(event)
    title = str(body.get("title") or "").strip()
    filename = webmail_attachment_safe_name(body.get("filename") or "magazine.pdf")
    content_type = str(body.get("content_type") or "application/pdf").strip().lower()
    if not title:
        raise ValueError("title is required.")
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF magazine files are supported for direct upload.")
    if content_type not in {"application/pdf", "application/x-pdf"}:
        raise ValueError("Only PDF magazine files are supported for direct upload.")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    key = f"{MAGAZINES_PREFIX}{article_slug(title)}-{timestamp}-{secrets.token_hex(3)}.pdf"
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": SITE_BUCKET, "Key": key, "ContentType": "application/pdf"},
        ExpiresIn=UPLOAD_EXPIRY,
    )
    return response(200, {"upload_url": url, "key": key, "title": title, "public_url": f"/{key}"})


def publish_magazine_upload(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_magazine_upload_role(claims)
    body = parse_body(event)
    title = str(body.get("title") or "").strip()
    key = str(body.get("key") or "").strip()
    if not title:
        raise ValueError("title is required.")
    if not key.startswith(MAGAZINES_PREFIX) or not key.lower().endswith(".pdf"):
        raise ValueError("A valid magazine PDF key is required.")
    try:
        s3.head_object(Bucket=SITE_BUCKET, Key=key)
    except ClientError as exc:
        raise ValueError("Uploaded magazine PDF was not found.") from exc
    uploader_email = webmail_member_contact_email(claims) or str(claims.get("email") or "")
    entry = save_magazine_entry(title, key.rsplit("/", 1)[-1], key, uploader_email, "upload", "")
    return response(200, {"message": "Magazine uploaded.", "item": entry})


def enrich_article_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(item)
    uploader_name = str(enriched.get("uploaded_by_name") or "").strip()
    uploader_id = str(enriched.get("uploaded_by") or "").strip()
    if not uploader_name and uploader_id:
        try:
            summary = resolve_user_summary(uploader_id)
            uploader_name = str(
                summary.get("name")
                or summary.get("preferred_username")
                or summary.get("email")
                or summary.get("cognito_username")
                or ""
            ).strip()
        except Exception:
            uploader_name = ""
    if uploader_name:
        enriched["uploaded_by_name"] = uploader_name
    return enriched


def list_public_articles() -> Dict[str, Any]:
    manifest = load_articles_manifest()
    raw_items = [item for item in (manifest.get("articles") or []) if isinstance(item, dict)]
    items = [article_public_payload(item, authenticated=False) for item in raw_items if not article_is_members_only(item)]
    items.sort(key=lambda item: str(item.get("uploaded_at") or ""), reverse=True)
    return response(200, {"items": items, "articles": items})


def list_member_articles(_event: Dict[str, Any], _claims: Dict[str, Any]) -> Dict[str, Any]:
    manifest = load_articles_manifest()
    items = [article_public_payload(item, authenticated=True) for item in (manifest.get("articles") or []) if isinstance(item, dict)]
    items.sort(key=lambda item: str(item.get("uploaded_at") or ""), reverse=True)
    return response(200, {"items": items, "articles": items})


def create_article_upload_url(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    title = str(body.get("title") or "").strip()
    filename = str(body.get("filename") or "").strip()
    content_type = str(body.get("content_type") or "application/pdf").strip().lower()
    visibility = normalise_article_visibility(body.get("visibility") or body.get("audience"), body.get("members_only"))
    if not title:
        raise ValueError("title is required.")
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")
    if content_type not in {"application/pdf", "application/x-pdf"}:
        raise ValueError("Only PDF files are supported.")
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    slug = article_slug(title)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    key = f"{article_prefix_for_visibility(visibility)}{slug}-{timestamp}.pdf"
    bucket = article_storage_bucket_for_visibility(visibility)
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": "application/pdf"},
        ExpiresIn=UPLOAD_EXPIRY,
    )
    return response(200, {"upload_url": url, "key": key, "public_url": f"/{key}" if visibility == "public" else "", "title": title, "visibility": visibility, "members_only": visibility == "members"})


def send_article_notification_email(entry: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_ARTICLE_NOTIFICATIONS:
        return {"enabled": False, "sent": 0, "total": 0, "skipped": True, "reason": "disabled"}
    recipients = list_active_member_recipients()
    if not recipients:
        return {"enabled": True, "sent": 0, "total": 0, "skipped": True, "reason": "no_recipients"}
    article_title = str(entry.get("title") or "New article").strip() or "New article"
    uploader = str(entry.get("uploaded_by_name") or "LROC Member").strip() or "LROC Member"
    article_link = public_url(entry.get("url") or "")
    library_link = public_url("articles.html")
    subject = f"New LROC article: {article_title}"
    body = (
        f"A new LROC article has been published.\n\n"
        f"Title: {article_title}\n"
        f"Uploaded by: {uploader}\n\n"
        f"Read the article: {article_link or library_link}\n"
        f"Articles library: {library_link}"
    )
    filtered = filter_sendable_recipients(recipients, apply_system_guard=True, context="article_notification")
    sender = secretary_sender_context()
    sent = 0
    message_ids: List[str] = []
    for recipient in filtered["sendable"]:
        mail = wrap_member_email(subject, body, recipient, sender)
        result = send_email_via_ses(
            [recipient["email"]],
            mail["subject"],
            mail["text"],
            mail["html"],
            from_email=sender.get("from_email"),
            reply_to=sender.get("reply_to"),
        )
        sent += 1
        if result.get("MessageId"):
            message_ids.append(str(result.get("MessageId")))
    return {
        "enabled": True,
        "email_guard": system_email_guard_summary(),
        "sent": sent,
        "total": len(filtered["sendable"]),
        "skipped_suppressed": len([x for x in filtered["skipped"] if x.get("reason") not in {"system_email_test_mode", "no_cognito_presence", "system_email_mode_off"}]),
        "skipped_email_guard": len([x for x in filtered["skipped"] if x.get("reason") in {"system_email_test_mode", "no_cognito_presence", "system_email_mode_off"}]),
        "message_ids": message_ids,
    }


def publish_article(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    title = str(body.get("title") or "").strip()
    key = str(body.get("key") or "").strip()
    visibility = normalise_article_visibility(body.get("visibility") or body.get("audience"), body.get("members_only"))
    prefix = article_prefix_for_visibility(visibility)
    bucket = article_storage_bucket_for_visibility(visibility)
    if not title:
        raise ValueError("title is required.")
    if not key.startswith(prefix) or not key.lower().endswith(".pdf"):
        raise ValueError("A valid article PDF key is required.")
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        raise ValueError("Uploaded article PDF not found in the site bucket.") from exc
    manifest = load_articles_manifest()
    items = [item for item in manifest.get("articles") or [] if isinstance(item, dict)]
    article_id = article_slug(f"{title}-{key.rsplit('/', 1)[-1].replace('.pdf', '')}")
    uploader_id, display_name = resolve_uploader_display(claims)
    entry = {
        "id": article_id,
        "title": title,
        "filename": key.rsplit("/", 1)[-1],
        "key": key,
        "url": f"/{key}" if visibility == "public" else "",
        "visibility": visibility,
        "members_only": visibility == "members",
        "uploaded_at": utc_now(),
        "uploaded_by": uploader_id,
        "uploaded_by_name": display_name,
    }
    items = [item for item in items if str(item.get("id") or "") != article_id]
    items.insert(0, entry)
    manifest["articles"] = items
    save_articles_manifest(manifest)
    try:
        notification = send_article_notification_email(entry)
    except Exception as exc:
        notification = {"enabled": ENABLE_ARTICLE_NOTIFICATIONS, "sent": 0, "total": 0, "error": str(exc)}
    return response(200, {"message": "Article published.", "item": entry, "notification": notification})


def article_download_url_route(event: Dict[str, Any], _claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    article_id = str(body.get("id") or "").strip()
    key = str(body.get("key") or "").strip()
    manifest = load_articles_manifest()
    found = None
    for item in manifest.get("articles") or []:
        if not isinstance(item, dict):
            continue
        if (article_id and str(item.get("id") or "") == article_id) or (key and str(item.get("key") or "") == key):
            found = item
            break
    if not found:
        raise ValueError("Article not found.")
    object_key = str(found.get("key") or "").strip()
    visibility = normalise_article_visibility(found.get("visibility"), found.get("members_only"))
    bucket = article_storage_bucket_for_visibility(visibility)
    if visibility != "members" or not object_key.startswith(ARTICLES_MEMBER_PREFIX):
        return response(200, {"url": found.get("url") or f"/{object_key}", "public": True})
    filename = webmail_attachment_safe_name(found.get("filename") or object_key.rsplit("/", 1)[-1] or "article.pdf")
    url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": object_key, "ResponseContentDisposition": f'inline; filename="{filename}"'}, ExpiresIn=DOWNLOAD_EXPIRY)
    return response(200, {"url": url, "public": False})


def delete_article(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    article_id = str(body.get("id") or "").strip()
    key = str(body.get("key") or "").strip()
    if not article_id and not key:
        raise ValueError("Article id or key is required.")
    manifest = load_articles_manifest()
    items = [item for item in manifest.get("articles") or [] if isinstance(item, dict)]
    removed = None
    kept = []
    for item in items:
        item_id = str(item.get("id") or "").strip()
        item_key = str(item.get("key") or "").strip()
        if removed is None and ((article_id and item_id == article_id) or (key and item_key == key)):
            removed = item
            continue
        kept.append(item)
    if not removed:
        raise ValueError("Article not found.")
    object_key = str(removed.get("key") or "").strip()
    if object_key.startswith(ARTICLES_PREFIX) or object_key.startswith(ARTICLES_MEMBER_PREFIX):
        try:
            s3.delete_object(Bucket=article_storage_bucket_for_visibility(normalise_article_visibility(removed.get("visibility"), removed.get("members_only"))), Key=object_key)
        except ClientError:
            pass
    manifest["articles"] = kept
    save_articles_manifest(manifest)
    return response(200, {"message": "Article deleted.", "removed": removed})


def create_event_info_upload_url(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    title = str(body.get("title") or "").strip()
    filename = str(body.get("filename") or "").strip()
    content_type = str(body.get("content_type") or "application/pdf").strip().lower()
    if not title:
        raise ValueError("title is required.")
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")
    if content_type not in {"application/pdf", "application/x-pdf"}:
        raise ValueError("Only PDF files are supported.")
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    slug = event_slug(title, fallback="event-info")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    key = f"{EVENTS_PDF_PREFIX}{slug}-{timestamp}.pdf"
    uploader_id, display_name = resolve_uploader_display(claims)
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": SITE_BUCKET, "Key": key, "ContentType": "application/pdf"},
        ExpiresIn=UPLOAD_EXPIRY,
    )
    return response(200, {
        "upload_url": url,
        "key": key,
        "public_url": f"/{key}",
        "url": f"/{key}",
        "title": f"{title} information",
        "filename": key.rsplit("/", 1)[-1],
        "uploaded_at": utc_now(),
        "uploaded_by": uploader_id,
        "uploaded_by_name": display_name,
    })


def delete_event_info(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    key = str(body.get("key") or "").strip()
    if not key.startswith(EVENTS_PDF_PREFIX) or not key.lower().endswith(".pdf"):
        raise ValueError("A valid event PDF key is required.")
    try:
        s3.delete_object(Bucket=SITE_BUCKET, Key=key)
    except ClientError:
        pass
    return response(200, {"message": "Event info PDF deleted.", "key": key})


def event_reminder_state_key(event_id: str, event_date: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": f"EVENT#{event_id}"}, "sk": {"S": f"REMINDER#{event_date}"}}


def event_reminder_already_sent(event_id: str, event_date: str) -> bool:
    require_email_state_table()
    resp = ddb.get_item(TableName=EMAIL_STATE_TABLE, Key=event_reminder_state_key(event_id, event_date), ConsistentRead=True)
    return bool(resp.get("Item"))


def mark_event_reminder_sent(event_row: Dict[str, Any], event_date: str, recipient_count: int, triggered_by: str) -> None:
    require_email_state_table()
    event_id = str(event_row.get("event_id") or "").strip()
    ddb.put_item(
        TableName=EMAIL_STATE_TABLE,
        Item={
            "pk": {"S": f"EVENT#{event_id}"},
            "sk": {"S": f"REMINDER#{event_date}"},
            "event_id": {"S": event_id},
            "event_date": {"S": event_date},
            "event_name": {"S": str(event_row.get("trip_name") or "")},
            "sent_at": {"S": utc_now()},
            "recipient_count": {"N": str(recipient_count)},
            "triggered_by": {"S": str(triggered_by or "scheduler")},
        },
    )


def event_reminder_date(event_row: Dict[str, Any]) -> Any:
    return parse_event_date_value(event_row.get("date_from") or event_row.get("start_at") or event_row.get("date"))


def format_event_reminder_datetime(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Date to be advised"
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw.split("+", 1)[0], fmt)
            if "T" in raw:
                return dt.strftime("%A %d %b %Y, %I:%M %p").replace(" 0", " ").replace("AM", "am").replace("PM", "pm")
            return dt.strftime("%A %d %b %Y")
        except ValueError:
            continue
    parsed = parse_event_date_value(raw)
    if parsed:
        return parsed.strftime("%A %d %b %Y")
    return raw


def event_location_text(event_row: Dict[str, Any]) -> str:
    loc = event_row.get("meeting_location") if isinstance(event_row.get("meeting_location"), dict) else {}
    parts = [
        str(loc.get("name") or "").strip(),
        str(loc.get("address") or loc.get("label") or "").strip(),
    ]
    text = ", ".join(part for part in parts if part)
    return text or "To be advised"


def build_event_reminder_message(event_row: Dict[str, Any]) -> Dict[str, str]:
    title = str(event_row.get("trip_name") or "Club event").strip() or "Club event"
    date_text = format_event_reminder_datetime(event_row.get("date_from") or event_row.get("date"))
    location = event_location_text(event_row)
    details = str(event_row.get("blurb") or "").strip()
    events_link = public_url("events.html")
    event_chat_link = public_url(f"chat.html?room={event_row.get('chat_room_id')}") if event_row.get("chat_room_id") else ""
    subject = f"LROC reminder: {title} on {date_text}"
    text_parts = [
        f"This is a reminder that the following LROC trip/event is coming up in {EVENT_REMINDER_LOOKAHEAD_DAYS} days.",
        "",
        f"Event: {title}",
        f"Date/time: {date_text}",
        f"Location: {location}",
    ]
    if details:
        text_parts.extend(["", details])
    text_parts.extend(["", f"Events page: {events_link or 'events.html'}"])
    if event_chat_link:
        text_parts.append(f"Event chat: {event_chat_link}")
    html_body = (
        f"<p>This is a reminder that the following LROC trip/event is coming up in {EVENT_REMINDER_LOOKAHEAD_DAYS} days.</p>"
        f"<p><strong>Event:</strong> {html.escape(title)}<br>"
        f"<strong>Date/time:</strong> {html.escape(date_text)}<br>"
        f"<strong>Location:</strong> {html.escape(location)}</p>"
    )
    if details:
        html_body += "".join(f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in re.split(r"\n\s*\n", details) if part.strip())
    html_body += f"<p><a href=\"{html.escape(events_link)}\">Open the Events page</a></p>"
    if event_chat_link:
        html_body += f"<p><a href=\"{html.escape(event_chat_link)}\">Open the event chat</a></p>"
    return {"subject": subject, "text": "\n".join(text_parts), "html": html_body}


def run_event_reminder_scan(*, target_date: str | None = None, days_ahead: int | None = None, dry_run: bool = False, triggered_by: str = "scheduler") -> Dict[str, Any]:
    recipients = list_active_member_recipients()
    filtered = filter_sendable_recipients(recipients, apply_system_guard=True, context="event_reminder")
    emails: List[str] = [item["email"] for item in filtered["sendable"]]
    if target_date:
        target = datetime.strptime(str(target_date), "%Y-%m-%d").date()
    else:
        local_now = datetime.now(ZoneInfo(CLUB_TIME_ZONE))
        target = local_now.date() + timedelta(days=(days_ahead if days_ahead is not None else EVENT_REMINDER_LOOKAHEAD_DAYS))
    target_iso = target.isoformat()
    events: List[Dict[str, Any]] = []
    for row in list_trip_events(admin=False):
        row_date = event_reminder_date(row)
        if row_date and row_date.isoformat() == target_iso:
            events.append(row)
    summary: Dict[str, Any] = {
        "enabled": ENABLE_EVENT_REMINDERS,
        "email_guard": system_email_guard_summary(),
        "dry_run": dry_run,
        "target_date": target_iso,
        "recipient_total": len(emails),
        "skipped_suppressed": len([x for x in filtered["skipped"] if x.get("reason") not in {"system_email_test_mode", "no_cognito_presence", "system_email_mode_off"}]),
        "skipped_email_guard": len([x for x in filtered["skipped"] if x.get("reason") in {"system_email_test_mode", "no_cognito_presence", "system_email_mode_off"}]),
        "matching_events": [],
        "sent_events": 0,
        "sent_recipients": 0,
        "skipped_existing": 0,
    }
    if not events:
        summary["message"] = "No matching events found for the reminder date."
        return summary
    for row in events:
        event_id = str(row.get("event_id") or "").strip()
        if not event_id:
            continue
        already_sent = event_reminder_already_sent(event_id, target_iso)
        event_summary = {
            "event_id": event_id,
            "event": str(row.get("trip_name") or "").strip(),
            "date": target_iso,
            "already_sent": already_sent,
        }
        if already_sent:
            summary["skipped_existing"] += 1
            summary["matching_events"].append(event_summary)
            continue
        if dry_run or not ENABLE_EVENT_REMINDERS:
            event_summary["would_send_to"] = len(emails)
            summary["matching_events"].append(event_summary)
            continue
        if not emails:
            event_summary["would_send_to"] = 0
            summary["matching_events"].append(event_summary)
            continue
        message = build_event_reminder_message(row)
        sender = secretary_sender_context()
        message_ids: List[str] = []
        for recipient in filtered["sendable"]:
            mail = wrap_member_email(message["subject"], message["text"], recipient, sender)
            result = send_email_via_ses(
                [recipient["email"]],
                mail["subject"],
                mail["text"],
                mail["html"],
                from_email=sender.get("from_email"),
                reply_to=sender.get("reply_to"),
            )
            if result.get("MessageId"):
                message_ids.append(str(result.get("MessageId")))
        mark_event_reminder_sent(row, target_iso, len(emails), triggered_by)
        event_summary["message_ids"] = message_ids
        event_summary["sent_to"] = len(emails)
        summary["sent_events"] += 1
        summary["sent_recipients"] += len(emails)
        summary["matching_events"].append(event_summary)
    if not ENABLE_EVENT_REMINDERS and not dry_run:
        summary["message"] = "Event reminders are currently disabled."
    return summary


def run_event_reminders_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    target_date = str(body.get("target_date") or "").strip() or None
    days_ahead_raw = body.get("days_ahead")
    days_ahead = None if days_ahead_raw in {None, ""} else int(days_ahead_raw)
    dry_run = bool(body.get("dry_run", not ENABLE_EVENT_REMINDERS))
    summary = run_event_reminder_scan(
        target_date=target_date,
        days_ahead=days_ahead,
        dry_run=dry_run,
        triggered_by=claims.get("email") or claims.get("sub") or "admin",
    )
    return response(200, summary)


def run_vehicle_registration_reminders_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    summary = run_vehicle_registration_reminder_scan(
        triggered_by=claims.get("email") or claims.get("sub") or "admin",
    )
    return response(200, summary)


def member_pk(sub: str) -> str:
    return f"MEMBER#{sub}"


def meta_key(sub: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": member_pk(sub)}, "sk": {"S": "PROFILE"}}


def from_ddb_attr(value: Dict[str, Any]) -> Any:
    if "S" in value:
        return value["S"]
    if "N" in value:
        n = value["N"]
        return int(n) if n.isdigit() else float(n)
    if "BOOL" in value:
        return bool(value["BOOL"])
    if "NULL" in value:
        return None
    if "L" in value:
        return [from_ddb_attr(v) for v in value["L"]]
    if "M" in value:
        return {k: from_ddb_attr(v) for k, v in value["M"].items()}
    return None


def item_to_python(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: from_ddb_attr(v) for k, v in item.items()}


def to_ddb_attr(value: Any) -> Dict[str, Any]:
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"N": str(value)}
    if isinstance(value, list):
        return {"L": [to_ddb_attr(item) for item in value]}
    if isinstance(value, dict):
        return {"M": {str(k): to_ddb_attr(v) for k, v in value.items()}}
    return {"S": str(value)}


def python_to_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k): to_ddb_attr(v) for k, v in item.items()}


def parse_other_callsigns(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value).replace(";", "\n").replace(",", "\n")
        raw_items = text.splitlines()
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        callsign = str(item or "").strip()
        if not callsign:
            continue
        key = callsign.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(callsign[:32])
    return cleaned[:12]


def normalise_text_list(value: Any, *, max_items: int = 20, max_len: int = 120) -> List[str]:
    if value is None:
        raw_items: List[Any] = []
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[,;|\n]", str(value or ""))
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = re.sub(r"\s+", " ", str(item or "").strip())[:max_len]
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= max_items:
            break
    return cleaned


def first_present(meta: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = meta.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def merge_non_empty_metadata(summary: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Merge DynamoDB metadata into a Cognito summary without blanking Cognito fields.

    Restored/legacy metadata records can be sparse.  The previous admin list
    used summary.update(metadata), so an empty metadata email/name/member number
    could hide the Cognito email/name in Site Admin.  Only non-empty metadata
    values should override the Cognito summary.
    """
    merged = dict(summary)
    for key, value in (metadata or {}).items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def normalise_membership_metadata(item: Dict[str, Any] | None) -> Dict[str, Any]:
    meta = dict(item or {})
    membership_type = str(first_present(meta, "membership_type", "membershipType") or "").strip().lower()
    membership_status = str(first_present(meta, "membership_status", "membershipStatus", "status") or "").strip().lower()
    membership_expiry = str(first_present(meta, "membership_expiry", "membershipExpiry") or "").strip()
    other_callsigns = parse_other_callsigns(first_present(meta, "other_callsigns", "otherCallsigns"))
    account_status = str(first_present(meta, "account_status", "accountStatus") or "active").strip().lower() or "active"
    if membership_type == "life":
        membership_status = "life"
        membership_expiry = ""
    invited = meta.get("invited")
    if "invited" not in meta:
        invited_value = ""
    elif isinstance(invited, bool):
        invited_value = "Y" if invited else "N"
    else:
        invited_text = str(invited or "").strip().upper()
        invited_value = "Y" if invited_text in {"Y", "YES", "TRUE", "1"} else "N"
    club_roles = normalise_text_list(meta.get("club_roles"), max_items=30, max_len=120)
    system_roles = normalise_text_list(first_present(meta, "system_roles", "member_system_roles"), max_items=12, max_len=80)
    assigned_role_ids = [normalise_position_id(x) for x in normalise_text_list(first_present(meta, "assigned_role_ids", "assignedRoleIds"), max_items=20, max_len=80)]
    assigned_role_ids = [x for x in assigned_role_ids if x]
    assigned_role_names = normalise_text_list(first_present(meta, "assigned_role_names", "assignedRoleNames"), max_items=20, max_len=160)
    committee_position_id = normalise_position_id(first_present(meta, "committee_position_id", "official_position_id", "club_position_id") or "")
    committee_position_name = str(first_present(meta, "committee_position_name", "official_position_name", "club_position_name") or "").strip()
    display_name = str(first_present(meta, "name", "Name") or "").strip()
    if not display_name:
        display_name = " ".join([
            str(first_present(meta, "first_name", "firstName", "Firstname") or "").strip(),
            str(first_present(meta, "last_name", "lastName", "Lastname") or "").strip(),
        ]).strip()
    return {
        "membership_type": membership_type,
        "membership_status": membership_status,
        "membership_expiry": membership_expiry,
        "other_callsigns": other_callsigns,
        "account_status": account_status,
        "committee_position_id": committee_position_id,
        "committee_position_name": committee_position_name,
        "official_position_id": committee_position_id,
        "official_position_name": committee_position_name,
        "assigned_role_ids": assigned_role_ids,
        "assigned_role_names": assigned_role_names,
        "system_roles": system_roles,
        "deleted_at": str(meta.get("deleted_at") or "").strip(),
        "deleted_by": str(meta.get("deleted_by") or "").strip(),
        "site_member_id": str(first_present(meta, "site_member_id", "member_number", "SiteMemberId", "siteMemberId", "memberNumber", "MemberNumber") or "").strip(),
        "member_number": str(first_present(meta, "member_number", "site_member_id", "memberNumber", "MemberNumber", "SiteMemberId", "siteMemberId") or "").strip(),
        "first_name": str(first_present(meta, "first_name", "firstName", "Firstname", "given_name") or "").strip(),
        "middle_name": str(first_present(meta, "middle_name", "middleName") or "").strip(),
        "last_name": str(first_present(meta, "last_name", "lastName", "Lastname", "family_name") or "").strip(),
        "title": str(meta.get("title") or "").strip(),
        "email": str(first_present(meta, "email", "Email") or "").strip().lower(),
        "email_raw": str(first_present(meta, "email_raw", "emailRaw", "Email") or "").strip(),
        "email_usable": bool(meta.get("email_usable")) if isinstance(meta.get("email_usable"), bool) else str(meta.get("email_usable") or "").strip().upper() in {"Y", "YES", "TRUE", "1"},
        "invite_eligible": bool(meta.get("invite_eligible")) if isinstance(meta.get("invite_eligible"), bool) else str(meta.get("invite_eligible") or "").strip().upper() in {"Y", "YES", "TRUE", "1"},
        "username": str(first_present(meta, "username", "Username") or "").strip(),
        "name": display_name,
        "phone_number": str(first_present(meta, "phone_number", "phoneNumber") or "").strip(),
        "mobile": str(first_present(meta, "mobile", "Mobile") or "").strip(),
        "phone": str(first_present(meta, "phone", "Phone") or "").strip(),
        "gender": str(meta.get("gender") or "").strip(),
        "date_of_birth_raw": str(meta.get("date_of_birth_raw") or "").strip(),
        "date_of_birth": str(meta.get("date_of_birth") or "").strip(),
        "company_name": str(meta.get("company_name") or "").strip(),
        "membership_level": str(meta.get("membership_level") or "").strip(),
        "membership_product": str(meta.get("membership_product") or "").strip(),
        "current_full_product_name": str(meta.get("current_full_product_name") or "").strip(),
        "join_date_raw": str(meta.get("join_date_raw") or "").strip(),
        "join_date": str(meta.get("join_date") or "").strip(),
        "expiry_date_raw": str(meta.get("expiry_date_raw") or "").strip(),
        "expiry_date": str(meta.get("expiry_date") or "").strip(),
        "card_number": str(first_present(meta, "card_number", "cardNumber") or "").strip(),
        "party_id": str(first_present(meta, "party_id", "partyId", "UID", "uid") or "").strip(),
        "member_type": str(meta.get("member_type") or "").strip(),
        "primary_first_name": str(meta.get("primary_first_name") or "").strip(),
        "primary_last_name": str(meta.get("primary_last_name") or "").strip(),
        "primary_member_number": str(meta.get("primary_member_number") or "").strip(),
        "profile_image": str(meta.get("profile_image") or "").strip(),
        "avatar_data_url": normalise_avatar_data_url(meta.get("avatar_data_url")),
        "ice_name": str(meta.get("ice_name") or "").strip(),
        "ice_phone_number": str(meta.get("ice_phone_number") or "").strip(),
        "ice_phone_raw": str(meta.get("ice_phone_raw") or "").strip(),
        "dietary_requirements_allergies": str(meta.get("dietary_requirements_allergies") or "").strip(),
        "address1": str(meta.get("address1") or "").strip(),
        "address2": str(meta.get("address2") or "").strip(),
        "city": str(meta.get("city") or "").strip(),
        "state": str(meta.get("state") or "").strip(),
        "country": str(meta.get("country") or "").strip(),
        "postcode": str(meta.get("postcode") or "").strip(),
        "postal_address1": str(meta.get("postal_address1") or "").strip(),
        "postal_address2": str(meta.get("postal_address2") or "").strip(),
        "postal_city": str(meta.get("postal_city") or "").strip(),
        "postal_state": str(meta.get("postal_state") or "").strip(),
        "postal_country": str(meta.get("postal_country") or "").strip(),
        "postal_postcode": str(meta.get("postal_postcode") or "").strip(),
        "printed_magazine": normalise_printed_magazine(first_present(
            meta,
            "printed_magazine",
            "printedMagazine",
            "printed_magazine_raw",
            "do you want to receive a printed copy of the magazine?",
        )),
        "club_roles_raw": str(first_present(meta, "club_roles_raw", "clubRolesRaw", "rolesRaw", "Roles") or "").strip(),
        "club_roles": [str(x).strip() for x in club_roles if str(x).strip()],
        "member_created_date_raw": str(first_present(meta, "member_created_date_raw", "memberCreatedDateRaw", "CreatedDate") or "").strip(),
        "member_created_date": str(first_present(meta, "member_created_date", "memberCreatedDate", "CreatedDate") or "").strip(),
        "activated": bool(meta.get("activated")) if isinstance(meta.get("activated"), bool) else str(meta.get("activated") or "").strip().upper() == "Y",
        "imported_member": bool(meta.get("imported_member")),
        "import_batch_id": str(meta.get("import_batch_id") or "").strip(),
        "imported_at": str(meta.get("imported_at") or "").strip(),
        "imported_by": str(meta.get("imported_by") or "").strip(),
        "import_source": str(meta.get("import_source") or "").strip(),
        "invited": invited_value,
        "invite_sent_at": str(meta.get("invite_sent_at") or "").strip(),
        "invite_sent_by": str(meta.get("invite_sent_by") or "").strip(),
        "invite_batch_id": str(meta.get("invite_batch_id") or "").strip(),
        "cognito_sub": str(meta.get("cognito_sub") or "").strip(),
        "cognito_username": str(meta.get("cognito_username") or "").strip(),
    }


def get_member_metadata(sub: str) -> Dict[str, Any]:
    require_metadata_table()
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=meta_key(sub), ConsistentRead=True)
    item = item_to_python(resp.get("Item", {})) if resp.get("Item") else {}
    return normalise_membership_metadata(item)


def normalise_avatar_data_url(value: Any, *, strict: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 90000:
        if strict:
            raise ValueError("Avatar image is too large after resizing.")
        return ""
    if not re.match(r"^data:image/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+$", text, re.I):
        if strict:
            raise ValueError("Avatar must be a resized PNG, JPEG, or WebP data image.")
        return ""
    return text


def validate_profile_preferences_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """Validate member-editable profile fields.

    This deliberately excludes system/club-managed fields such as member_number,
    card_number, membership_level/status/product/expiry, Cognito role/group
    fields, invite flags, and import metadata. Members can maintain their
    contact/address/profile details without changing membership authority data.
    """
    first_name, middle_name, last_name, _name_warnings = normalise_import_member_names(
        str(body.get("first_name") or ""),
        str(body.get("middle_name") or ""),
        str(body.get("last_name") or ""),
    )
    mobile, phone, _phone_warnings = normalise_member_contact_numbers(str(body.get("mobile") or ""), str(body.get("phone") or body.get("phone_number") or ""))
    ice_phone, _ice_bucket, _ice_warnings = normalise_import_phone_number(str(body.get("ice_phone_number") or ""))

    printed_magazine = normalise_printed_magazine(body.get("printed_magazine"))

    payload = {
        "title": clean_text_field(body.get("title"), 40),
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "name": clean_text_field(body.get("name"), 240),
        "username": clean_text_field(body.get("username"), 160),
        "gender": clean_text_field(body.get("gender"), 40),
        "date_of_birth_raw": clean_text_field(body.get("date_of_birth_raw") or body.get("date_of_birth"), 40),
        "date_of_birth": clean_text_field(body.get("date_of_birth"), 20),
        "company_name": clean_text_field(body.get("company_name"), 240),
        "mobile": mobile,
        "phone": phone,
        "phone_number": mobile or phone,
        "address1": clean_text_field(body.get("address1"), 240),
        "address2": clean_text_field(body.get("address2"), 240),
        "city": clean_text_field(body.get("city"), 120),
        "state": clean_text_field(body.get("state"), 80),
        "country": clean_text_field(body.get("country"), 120),
        "postcode": clean_text_field(body.get("postcode"), 20),
        "postal_address1": clean_text_field(body.get("postal_address1"), 240),
        "postal_address2": clean_text_field(body.get("postal_address2"), 240),
        "postal_city": clean_text_field(body.get("postal_city"), 120),
        "postal_state": clean_text_field(body.get("postal_state"), 80),
        "postal_country": clean_text_field(body.get("postal_country"), 120),
        "postal_postcode": clean_text_field(body.get("postal_postcode"), 20),
        "profile_image": clean_text_field(body.get("profile_image"), 1000),
        "ice_name": clean_text_field(body.get("ice_name"), 160),
        "ice_phone_raw": clean_text_field(body.get("ice_phone_number"), 80),
        "ice_phone_number": ice_phone,
        "dietary_requirements_allergies": clean_multiline_field(body.get("dietary_requirements_allergies"), 2000),
        "printed_magazine": printed_magazine,
    }

    if "email" in body:
        email, email_usable, invite_eligible, _email_warnings = validate_admin_email_for_invite(body.get("email"))
        payload["email"] = email
        payload["email_raw"] = clean_text_field(body.get("email"), 320)
        payload["email_usable"] = email_usable
        payload["invite_eligible"] = invite_eligible
    if "avatar_data_url" in body:
        payload["avatar_data_url"] = normalise_avatar_data_url(body.get("avatar_data_url"), strict=True)

    return {k: v for k, v in payload.items() if v not in (None, [], {})}


def validate_membership_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    allowed_types = {"", "standard", "life"}
    allowed_statuses = {"", "financial", "due", "lapsed", "life", "active", "current", "expired", "cancelled", "inactive", "pending", "pending_payment"}
    membership_type = str(body.get("membership_type") or "").strip().lower()
    membership_status = str(body.get("membership_status") or "").strip().lower()
    membership_expiry = str(body.get("membership_expiry") or "").strip()
    if membership_type not in allowed_types:
        raise ValueError("membership_type must be standard, life, or blank.")
    if membership_status not in allowed_statuses:
        raise ValueError("membership_status must be current, expired, pending_payment, financial, due, lapsed, life, active, cancelled, inactive, or blank.")
    if membership_expiry and not re.match(r"^\d{4}-\d{2}-\d{2}$", membership_expiry):
        raise ValueError("membership_expiry must be YYYY-MM-DD or blank.")
    if membership_type == "life":
        membership_status = "life"
        membership_expiry = ""

    email, email_usable, invite_eligible, email_warnings = validate_admin_email_for_invite(body.get("email")) if "email" in body else ("", False, False, [])
    mobile, phone, phone_warnings = normalise_member_contact_numbers(str(body.get("mobile") or ""), str(body.get("phone") or body.get("phone_number") or ""))
    ice_phone, _ice_bucket, ice_warnings = normalise_import_phone_number(str(body.get("ice_phone_number") or ""))
    first_name, middle_name, last_name, name_warnings = normalise_import_member_names(
        str(body.get("first_name") or ""),
        str(body.get("middle_name") or ""),
        str(body.get("last_name") or ""),
    )
    member_number = clean_text_field(body.get("member_number") or body.get("site_member_id"), 80)
    site_member_id = member_number
    card_number, card_warnings = member_card_number_from_member_number(member_number, body.get("card_number"))

    payload = {
        "membership_type": membership_type,
        "membership_status": membership_status,
        "membership_expiry": membership_expiry,
        "other_callsigns": parse_other_callsigns(body.get("other_callsigns")),
        "site_member_id": site_member_id,
        "member_number": member_number,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "title": clean_text_field(body.get("title"), 40),
        "username": clean_text_field(body.get("username"), 160),
        "gender": clean_text_field(body.get("gender"), 40),
        "date_of_birth_raw": clean_text_field(body.get("date_of_birth_raw") or body.get("date_of_birth"), 40),
        "date_of_birth": clean_text_field(body.get("date_of_birth"), 20),
        "company_name": clean_text_field(body.get("company_name"), 240),
        "membership_level": clean_text_field(body.get("membership_level"), 120),
        "membership_product": clean_text_field(body.get("membership_product"), 180),
        "current_full_product_name": clean_text_field(body.get("current_full_product_name"), 240),
        "membership_amount_paid": normalise_import_money(body.get("membership_amount_paid")),
        "membership_amount_outstanding": normalise_import_money(body.get("membership_amount_outstanding")),
        "membership_level_start_date_raw": clean_text_field(body.get("membership_level_start_date_raw") or body.get("membership_level_start_date"), 40),
        "membership_level_start_date": clean_text_field(body.get("membership_level_start_date"), 20),
        "approve_status": clean_text_field(body.get("approve_status"), 80),
        "printed_magazine": normalise_printed_magazine(body.get("printed_magazine")),
        "join_date_raw": clean_text_field(body.get("join_date_raw") or body.get("join_date"), 40),
        "join_date": clean_text_field(body.get("join_date"), 20),
        "expiry_date_raw": clean_text_field(body.get("expiry_date_raw") or body.get("expiry_date"), 40),
        "expiry_date": clean_text_field(body.get("expiry_date"), 20),
        "card_number": card_number,
        "party_id": clean_text_field(body.get("party_id"), 80),
        "member_type": clean_text_field(body.get("member_type"), 120),
        "primary_first_name": clean_text_field(body.get("primary_first_name"), 120),
        "primary_last_name": clean_text_field(body.get("primary_last_name"), 120),
        "primary_member_number": clean_text_field(body.get("primary_member_number"), 80),
        "profile_image": clean_text_field(body.get("profile_image"), 1000),
        "ice_name": clean_text_field(body.get("ice_name"), 160),
        "ice_phone_raw": clean_text_field(body.get("ice_phone_number"), 80),
        "ice_phone_number": ice_phone,
        "dietary_requirements_allergies": clean_multiline_field(body.get("dietary_requirements_allergies"), 2000),
        "address1": clean_text_field(body.get("address1"), 240),
        "address2": clean_text_field(body.get("address2"), 240),
        "city": clean_text_field(body.get("city"), 120),
        "state": clean_text_field(body.get("state"), 80),
        "country": clean_text_field(body.get("country"), 120),
        "postcode": clean_text_field(body.get("postcode"), 20),
        "postal_address1": clean_text_field(body.get("postal_address1"), 240),
        "postal_address2": clean_text_field(body.get("postal_address2"), 240),
        "postal_city": clean_text_field(body.get("postal_city"), 120),
        "postal_state": clean_text_field(body.get("postal_state"), 80),
        "postal_country": clean_text_field(body.get("postal_country"), 120),
        "postal_postcode": clean_text_field(body.get("postal_postcode"), 20),
        "mobile": mobile,
        "phone": phone,
    }
    # Preserve raw club role/product wording for admin display.
    if "club_roles_raw" in body:
        payload["club_roles_raw"] = clean_text_field(body.get("club_roles_raw"), 500)
        payload["club_roles"] = [x.strip() for x in re.split(r"[,;|\n]", payload["club_roles_raw"]) if x.strip()]
    if "email" in body:
        payload["email"] = email
        payload["email_raw"] = clean_text_field(body.get("email"), 320)
        payload["email_usable"] = email_usable
        payload["invite_eligible"] = invite_eligible
        if email_usable and str(body.get("invited") or "").strip().upper() != "Y":
            payload["invited"] = "N"
    if "committee_position_id" in body:
        payload["committee_position_id"] = normalise_position_id(body.get("committee_position_id") or "")
    return {k: v for k, v in payload.items() if v not in (None, [], {})}


def cognito_attrs_map(attrs: List[Dict[str, str]]) -> Dict[str, str]:
    return {a.get("Name", ""): a.get("Value", "") for a in attrs or []}


def callsign_without_deleted_suffix(value: str) -> str:
    text = str(value or "").strip()
    return text[:-len(DELETED_SUFFIX)].rstrip() if text.endswith(DELETED_SUFFIX) else text


def callsign_with_deleted_suffix(value: str) -> str:
    base = callsign_without_deleted_suffix(value)
    return f"{base}{DELETED_SUFFIX}" if base else DELETED_SUFFIX.strip()


def format_user_summary(user: Dict[str, Any]) -> Dict[str, Any]:
    attrs = cognito_attrs_map(user.get("Attributes") or user.get("UserAttributes") or [])
    enabled = bool(user.get("Enabled", True))
    callsign = attrs.get("custom:callsign", "")
    display_callsign = callsign
    if not enabled and callsign and not callsign.endswith(DELETED_SUFFIX):
        display_callsign = f"{callsign}{DELETED_SUFFIX}"
    return {
        "username": user.get("Username", ""),
        "sub": attrs.get("sub", user.get("Username", "")),
        "email": attrs.get("email", ""),
        "name": attrs.get("name", ""),
        "phone_number": attrs.get("phone_number", ""),
        "callsign": callsign,
        "display_callsign": display_callsign,
        "enabled": enabled,
        "user_status": str(user.get("UserStatus") or ""),
    }


def find_cognito_user(identifier: str) -> Dict[str, Any]:
    require_user_pool()
    needle = str(identifier or "").strip()
    if not needle:
        raise ValueError("A member identifier is required.")
    next_token = None
    while True:
        kwargs: Dict[str, Any] = {"UserPoolId": USER_POOL_ID, "Limit": 60}
        if next_token:
            kwargs["PaginationToken"] = next_token
        resp = cognito.list_users(**kwargs)
        for user in resp.get("Users", []):
            summary = format_user_summary(user)
            if needle in {summary["sub"], summary["email"], summary["username"]}:
                return user
        next_token = resp.get("PaginationToken")
        if not next_token:
            break
    raise ValueError("Member not found in Cognito.")


def resolve_user_summary(identifier: str) -> Dict[str, Any]:
    user = find_cognito_user(identifier)
    summary = format_user_summary(user)
    metadata = get_member_metadata(summary["sub"])
    summary.update(metadata)
    if summary.get("account_status") == "deleted" and summary.get("callsign") and not summary.get("display_callsign"):
        summary["display_callsign"] = f"{summary['callsign']}{DELETED_SUFFIX}"
    return summary


def save_member_metadata(sub: str, payload: Dict[str, Any], claims: Dict[str, Any], *, account_status: str | None = None, deleted_at: str | None = None, deleted_by: str | None = None) -> Dict[str, Any]:
    require_metadata_table()
    existing = get_member_metadata(sub)
    merged = {**existing, **payload}
    if account_status is not None:
        merged["account_status"] = account_status
    if deleted_at is not None:
        merged["deleted_at"] = deleted_at
    if deleted_by is not None:
        merged["deleted_by"] = deleted_by
    now = utc_now()
    item: Dict[str, Dict[str, Any]] = {
        "pk": {"S": member_pk(sub)},
        "sk": {"S": "PROFILE"},
        "membership_type": {"S": str(merged.get("membership_type") or "")},
        "membership_status": {"S": str(merged.get("membership_status") or "")},
        "membership_expiry": {"S": str(merged.get("membership_expiry") or "")},
        "account_status": {"S": str(merged.get("account_status") or "active")},
        "committee_position_id": {"S": normalise_position_id(merged.get("committee_position_id") or "")},
        "other_callsigns": {"L": [{"S": x} for x in parse_other_callsigns(merged.get("other_callsigns"))]},
        "updated_at": {"S": now},
        "updated_by": {"S": claims.get("email") or claims.get("sub") or "admin"},
    }
    for key in [
        "site_member_id", "member_number", "first_name", "middle_name", "last_name", "title", "email", "email_raw", "username", "name", "phone_number", "mobile", "phone",
        "committee_position_name", "official_position_id", "official_position_name",
        "gender", "date_of_birth_raw", "date_of_birth", "company_name", "membership_level", "membership_product", "current_full_product_name",
        "membership_amount_paid", "membership_amount_outstanding", "membership_level_start_date_raw", "membership_level_start_date",
        "approve_status", "printed_magazine", "import_agreement", "form_updated_at_raw", "form_updated_at",
        "join_date_raw", "join_date", "expiry_date_raw", "expiry_date", "card_number", "party_id", "member_type", "primary_first_name",
        "primary_last_name", "primary_member_number", "profile_image", "avatar_data_url", "ice_name", "ice_phone_number", "ice_phone_raw", "dietary_requirements_allergies",
        "address1", "address2", "city", "state", "country", "postcode", "postal_address1", "postal_address2", "postal_city", "postal_state", "postal_country", "postal_postcode",
        "club_roles_raw", "member_created_date_raw", "member_created_date", "import_batch_id", "imported_at", "imported_by", "import_source", "invited",
        "invite_sent_at", "invite_sent_by", "invite_batch_id", "cognito_sub", "cognito_username"
    ]:
        value = str(merged.get(key) or "").strip()
        if value:
            item[key] = {"S": value}
    if "email_usable" in merged:
        item["email_usable"] = {"BOOL": bool(merged.get("email_usable"))}
    if "invite_eligible" in merged:
        item["invite_eligible"] = {"BOOL": bool(merged.get("invite_eligible"))}
    for list_key in ["club_roles", "assigned_role_ids", "assigned_role_names", "system_roles"]:
        if list_key in merged:
            item[list_key] = {"L": [{"S": str(x).strip()} for x in normalise_text_list(merged.get(list_key), max_items=30, max_len=160) if str(x).strip()]}
    if "activated" in merged:
        item["activated"] = {"BOOL": bool(merged.get("activated"))}
    if "imported_member" in merged:
        item["imported_member"] = {"BOOL": bool(merged.get("imported_member"))}
    if merged.get("deleted_at"):
        item["deleted_at"] = {"S": str(merged.get("deleted_at"))}
    if merged.get("deleted_by"):
        item["deleted_by"] = {"S": str(merged.get("deleted_by"))}
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=item)
    return normalise_membership_metadata({
        **merged,
        "updated_at": now,
        "updated_by": claims.get("email") or claims.get("sub") or "admin",
    })


def generate_temporary_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    base = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+"),
    ]
    while len(base) < length:
        base.append(secrets.choice(alphabet + "!@#$%^&*()-_=+"))
    secrets.SystemRandom().shuffle(base)
    return "".join(base)



def list_imported_member_metadata(*, query: str = "") -> List[Dict[str, Any]]:
    require_metadata_table()
    q = str(query or "").strip()
    # Imported metadata-only records are scanned after Cognito users.  The
    # previous hard stop at 500 records could hide later imported members from
    # Site Admin search, which made individual invites impossible once a club
    # import contained more than 500 people.  Keep an upper guard for accidental
    # runaway scans, but do not stop at 500.
    max_items = ADMIN_IMPORTED_MEMBER_SCAN_MAX
    items: List[Dict[str, Any]] = []
    next_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "FilterExpression": "begins_with(pk, :prefix) AND sk = :profile",
            "ExpressionAttributeValues": {":prefix": {"S": "MEMBER#imported:"}, ":profile": {"S": "PROFILE"}},
            "Limit": 100,
        }
        if next_key:
            kwargs["ExclusiveStartKey"] = next_key
        resp = ddb.scan(**kwargs)
        for raw in resp.get("Items", []):
            item = item_to_python(raw)
            sub = str(item.get("pk") or "").replace("MEMBER#", "", 1)
            meta = normalise_membership_metadata(item)
            meta.update({
                "sub": sub,
                "username": meta.get("username") or sub,
                "enabled": False,
                "user_status": "NOT_INVITED",
                "display_callsign": meta.get("club_roles_raw") or "Imported member",
            })
            if not meta.get("name"):
                meta["name"] = " ".join([meta.get("first_name", ""), meta.get("last_name", "")]).strip()
            if not meta.get("invited"):
                meta["invited"] = "N"
            # When an admin searches by name/email/member number, filter while
            # scanning so the matching imported member is not lost behind the
            # result cap.
            if q and not member_matches_search(meta, q):
                continue
            items.append(meta)
            if len(items) >= max_items:
                break
        next_key = resp.get("LastEvaluatedKey")
        if not next_key or len(items) >= max_items:
            break
    return items


def get_metadata_by_site_member_id(site_member_id: str) -> Dict[str, Any] | None:
    require_metadata_table()
    needle = str(site_member_id or "").strip()
    if not needle:
        return None
    next_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "FilterExpression": "site_member_id = :sid AND sk = :profile",
            "ExpressionAttributeValues": {":sid": {"S": needle}, ":profile": {"S": "PROFILE"}},
            "Limit": 25,
        }
        if next_key:
            kwargs["ExclusiveStartKey"] = next_key
        resp = ddb.scan(**kwargs)
        for raw in resp.get("Items", []):
            item = item_to_python(raw)
            item["sub"] = str(item.get("pk") or "").replace("MEMBER#", "", 1)
            return item
        next_key = resp.get("LastEvaluatedKey")
        if not next_key:
            break
    return None


def get_imported_member_metadata_by_site_member_id(site_member_id: str) -> Dict[str, Any] | None:
    """Fast path for CSV-imported members, whose synthetic sub is deterministic."""
    sid = str(site_member_id or "").strip()
    if not sid:
        return None
    item = get_member_metadata(IMPORTED_MEMBER_SUB_PREFIX + sid)
    if not item:
        return None
    item["sub"] = IMPORTED_MEMBER_SUB_PREFIX + sid
    return item




def max_existing_numeric_member_number() -> int:
    """Return the highest numeric member_number currently stored on member profiles.

    v2 member imports store member_number as the authoritative club/card
    number.  site_member_id is retained as a compatibility mirror only; use it
    as a fallback for older records that pre-date member_number.
    """
    require_metadata_table()
    highest = 0
    next_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "ProjectionExpression": "member_number, site_member_id, sk",
            "FilterExpression": "(attribute_exists(member_number) OR attribute_exists(site_member_id)) AND sk = :profile",
            "ExpressionAttributeValues": {":profile": {"S": "PROFILE"}},
            "Limit": 100,
        }
        if next_key:
            kwargs["ExclusiveStartKey"] = next_key
        resp = ddb.scan(**kwargs)
        for raw in resp.get("Items", []):
            value = str(from_ddb_attr(raw.get("member_number", {})) or "").strip()
            if not value:
                value = str(from_ddb_attr(raw.get("site_member_id", {})) or "").strip()
            if value.isdigit():
                highest = max(highest, int(value))
        next_key = resp.get("LastEvaluatedKey")
        if not next_key:
            break
    return highest


def allocate_next_member_number() -> str:
    """Atomically allocate max(member_number)+1 using a DynamoDB counter item.

    member_number is the real club/member-card number.  The separate CSV
    card_number is ignored/mirrored, so new admin-created members allocate the
    next member_number safely at write time.
    """
    require_metadata_table()
    key = {"pk": {"S": "COUNTER#MEMBER_NUMBER"}, "sk": {"S": "COUNTER"}}
    while True:
        try:
            resp = ddb.update_item(
                TableName=MEMBER_METADATA_TABLE,
                Key=key,
                UpdateExpression="ADD current_value :one SET updated_at = :now",
                ConditionExpression="attribute_exists(pk)",
                ExpressionAttributeValues={":one": {"N": "1"}, ":now": {"S": utc_now()}},
                ReturnValues="UPDATED_NEW",
            )
            value = from_ddb_attr(resp.get("Attributes", {}).get("current_value", {"N": "0"}))
            return str(int(value))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            next_value = max_existing_numeric_member_number() + 1
            try:
                ddb.put_item(
                    TableName=MEMBER_METADATA_TABLE,
                    Item={**key, "current_value": {"N": str(next_value)}, "created_at": {"S": utc_now()}},
                    ConditionExpression="attribute_not_exists(pk)",
                )
                return str(next_value)
            except ClientError as put_exc:
                if put_exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                # Another writer created the counter between our scan and put; retry ADD.
                continue



def advance_member_number_counter_at_least(value: Any) -> None:
    """Keep the atomic member-number counter ahead of any manually/imported member numbers."""
    text = str(value or "").strip()
    if not text.isdigit():
        return
    target = int(text)
    if target <= 0:
        return
    key = {"pk": {"S": "COUNTER#MEMBER_NUMBER"}, "sk": {"S": "COUNTER"}}
    while True:
        resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=key, ConsistentRead=True)
        if not resp.get("Item"):
            try:
                ddb.put_item(
                    TableName=MEMBER_METADATA_TABLE,
                    Item={**key, "current_value": {"N": str(max(max_existing_numeric_member_number(), target))}, "created_at": {"S": utc_now()}},
                    ConditionExpression="attribute_not_exists(pk)",
                )
                return
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                continue
        current = int(from_ddb_attr(resp["Item"].get("current_value", {"N": "0"})) or 0)
        if current >= target:
            return
        try:
            ddb.update_item(
                TableName=MEMBER_METADATA_TABLE,
                Key=key,
                UpdateExpression="SET current_value = :target, updated_at = :now",
                ConditionExpression="current_value = :current",
                ExpressionAttributeValues={":target": {"N": str(target)}, ":current": {"N": str(current)}, ":now": {"S": utc_now()}},
            )
            return
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            continue

def validate_admin_email_for_invite(value: Any) -> tuple[str, bool, bool, List[str]]:
    email, usable, warnings = normalise_import_email(str(value or ""))
    return email, usable, usable, warnings


def clean_text_field(value: Any, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def normalise_printed_magazine(value: Any) -> str:
    """Canonicalise the printed magazine preference to Y/N/blank.

    Older imports/admin edits used values such as Yes, I agree, true, or 1,
    while the profile checkbox expects a simple yes/no flag. Keep this
    canonical so Site Admin, imports, and member profile all agree.
    """
    if value is True:
        return "Y"
    if value is False:
        return "N"
    text = str(value or "").strip()
    lowered = text.lower()
    if not lowered:
        return ""
    if lowered in {"y", "yes", "true", "1", "on", "agree", "agreed", "i agree"}:
        return "Y"
    if lowered in {"n", "no", "false", "0", "off"}:
        return "N"
    return "Y" if lowered.startswith("y") else clean_text_field(text, 16)


def clean_multiline_field(value: Any, limit: int = 2000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]

def existing_site_member_id_set() -> set[str]:
    """Return existing SiteMemberId values with one table scan for import preview.

    Preview must stay quick and side-effect-free.  It deliberately avoids Cognito
    lookups and per-row DynamoDB scans so a large already-imported list does not
    make preview time out.
    """
    require_metadata_table()
    existing: set[str] = set()
    next_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "ProjectionExpression": "member_number, site_member_id, sk",
            "FilterExpression": "(attribute_exists(member_number) OR attribute_exists(site_member_id)) AND sk = :profile",
            "ExpressionAttributeValues": {":profile": {"S": "PROFILE"}},
            "Limit": 250,
        }
        if next_key:
            kwargs["ExclusiveStartKey"] = next_key
        resp = ddb.scan(**kwargs)
        for raw in resp.get("Items", []):
            sid = str(from_ddb_attr(raw.get("site_member_id", {})) or "").strip()
            mid = str(from_ddb_attr(raw.get("member_number", {})) or "").strip()
            if sid:
                existing.add(sid)
            if mid:
                existing.add(mid)
        next_key = resp.get("LastEvaluatedKey")
        if not next_key:
            break
    return existing


def count_member_metadata_records(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    require_metadata_table()
    counts = {"total_profiles": 0, "imported_profiles": 0, "uninvited_imported": 0, "invited_imported": 0, "with_site_member_id": 0}
    next_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "ProjectionExpression": "pk, sk, site_member_id, member_number, SiteMemberId, siteMemberId, imported_member, invited, cognito_sub",
            "FilterExpression": "sk = :profile",
            "ExpressionAttributeValues": {":profile": {"S": "PROFILE"}},
            "Limit": 250,
        }
        if next_key:
            kwargs["ExclusiveStartKey"] = next_key
        resp = ddb.scan(**kwargs)
        for raw in resp.get("Items", []):
            item = item_to_python(raw)
            counts["total_profiles"] += 1
            if str(first_present(item, "member_number", "site_member_id", "SiteMemberId", "siteMemberId") or "").strip():
                counts["with_site_member_id"] += 1
            pk = str(item.get("pk") or "")
            imported = bool(item.get("imported_member")) or pk.startswith("MEMBER#imported:")
            if imported:
                counts["imported_profiles"] += 1
                invited = str(item.get("invited") or "N").strip().upper()
                if invited == "Y":
                    counts["invited_imported"] += 1
                else:
                    counts["uninvited_imported"] += 1
        next_key = resp.get("LastEvaluatedKey")
        if not next_key:
            break
    return response(200, {"counts": counts})


def find_cognito_user_by_email(email: str) -> Dict[str, Any] | None:
    require_user_pool()
    address = str(email or "").strip().lower()
    if not address:
        return None
    try:
        resp = cognito.list_users(UserPoolId=USER_POOL_ID, Filter=f'email = "{address}"', Limit=1)
        users = resp.get("Users", [])
        return users[0] if users else None
    except ClientError:
        return None


def list_member_summaries(query: str = "") -> List[Dict[str, Any]]:
    if not USER_POOL_ID:
        return []
    users: List[Dict[str, Any]] = []
    next_token = None
    while True:
        kwargs: Dict[str, Any] = {"UserPoolId": USER_POOL_ID, "Limit": 60}
        if next_token:
            kwargs["PaginationToken"] = next_token
        resp = cognito.list_users(**kwargs)
        users.extend(resp.get("Users", []))
        next_token = resp.get("PaginationToken")
        if not next_token or len(users) >= 300:
            break
    q = query.strip().lower()
    vehicle_rego_matches = scan_vehicle_registration_matches(query) if q else {}
    results: List[Dict[str, Any]] = []
    seen_subs: set[str] = set()
    for user in users:
        summary = format_user_summary(user)
        summary = merge_non_empty_metadata(summary, get_member_metadata(summary["sub"]))
        if not summary.get("invited"):
            summary["invited"] = "Y"
        seen_subs.add(summary["sub"])
        if not summary.get("enabled"):
            summary["account_status"] = "deleted"
            summary["display_callsign"] = callsign_with_deleted_suffix(summary.get("callsign", "")) if summary.get("callsign") else summary.get("display_callsign", "")
        vehicle_regos = vehicle_rego_matches.get(str(summary.get("sub") or ""), [])
        if q and not member_matches_search(summary, query, vehicle_regos):
            continue
        if vehicle_regos:
            summary["matched_vehicle_registrations"] = vehicle_regos
        summary["groups"] = sorted(member_groups_for_username(str(summary.get("username") or summary.get("email") or "")))
        results.append(summary)
    for imported in list_imported_member_metadata(query=query):
        if imported.get("sub") in seen_subs:
            continue
        vehicle_regos = vehicle_rego_matches.get(str(imported.get("sub") or ""), [])
        if q and not member_matches_search(imported, query, vehicle_regos):
            continue
        if vehicle_regos:
            imported["matched_vehicle_registrations"] = vehicle_regos
        imported["groups"] = []
        results.append(imported)
    results.sort(key=member_summary_sort_key)
    return results[:2000]




def member_summary_display_number(item: Dict[str, Any]) -> str:
    return str(first_present(item, "member_number", "site_member_id", "SiteMemberId", "siteMemberId", "memberNumber", "MemberNumber") or "").strip()


def compact_alnum(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def name_sort_parts(item: Dict[str, Any]) -> tuple[str, str, str]:
    last = str(first_present(item, "last_name", "lastName", "Lastname") or "").strip().lower()
    first = str(first_present(item, "first_name", "firstName", "Firstname") or "").strip().lower()
    middle = str(first_present(item, "middle_name", "middleName") or "").strip().lower()
    if not (last or first or middle):
        name = str(item.get("name") or "").strip()
        if "," in name:
            lhs, rhs = name.split(",", 1)
            last = lhs.strip().lower()
            parts = rhs.strip().split()
            first = (parts[0] if parts else "").lower()
            middle = " ".join(parts[1:]).lower()
        elif name:
            parts = name.split()
            if len(parts) == 1:
                first = parts[0].lower()
            else:
                first = parts[0].lower()
                middle = " ".join(parts[1:-1]).lower()
                last = parts[-1].lower()
    return last, first, middle


def member_summary_sort_key(item: Dict[str, Any]) -> tuple[str, str, str, int, str]:
    last, first, middle = name_sort_parts(item)
    member_no = member_summary_display_number(item)
    try:
        member_no_int = int(re.sub(r"\D+", "", member_no) or "0")
    except ValueError:
        member_no_int = 0
    return (last, first, middle, member_no_int, str(item.get("email") or item.get("sub") or "").lower())


def scan_vehicle_registration_matches(query: str) -> Dict[str, List[str]]:
    require_metadata_table()
    q = str(query or "").strip().lower()
    q_compact = compact_alnum(query)
    if not q and not q_compact:
        return {}
    matches: Dict[str, List[str]] = {}
    next_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "ProjectionExpression": "pk, sk, rego_number",
            "FilterExpression": "begins_with(#sk, :vehicle)",
            "ExpressionAttributeNames": {"#sk": "sk"},
            "ExpressionAttributeValues": {":vehicle": {"S": "VEHICLE#"}},
            "Limit": 250,
        }
        if next_key:
            kwargs["ExclusiveStartKey"] = next_key
        resp = ddb.scan(**kwargs)
        for raw in resp.get("Items", []):
            item = item_to_python(raw)
            rego = str(item.get("rego_number") or "").strip()
            if not rego:
                continue
            rego_lower = rego.lower()
            rego_compact = compact_alnum(rego)
            if (q and q in rego_lower) or (q_compact and q_compact in rego_compact):
                pk = str(item.get("pk") or "")
                sub = pk.replace("MEMBER#", "", 1) if pk.startswith("MEMBER#") else pk
                if sub:
                    matches.setdefault(sub, []).append(rego)
        next_key = resp.get("LastEvaluatedKey")
        if not next_key:
            break
    return matches


def member_search_haystack(item: Dict[str, Any], vehicle_regos: List[str] | None = None) -> str:
    return " ".join([
        member_summary_display_number(item),
        str(first_present(item, "last_name", "lastName", "Lastname") or ""),
        str(first_present(item, "first_name", "firstName", "Firstname") or ""),
        str(first_present(item, "middle_name", "middleName") or ""),
        str(item.get("name") or ""),
        str(item.get("title") or ""),
        str(item.get("username") or ""),
        str(item.get("email") or ""),
        str(item.get("email_raw") or ""),
        str(item.get("mobile") or ""),
        str(item.get("phone") or ""),
        str(item.get("phone_raw") or ""),
        str(item.get("phone_number") or ""),
        str(item.get("club_roles_raw") or ""),
        str(item.get("committee_position_name") or ""),
        str(item.get("official_position_name") or ""),
        str(item.get("address1") or ""),
        str(item.get("address2") or ""),
        str(item.get("city") or ""),
        str(item.get("postcode") or ""),
        str(item.get("postal_address1") or ""),
        str(item.get("postal_address2") or ""),
        str(item.get("postal_city") or ""),
        str(item.get("postal_postcode") or ""),
        " ".join(vehicle_regos or []),
    ]).lower()


def member_matches_search(item: Dict[str, Any], query: str, vehicle_regos: List[str] | None = None) -> bool:
    q = str(query or "").strip().lower()
    if not q:
        return True
    haystack = member_search_haystack(item, vehicle_regos)
    if q in haystack:
        return True
    q_compact = compact_alnum(query)
    haystack_compact = compact_alnum(haystack)
    if q_compact and q_compact in haystack_compact:
        return True
    # Admins often search imported members as "First Last" while the old-site
    # data and result cards may store/display them as "Last, First".  Match all
    # typed words independently so name searches are not order-sensitive.
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", q) if tok]
    if len(tokens) > 1 and all(tok in haystack for tok in tokens):
        return True
    compact_tokens = [compact_alnum(tok) for tok in tokens if compact_alnum(tok)]
    return bool(len(compact_tokens) > 1 and all(tok in haystack_compact for tok in compact_tokens))


def filter_member_summaries(items: List[Dict[str, Any]], *, status: str = "", invite: str = "", account: str = "") -> List[Dict[str, Any]]:
    status_filter = str(status or "").strip().lower()
    invite_filter = str(invite or "").strip().lower()
    account_filter = str(account or "").strip().lower()
    filtered: List[Dict[str, Any]] = []
    for item in items:
        membership_status = str(item.get("membership_status") or item.get("status") or "").strip().lower()
        account_status = str(item.get("account_status") or "active").strip().lower()
        cognito_status = str(item.get("user_status") or "").strip().upper()
        imported_only = str(item.get("sub") or "").startswith(IMPORTED_MEMBER_SUB_PREFIX) or bool(item.get("imported_member"))
        email_usable = bool(item.get("email_usable")) or bool(normalise_email_address(item.get("email") or ""))
        invited = str(item.get("invited") or ("N" if imported_only else "Y")).strip().upper()

        if status_filter:
            if status_filter == "blank":
                if membership_status:
                    continue
            else:
                # Exact, case-insensitive status matching. Avoid substring matching so
                # Current never leaks Expired rows and vice versa.
                if membership_status != status_filter:
                    continue

        if invite_filter:
            if invite_filter == "pending" and not (invited != "Y" and email_usable):
                continue
            if invite_filter == "invited" and invited != "Y":
                continue
            if invite_filter == "no_email" and email_usable:
                continue

        if account_filter:
            if account_filter == "imported" and not imported_only:
                continue
            if account_filter == "cognito" and imported_only:
                continue
            if account_filter == "active" and (account_status == "deleted" or not item.get("enabled", True)):
                continue
            if account_filter == "deleted" and not (account_status == "deleted" or not item.get("enabled", True)):
                continue

        item["display_member_number"] = member_summary_display_number(item)
        item["imported_only"] = imported_only
        item["cognito_status"] = cognito_status
        filtered.append(item)
    return filtered


def paginate_admin_member_summaries(query: str = "", *, status: str = "", invite: str = "", account: str = "", page: int = 1, page_size: int = 10) -> Dict[str, Any]:
    # Member Metadata intentionally shows 10 results per batch so the admin PWA
    # stays usable on phones and avoids shipping a large member list by default.
    safe_page_size = 10
    safe_page = max(1, int(page or 1))
    items = filter_member_summaries(list_member_summaries(query), status=status, invite=invite, account=account)
    total = len(items)
    page_count = max(1, (total + safe_page_size - 1) // safe_page_size)
    if safe_page > page_count:
        safe_page = page_count
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return {
        "items": items[start:end],
        "page": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "page_count": page_count,
            "has_previous": safe_page > 1,
            "has_next": safe_page < page_count,
        },
    }


def list_active_member_recipients() -> List[Dict[str, str]]:
    recipients: List[Dict[str, str]] = []
    for item in list_member_summaries(""):
        if not item.get("enabled", True):
            continue
        if str(item.get("account_status") or "active").strip().lower() == "deleted":
            continue
        email = str(item.get("email") or "").strip()
        if not email:
            continue
        recipients.append({
            "sub": str(item.get("sub") or "").strip(),
            "user_sub": str(item.get("sub") or "").strip(),
            "email": email,
            "name": str(item.get("name") or item.get("display_callsign") or item.get("callsign") or email).strip(),
            "imported_member": bool(item.get("imported_member")),
            "cognito_sub": str(item.get("cognito_sub") or "").strip(),
            "cognito_username": str(item.get("cognito_username") or item.get("username") or "").strip(),
        })
    return recipients


def send_admin_test_email(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    target = str(body.get("to") or claims.get("email") or "").strip()
    if not target:
        raise ValueError("to is required.")
    subject = str(body.get("subject") or "LROC SES test email").strip()
    message = str(body.get("message") or "This is a test email from the LROC SES foundation.").strip()
    html_message = str(body.get("html") or "").strip()
    result = send_email_via_ses([target], subject, message, html_message or None)
    return response(200, {
        "message": f"Test email queued to {target}.",
        "to": target,
        "message_id": result.get("MessageId", ""),
        "from": SES_FROM_EMAIL,
    })


def member_groups_for_username(username: str) -> set[str]:
    if not USER_POOL_ID or not username:
        return set()
    try:
        resp = cognito.admin_list_groups_for_user(UserPoolId=USER_POOL_ID, Username=username)
        return {str(group.get("GroupName") or "").strip() for group in resp.get("Groups") or [] if str(group.get("GroupName") or "").strip()}
    except ClientError:
        return set()


def resolve_admin_email_audience(audience: str = "active") -> Dict[str, Any]:
    audience = str(audience or "active").strip().lower()
    allowed = {"active", "committee", "admins", "webmaster"}
    if audience not in allowed:
        raise ValueError("Unsupported audience filter.")
    recipients: List[Dict[str, Any]] = []
    for item in list_member_summaries(""):
        if not item.get("enabled", True):
            continue
        if str(item.get("account_status") or "active").strip().lower() == "deleted":
            continue
        email = normalise_email_address(item.get("email") or "")
        if not email:
            continue
        groups = member_groups_for_username(str(item.get("username") or email)) if audience != "active" else set()
        if audience == "committee" and not groups.intersection({"committee", "admins", "webmaster"}):
            continue
        if audience == "admins" and not groups.intersection({"admins", "webmaster"}):
            continue
        if audience == "webmaster" and "webmaster" not in groups:
            continue
        recipients.append({
            "sub": str(item.get("sub") or ""),
            "email": email,
            "name": str(item.get("name") or item.get("display_callsign") or item.get("callsign") or email).strip(),
            "callsign": str(item.get("display_callsign") or item.get("callsign") or ""),
            "groups": sorted(groups),
        })
    filtered = filter_sendable_recipients(recipients)
    return {
        "audience": audience,
        "total": len(recipients),
        "sendable": filtered["sendable"],
        "skipped": filtered["skipped"],
        "sendable_count": len(filtered["sendable"]),
        "skipped_count": len(filtered["skipped"]),
    }


def admin_email_audience_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    audience = str(body.get("audience") or "active").strip().lower()
    data = resolve_admin_email_audience(audience)
    preview = int(body.get("preview", 50) or 50)
    preview = max(0, min(150, preview))
    data["sendable"] = data["sendable"][:preview]
    data["skipped"] = data["skipped"][:preview]
    return response(200, data)


def build_admin_bulk_email_bodies(subject: str, message: str, recipient: Dict[str, Any] | None = None, sender: Dict[str, Any] | None = None) -> Dict[str, str]:
    if recipient is None:
        recipient = {"name": "Member", "email": ""}
    if sender is None:
        sender = secretary_sender_context()
    return wrap_member_email(subject, message, recipient, sender)


def admin_email_positions_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    positions = [p for p in list_club_positions() if bool(p.get("active", True))]
    sender = sender_context_from_claims(claims, "")
    return response(200, {"items": positions, "default_from": sender.get("from_email", "")})


def admin_email_send_test_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    target = normalise_email_address(body.get("to") or claims.get("email") or "")
    if not valid_email_address(target):
        raise ValueError("A valid test recipient email address is required.")
    suppression = get_email_suppression(target)
    if suppression and str(suppression.get("status") or "suppressed").lower() != "cleared":
        raise ValueError(f"Not sending test email to suppressed address: {target} ({suppression.get('reason') or 'suppressed'}).")
    sender = sender_context_from_claims(claims, str(body.get("from_position_id") or ""))
    mail = build_admin_bulk_email_bodies(str(body.get("subject") or ""), str(body.get("message") or ""), {"email": target, "name": "Test recipient"}, sender)
    result = send_email_via_ses([target], mail["subject"], mail["text"], mail["html"], from_email=sender.get("from_email"), reply_to=sender.get("reply_to"))
    return response(200, {"message": f"Test email queued to {target}.", "to": target, "message_id": result.get("MessageId", ""), "from": sender.get("from_email", "")})


def admin_email_send_bulk_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    if str(body.get("confirm") or "").strip().upper() != "SEND":
        raise ValueError("Bulk send requires confirm=SEND.")
    audience = str(body.get("audience") or "active").strip().lower()
    sender = sender_context_from_claims(claims, str(body.get("from_position_id") or ""))
    audience_data = resolve_admin_email_audience(audience)
    recipients = [item for item in audience_data["sendable"] if normalise_email_address(item.get("email") or "")]
    sent = 0
    message_ids: List[str] = []
    for recipient in recipients:
        mail = build_admin_bulk_email_bodies(str(body.get("subject") or ""), str(body.get("message") or ""), recipient, sender)
        result = send_email_via_ses([recipient["email"]], mail["subject"], mail["text"], mail["html"], from_email=sender.get("from_email"), reply_to=sender.get("reply_to"))
        sent += 1
        if result.get("MessageId"):
            message_ids.append(str(result.get("MessageId")))
    return response(200, {"message": f"Bulk email queued to {sent} recipient{'s' if sent != 1 else ''}.", "audience": audience, "attempted": len(recipients), "sent": sent, "skipped": audience_data["skipped_count"], "from": sender.get("from_email", ""), "message_ids": message_ids})

def admin_email_suppress_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    email = normalise_email_address(body.get("email") or "")
    reason = str(body.get("reason") or "manual").strip().lower()
    if reason not in EMAIL_SUPPRESSION_REASONS:
        reason = "manual"
    item = suppress_email_address(email, reason, source="admin", details={"updated_by": str(claims.get("email") or claims.get("sub") or "admin")})
    return response(200, {"message": f"{email} suppressed for {reason}.", "item": item})


def admin_email_clear_suppression_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    email = normalise_email_address(body.get("email") or "")
    item = clear_email_suppression(email, cleared_by=str(claims.get("email") or claims.get("sub") or "admin"))
    return response(200, {"message": f"Suppression cleared for {email}.", "item": item})


def update_admin_member_roles(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    sub = str(body.get("sub") or "").strip()
    if not sub:
        raise ValueError("sub is required.")
    user = find_cognito_user(sub)
    summary = format_user_summary(user)
    username = str(summary.get("username") or summary.get("email") or sub)
    requested = body.get("roles") or []
    if not isinstance(requested, list):
        raise ValueError("roles must be a list.")
    target = {str(x or "").strip() for x in requested if str(x or "").strip()}
    if "member" in target:
        target.remove("member")
        target.add("members")
    if not target.issubset(ROLE_GROUPS):
        raise ValueError("Unsupported role requested.")
    target.add("members")
    current = member_groups_for_username(username)
    for group in sorted(target - current):
        cognito.admin_add_user_to_group(UserPoolId=USER_POOL_ID, Username=username, GroupName=group)
    for group in sorted((current & ROLE_GROUPS) - target):
        cognito.admin_remove_user_from_group(UserPoolId=USER_POOL_ID, Username=username, GroupName=group)
    position_id = normalise_position_id(body.get("committee_position_id") or "")
    position = get_club_position(position_id) if position_id else None
    position_name = str((position or {}).get("position_name") or "").strip()
    if position_id and not position_name:
        position_name = position_id.replace("-", " ").title()
    metadata_payload = {
        "committee_position_id": position_id,
        "committee_position_name": position_name,
        "official_position_id": position_id,
        "official_position_name": position_name,
        "assigned_role_ids": [position_id] if position_id else [],
        "assigned_role_names": [position_name] if position_name else [],
        "system_roles": sorted(target),
    }
    metadata = save_member_metadata(sub, metadata_payload, claims)
    updated = resolve_user_summary(sub)
    updated.update(metadata)
    updated["groups"] = sorted(member_groups_for_username(username))
    return response(200, {"message": "Member roles and position updated in member metadata.", "item": updated})

def get_profile_metadata(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = claims.get("sub")
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    return response(200, get_member_metadata(sub))


def update_profile_preferences(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = claims.get("sub")
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    payload = validate_profile_preferences_payload(parse_body(event))
    metadata = save_member_metadata(sub, payload, claims)
    return response(200, {"message": "Profile preferences updated.", "item": metadata})


def list_admin_member_metadata(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    params = get_query_params(event)
    query = (params.get("q") or "").strip()
    status = (params.get("status") or "").strip()
    invite = (params.get("invite") or "").strip()
    account = (params.get("account") or "").strip()
    try:
        page = int(params.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(params.get("page_size") or 10)
    except (TypeError, ValueError):
        page_size = 10
    return response(200, paginate_admin_member_summaries(query, status=status, invite=invite, account=account, page=page, page_size=page_size))


def update_admin_member_metadata(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    sub = str(body.get("sub") or "").strip()
    if not sub:
        raise ValueError("sub is required.")
    payload = validate_membership_payload(body)
    metadata = save_member_metadata(sub, payload, claims)
    summary = resolve_user_summary(sub)
    summary.update(metadata)
    return response(200, {"message": "Member metadata updated.", "item": summary})


def resend_admin_member_invite(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    sub = str(body.get("sub") or "").strip()
    if not sub:
        raise ValueError("sub is required.")

    # Imported metadata-only members can become real Cognito users once an admin
    # adds a usable email address.  This is the future bulk-invite path in small.
    if sub.startswith(IMPORTED_MEMBER_SUB_PREFIX):
        meta = get_member_metadata(sub)
        email = str(meta.get("email") or "").strip().lower()
        if not email or not meta.get("invite_eligible"):
            raise ValueError("This imported member has no usable email address yet. Add an email first, save, then send the invite.")
        existing_user = find_cognito_user_by_email(email)
        if existing_user:
            created_user = existing_user
        else:
            attrs = [
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ]
            if meta.get("name"):
                attrs.append({"Name": "name", "Value": str(meta.get("name"))})
            phone_for_cognito = str(meta.get("mobile") or "").strip()
            if phone_for_cognito.startswith("61"):
                attrs.append({"Name": "phone_number", "Value": "+" + phone_for_cognito})
            temp_password = generate_temporary_password()
            create_resp = cognito.admin_create_user(
                UserPoolId=USER_POOL_ID,
                Username=email,
                TemporaryPassword=temp_password,
                UserAttributes=attrs,
                DesiredDeliveryMediums=["EMAIL"],
            )
            created_user = create_resp.get("User") or find_cognito_user(email)
            cognito.admin_add_user_to_group(UserPoolId=USER_POOL_ID, Username=email, GroupName="members")
        summary = format_user_summary(created_user)
        payload = dict(meta)
        payload.update({
            "invited": "Y",
            "invite_sent_at": utc_now(),
            "invite_sent_by": claims.get("email") or claims.get("sub") or "admin",
            "cognito_sub": summary.get("sub") or "",
            "cognito_username": summary.get("username") or email,
            "imported_member": False,
        })
        metadata = save_member_metadata(summary["sub"], payload, claims, account_status="active")
        # Remove the synthetic imported-only record to avoid duplicate rows.
        ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=meta_key(sub))
        summary.update(metadata)
        return response(200, {"message": f"Invitation sent to {email}.", "item": summary})

    user = find_cognito_user(sub)
    summary = format_user_summary(user)
    if not summary.get("enabled", True):
        raise ValueError("Disabled members must be restored before resending an invite.")
    if str(summary.get("user_status") or "") != "FORCE_CHANGE_PASSWORD":
        raise ValueError("Invite resend is only available while the account is awaiting first sign-in.")
    cognito.admin_create_user(
        UserPoolId=USER_POOL_ID,
        Username=summary["username"],
        MessageAction="RESEND",
        DesiredDeliveryMediums=["EMAIL"],
    )
    result = resolve_user_summary(summary["sub"])
    return response(200, {"message": f"Invitation resent to {result.get('email') or result.get('username') or 'member'}.", "item": result})


def create_admin_member(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    payload = validate_membership_payload(body)
    email = str(payload.get("email") or "").strip().lower()
    name = clean_text_field(body.get("name") or payload.get("name") or " ".join([payload.get("first_name", ""), payload.get("last_name", "")]).strip(), 240)
    if name:
        payload["name"] = name
    if not payload.get("member_number"):
        payload["member_number"] = allocate_next_member_number()
    # site_member_id and card_number mirror member_number for legacy UI/data compatibility.
    payload["site_member_id"] = str(payload.get("member_number") or "").strip()
    payload["card_number"] = str(payload.get("member_number") or "").strip()
    advance_member_number_counter_at_least(payload.get("member_number"))

    if email:
        attrs = [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ]
        if name:
            attrs.append({"Name": "name", "Value": name})
        phone_for_cognito = str(payload.get("mobile") or "").strip()
        if phone_for_cognito.startswith("61"):
            attrs.append({"Name": "phone_number", "Value": "+" + phone_for_cognito})
        callsign = str(body.get("callsign") or "").strip()
        if callsign:
            attrs.append({"Name": "custom:callsign", "Value": callsign[:32]})
        temp_password = generate_temporary_password()
        create_resp = cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            TemporaryPassword=temp_password,
            UserAttributes=attrs,
            DesiredDeliveryMediums=["EMAIL"],
        )
        cognito.admin_add_user_to_group(UserPoolId=USER_POOL_ID, Username=email, GroupName="members")
        created_user = create_resp.get("User") or find_cognito_user(email)
        summary = format_user_summary(created_user)
        payload.update({
            "invited": "Y",
            "invite_sent_at": utc_now(),
            "invite_sent_by": claims.get("email") or claims.get("sub") or "admin",
            "cognito_sub": summary.get("sub") or "",
            "cognito_username": summary.get("username") or email,
            "imported_member": False,
        })
        metadata = save_member_metadata(summary["sub"], payload, claims, account_status="active", deleted_at="", deleted_by="")
        summary.update(metadata)
        return response(200, {"message": "Member created and invitation sent.", "item": summary})

    # Metadata-only new member.  Useful when the club has a member but no email yet.
    if not name:
        raise ValueError("name or first/last name is required when email is blank.")
    sub = IMPORTED_MEMBER_SUB_PREFIX + str(payload.get("site_member_id") or payload.get("card_number"))
    payload.update({
        "email": "",
        "email_usable": False,
        "invite_eligible": False,
        "invited": "N",
        "imported_member": True,
        "import_source": "admin-created-metadata",
        "imported_at": utc_now(),
        "imported_by": claims.get("email") or claims.get("sub") or "admin",
    })
    metadata = save_member_metadata(sub, payload, claims, account_status="active", deleted_at="", deleted_by="")
    summary = {"sub": sub, "username": sub, "enabled": False, "user_status": "NOT_INVITED", "email": "", "name": name}
    summary.update(metadata)
    return response(200, {"message": "Member metadata created. Add an email later to enable sending an invite.", "item": summary})



def parse_import_date(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return raw, datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw, ""


def split_club_roles(value: str) -> List[str]:
    roles: List[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;|]+", str(value or "")):
        role = re.sub(r"\s+", " ", part).strip()
        if not role:
            continue
        key = role.lower()
        if key in seen:
            continue
        seen.add(key)
        roles.append(role[:80])
    return roles[:20]


def normalise_import_phone_number(value: str) -> tuple[str, str, List[str]]:
    """Return (normalised_number, bucket, warnings).

    Imported club data has all contact numbers in the Phone column and a mix of
    AU formats. Where possible, normalise to digits-only international AU form:
    61xxxxxxxxx. Mobile numbers are identified by the 614 prefix so future SMS
    work does not accidentally target landlines.
    """
    raw = str(value or "").strip()
    warnings: List[str] = []
    if not raw:
        return "", "", warnings

    if re.search(r"[A-Za-z]", raw):
        warnings.append("Phone contained text/comment; non-numeric text was ignored.")

    cleaned = re.sub(r"[^0-9+]", "", raw)
    if cleaned.count("+") > 1 or ("+" in cleaned and not cleaned.startswith("+")):
        cleaned = "+" + cleaned.replace("+", "")
        warnings.append("Phone contained a misplaced plus sign; it was normalised.")

    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        warnings.append("Phone could not be normalised because no digits were found.")
        return raw, "phone", warnings

    normalised = ""
    if cleaned.startswith("+"):
        if digits.startswith("61") and len(digits) == 11:
            normalised = digits
        else:
            warnings.append("Phone has an international prefix but is not an 11-digit Australian 61 number; raw digits were preserved.")
            normalised = digits
    elif digits.startswith("61") and len(digits) == 11:
        normalised = digits
    elif digits.startswith("0") and len(digits) == 10:
        normalised = "61" + digits[1:]
    elif digits.startswith("4") and len(digits) == 9:
        normalised = "61" + digits
        warnings.append("Mobile looked like it was missing the leading 0; normalised as an Australian mobile.")
    elif len(digits) == 8:
        warnings.append("Phone looks like an 8-digit local landline with no area code; it was not converted to 61 format.")
        normalised = digits
    else:
        warnings.append("Phone format was not recognised; raw digits were preserved.")
        normalised = digits

    bucket = "mobile" if normalised.startswith("614") and len(normalised) == 11 else "phone"
    return normalised, bucket, warnings


PLACEHOLDER_MEMBER_EMAILS = {"unknown@unknown", "unknown@unknown.com", "noemail@unknown", "no-email@unknown"}


def normalise_import_email(value: str) -> tuple[str, bool, List[str]]:
    raw = str(value or "").strip().lower()
    warnings: List[str] = []
    if not raw:
        return "", False, ["No email address; this member can be imported but cannot be invited until an email is added."]
    if raw in PLACEHOLDER_MEMBER_EMAILS:
        return "", False, [f"Placeholder email {raw} was treated as missing; member can be imported but cannot be invited until a real email is added."]
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", raw):
        return "", False, [f"Email format is not valid ({raw}); member can be imported but cannot be invited until corrected."]
    return raw, True, warnings


def csv_value(row: Dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def csv_value_any(row: Dict[str, Any], *keys: str) -> str:
    """Fetch a CSV value by exact key, then by trimmed/case-insensitive key.

    The richer old-site export includes at least one header with trailing
    whitespace (car #1 - make ), so import code must not depend on perfect
    header spelling.
    """
    for key in keys:
        if key in row and row.get(key) is not None:
            value = str(row.get(key) or "").strip()
            if value:
                return value
    lookup = {str(k or "").strip().casefold(): v for k, v in row.items() if k is not None}
    for key in keys:
        value = lookup.get(str(key or "").strip().casefold())
        if value is not None:
            text = str(value or "").strip()
            if text:
                return text
    return ""




def remove_redundant_membership_level(value: Any, membership_level: Any, limit: int = 240) -> str:
    """Remove duplicated membership level text from imported membership detail fields.

    The old-site export often repeats the level inside product-like fields, e.g.
    "Full Membership - Annual Membership Renewal".  LROC stores the level in
    its own field, so the repeated prefix is redundant and makes the admin cards
    noisy.  This deliberately only removes exact case-insensitive level matches
    at the start/end or as a separated token, not arbitrary substrings inside
    unrelated words.
    """
    text = clean_text_field(value, limit)
    level = clean_text_field(membership_level, limit)
    if not text or not level:
        return text

    def norm(v: str) -> str:
        return re.sub(r"\s+", " ", v or "").strip().casefold()

    if norm(text) == norm(level):
        return ""

    # Prefix forms: "Full Membership - Annual Renewal", "Full Membership: Annual Renewal".
    prefix_re = re.compile(r"^" + re.escape(level) + r"\s*(?:[-–—:|/]+\s*)+", re.IGNORECASE)
    cleaned = prefix_re.sub("", text).strip()

    # Suffix forms: "Annual Renewal - Full Membership".
    suffix_re = re.compile(r"\s*(?:[-–—:|/]+\s*)+" + re.escape(level) + r"$", re.IGNORECASE)
    cleaned = suffix_re.sub("", cleaned).strip()

    # Repeated separated token inside a product string.
    token_re = re.compile(r"(?:^|\s*[-–—:|/]+\s*)" + re.escape(level) + r"(?:\s*[-–—:|/]+\s*|$)", re.IGNORECASE)
    cleaned = token_re.sub(" - ", cleaned).strip(" -–—:|/").strip()
    cleaned = re.sub(r"\s*[-–—:|/]\s*[-–—:|/]+\s*", " - ", cleaned).strip(" -–—:|/").strip()
    return cleaned[:limit]

def normalise_import_yes_no(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return text in {"y", "yes", "true", "1", "on", "historic", "approved"}


def normalise_import_money(value: Any) -> str:
    return clean_text_field(value, 32)


def normalise_import_vehicle(row: Dict[str, Any]) -> tuple[Dict[str, Any] | None, List[str]]:
    warnings: List[str] = []
    make = clean_vehicle_text(csv_value_any(row, "car #1 - make", "car #1 - make "), 64)
    model = clean_vehicle_text(csv_value_any(row, "car #1 - model"), 64)
    rego = clean_vehicle_text(csv_value_any(row, "car #1 - rego"), 32).upper().replace(" ", "")
    vin = clean_vehicle_text(csv_value_any(row, "car #1 - vin number"), 80).upper().replace(" ", "")
    year = clean_vehicle_text(csv_value_any(row, "car #1 - year of manufacture"), 16)
    created = clean_text_field(csv_value_any(row, "car #1 - created date"), 32)
    modified = clean_text_field(csv_value_any(row, "car #1 - last modified date"), 32)
    historic = normalise_import_yes_no(csv_value_any(row, "car #1 - is this a historic car"))

    if not any([make, model, rego, vin, year]):
        return None, warnings
    if year and not re.match(r"^\d{4}$", year):
        warnings.append(f"Car 1 year of manufacture {year} is not a four digit year; raw value will be preserved.")
    if not rego and not vin:
        warnings.append("Car 1 has no rego or VIN/chassis; it will still import but duplicate matching is less certain.")
    return {
        "make": make,
        "model": model,
        "variant": "",
        "fuel_type": "",
        "specific_build": "",
        "year": year,
        "rego_number": rego,
        "historic_classic": historic,
        "vin_serial_number": vin,
        "source": "member-form-data-import",
        "source_vehicle_slot": "car #1",
        "source_created_date": created,
        "source_last_modified_date": modified,
    }, warnings


def normalise_import_member_names(first_name: str, middle_name: str, last_name: str) -> tuple[str, str, str, List[str]]:
    """Clean member names from the v2 export.

    The old site export can repeat the last name in middle_name.  For example,
    Tony Edward Edward should import as Tony Edward with a blank middle name.
    """
    first = clean_text_field(first_name, 120)
    middle = clean_text_field(middle_name, 120)
    last = clean_text_field(last_name, 120)
    warnings: List[str] = []
    if middle and last and middle.strip().casefold() == last.strip().casefold():
        warnings.append("Middle name matched last name; middle name was cleared.")
        middle = ""
    return first, middle, last, warnings


def member_card_number_from_member_number(member_number: Any, raw_card_number: Any = "") -> tuple[str, List[str]]:
    """The usable club card number is the member_number.

    The new export includes a large legacy card_number, but the LROC card/display
    number is member_number.  We mirror member_number into card_number so older
    admin UI fields stay populated without advancing a separate legacy counter.
    """
    member = clean_text_field(member_number, 80)
    raw_card = clean_text_field(raw_card_number, 80)
    warnings: List[str] = []
    # The old-site card_number is a legacy/generated number that is not useful for
    # LROC.  Do not warn for every row; member_number is intentionally mirrored.
    return member, warnings


def normalise_member_contact_numbers(raw_mobile: str, raw_phone: str) -> tuple[str, str, List[str]]:
    """Normalise the new export mobile/phone fields into safe buckets.

    Any number that resolves to 614xxxxxxxx is stored as mobile.  Anything else
    that can be normalised is stored as phone.  This keeps future SMS code from
    ever trying to send messages to landlines simply because the source CSV used
    the wrong column.
    """
    warnings: List[str] = []
    mobile = ""
    phone = ""
    for label, raw_value in [("mobile", raw_mobile), ("phone", raw_phone)]:
        raw = str(raw_value or "").strip()
        if not raw:
            continue
        normalised, bucket, number_warnings = normalise_import_phone_number(raw)
        warnings.extend([f"{label} column: {w}" for w in number_warnings])
        if not normalised:
            continue
        if bucket == "mobile":
            if mobile and mobile != normalised:
                warnings.append(f"Additional mobile value {normalised} from {label} column was ignored; primary mobile is {mobile}.")
            else:
                mobile = normalised
            if label == "phone":
                warnings.append("Phone column contained a mobile number; stored in Mobile for future SMS safety.")
        else:
            if phone and phone != normalised:
                warnings.append(f"Additional phone value {normalised} from {label} column was ignored; primary phone is {phone}.")
            else:
                phone = normalised
            if label == "mobile":
                warnings.append("Mobile column did not contain an Australian mobile; stored in Phone instead.")
    return mobile, phone, warnings


def import_membership_type(level: str, product: str, full_product: str, member_type: str) -> str:
    text = " ".join([level, product, full_product, member_type]).lower()
    if "life" in text:
        return "life"
    return "standard" if text.strip() else ""


def import_membership_status(status: str, membership_type: str) -> str:
    if membership_type == "life":
        return "life"
    text = re.sub(r"\s+", "_", str(status or "").strip().lower())
    return text[:80]


def import_roles_from_membership(row: Dict[str, Any]) -> tuple[str, List[str]]:
    values = [
        csv_value_any(row, "membership - membership level", "membership_level"),
        csv_value_any(row, "membership - membership status", "membership_status"),
        csv_value_any(row, "membership - membership product", "membership_product"),
        csv_value_any(row, "member_type"),
    ]
    raw = " | ".join([v for v in values if v])
    roles: List[str] = []
    seen: set[str] = set()
    for value in values:
        for part in split_club_roles(value):
            key = part.lower()
            if key not in seen:
                seen.add(key)
                roles.append(part)
    return raw, roles


def parse_member_import_csv(csv_text: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    text = str(csv_text or "").lstrip("\ufeff")
    if not text.strip():
        raise ValueError("CSV text is required.")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    if "SiteMemberId" in headers or "Firstname" in headers:
        raise ValueError("This importer now expects the richer LROC member form export using member_number, first_name, membership - membership level and car #1 columns. The older SiteMemberId/Firstname CSV is no longer accepted.")
    missing = [h for h in MEMBER_IMPORT_REQUIRED_HEADERS if h not in headers]
    if missing:
        raise ValueError("Missing required CSV header(s): " + ", ".join(missing))
    rows: List[Dict[str, Any]] = []
    all_messages: List[Dict[str, Any]] = []
    seen_member_numbers: set[str] = set()
    seen_card_numbers: set[str] = set()
    seen_emails: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        errors: List[str] = []
        warnings: List[str] = []
        if row.get(None):
            errors.append("Extra CSV columns detected. Check for unquoted commas or tabs pasted into a CSV field.")
        raw_columns = {h: csv_value_any(row, h) for h in MEMBER_IMPORT_HEADERS}
        expected_lookup = {h.strip().casefold() for h in MEMBER_IMPORT_HEADERS}
        unexpected_headers = [h for h in headers if h is not None and h.strip().casefold() not in expected_lookup]
        if unexpected_headers:
            warnings.append("Unexpected CSV header(s) ignored: " + ", ".join(unexpected_headers[:8]) + ("…" if len(unexpected_headers) > 8 else ""))

        member_number = csv_value(row, "member_number")
        first_name, middle_name, last_name, name_warnings = normalise_import_member_names(
            csv_value(row, "first_name"),
            csv_value(row, "middle_name"),
            csv_value(row, "last_name"),
        )
        warnings.extend(name_warnings)
        title = csv_value(row, "title")
        username = csv_value(row, "username")
        card_number, card_warnings = member_card_number_from_member_number(member_number, csv_value(row, "card_number"))
        warnings.extend(card_warnings)
        party_id = csv_value(row, "party_id")
        raw_email = csv_value(row, "email")
        email, email_usable, email_warnings = normalise_import_email(raw_email)
        skip_reason = ""
        if not member_number:
            skip_reason = "No member_number; treated as an old/expired member and skipped."
        if not skip_reason and not first_name and not last_name and not email_usable:
            errors.append("first_name, last_name, or a usable email is required.")
        if not skip_reason:
            warnings.extend(email_warnings)
        if member_number and member_number in seen_member_numbers:
            errors.append("Duplicate member_number in this CSV.")
        if card_number and card_number in seen_card_numbers:
            warnings.append("Duplicate card_number in this CSV.")
        if email_usable and email in seen_emails:
            warnings.append("Duplicate email in this CSV; matching will update the same member.")
        if member_number:
            seen_member_numbers.add(member_number)
        if card_number:
            seen_card_numbers.add(card_number)
        if email_usable and email:
            seen_emails.add(email)

        dob_raw, dob_iso = parse_import_date(csv_value_any(row, "date_of_birth"))
        join_raw, join_iso = parse_import_date(csv_value_any(row, "membership - join date", "join_date"))
        level_start_raw, level_start_iso = parse_import_date(csv_value_any(row, "membership - level start date"))
        expiry_raw, expiry_iso = parse_import_date(csv_value_any(row, "membership - membership expiry", "expiry_date"))
        form_date_raw, form_date_iso = parse_import_date(csv_value_any(row, "Date"))
        for label, raw, iso in [("date_of_birth", dob_raw, dob_iso), ("join_date", join_raw, join_iso), ("membership_level_start_date", level_start_raw, level_start_iso), ("expiry_date", expiry_raw, expiry_iso), ("Date", form_date_raw, form_date_iso)]:
            if raw and not iso:
                warnings.append(f"{label} could not be parsed as DD/MM/YYYY; raw value will be preserved.")

        mobile, phone, phone_warnings = normalise_member_contact_numbers(csv_value_any(row, "mobile"), csv_value_any(row, "phone"))
        warnings.extend(phone_warnings)
        ice_raw = csv_value_any(row, "ice_phone_number")
        ice_phone, _ice_bucket, ice_warnings = normalise_import_phone_number(ice_raw)
        warnings.extend([f"ICE phone: {w}" for w in ice_warnings])

        roles_raw, roles = import_roles_from_membership(row)
        membership_level = clean_text_field(csv_value_any(row, "membership - membership level", "membership_level"), 120)
        membership_product_raw = csv_value_any(row, "membership - membership product", "membership_product")
        membership_product = remove_redundant_membership_level(membership_product_raw, membership_level, 180)
        current_full_product_name = remove_redundant_membership_level(membership_product_raw, membership_level, 240)
        member_type = remove_redundant_membership_level(csv_value_any(row, "member_type"), membership_level, 120)
        membership_type = import_membership_type(membership_level, membership_product, current_full_product_name, member_type)
        membership_status_raw = csv_value_any(row, "membership - membership status", "membership_status")
        membership_status = import_membership_status(membership_status_raw, membership_type)
        membership_expiry = "" if membership_type == "life" else expiry_iso
        membership_amount_paid = normalise_import_money(csv_value_any(row, "membership - amount paid"))
        membership_amount_outstanding = normalise_import_money(csv_value_any(row, "membership - amount outstanding"))
        approve_status = clean_text_field(csv_value_any(row, "approve"), 80)
        printed_magazine = normalise_printed_magazine(csv_value_any(row, "do you want to receive a printed copy of the magazine?"))
        import_agreement = clean_text_field(csv_value_any(row, "i agree"), 200)
        import_vehicle, vehicle_warnings = normalise_import_vehicle(row)
        warnings.extend(vehicle_warnings)

        display_name = " ".join([part for part in [title, first_name, middle_name, last_name] if part]).strip()
        if not display_name:
            display_name = email or username or member_number

        item = {
            "row_number": row_number,
            "raw": raw_columns,
            "site_member_id": member_number,
            "member_number": member_number,
            "card_number": card_number,
            "party_id": party_id,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "title": title,
            "name": display_name,
            "email": email,
            "email_raw": raw_email,
            "email_usable": email_usable,
            "invite_eligible": email_usable,
            "username": username,
            "gender": csv_value_any(row, "gender"),
            "date_of_birth_raw": dob_raw,
            "date_of_birth": dob_iso,
            "company_name": csv_value_any(row, "company_name"),
            "membership_level": membership_level,
            "membership_status_raw": membership_status_raw,
            "membership_status": membership_status,
            "membership_type": membership_type,
            "membership_product": membership_product,
            "current_full_product_name": current_full_product_name,
            "member_type": member_type,
            "member_created_date_raw": join_raw,
            "member_created_date": join_iso,
            "join_date_raw": join_raw,
            "join_date": join_iso,
            "expiry_date_raw": expiry_raw,
            "expiry_date": expiry_iso,
            "membership_expiry": membership_expiry,
            "membership_level_start_date_raw": level_start_raw,
            "membership_level_start_date": level_start_iso,
            "membership_amount_paid": membership_amount_paid,
            "membership_amount_outstanding": membership_amount_outstanding,
            "approve_status": approve_status,
            "printed_magazine": printed_magazine,
            "import_agreement": import_agreement,
            "form_updated_at_raw": form_date_raw,
            "form_updated_at": form_date_iso,
            "vehicle_count": 1 if import_vehicle else 0,
            "vehicles": [import_vehicle] if import_vehicle else [],
            "vehicle_summary": " | ".join([x for x in [
                (import_vehicle or {}).get("year", ""), (import_vehicle or {}).get("make", ""),
                (import_vehicle or {}).get("model", ""), (import_vehicle or {}).get("rego_number", "")
            ] if x]) if import_vehicle else "",
            "activated": membership_status not in {"expired", "cancelled", "inactive", "lapsed"},
            "club_roles_raw": roles_raw,
            "club_roles": roles,
            "address1": csv_value_any(row, "address1"),
            "address2": csv_value_any(row, "address2"),
            "city": csv_value_any(row, "city"),
            "state": csv_value_any(row, "state"),
            "country": csv_value_any(row, "country"),
            "postcode": csv_value_any(row, "postcode"),
            "postal_address1": csv_value_any(row, "postal_address1"),
            "postal_address2": csv_value_any(row, "postal_address2"),
            "postal_city": csv_value_any(row, "postal_city"),
            "postal_state": csv_value_any(row, "postal_state"),
            "postal_country": csv_value_any(row, "postal_country"),
            "postal_postcode": csv_value_any(row, "postal_postcode"),
            "profile_image": csv_value_any(row, "profile_image"),
            "ice_name": csv_value_any(row, "ice_name"),
            "ice_phone_raw": ice_raw,
            "ice_phone_number": ice_phone,
            "dietary_requirements_allergies": csv_value_any(row, "dietary_requirements_allergies"),
            "primary_first_name": csv_value_any(row, "primary_first_name"),
            "primary_last_name": csv_value_any(row, "primary_last_name"),
            "primary_member_number": csv_value_any(row, "primary_member_number"),
            "mobile": mobile,
            "phone": phone,
            "phone_raw": " / ".join([x for x in [csv_value_any(row, "mobile"), csv_value_any(row, "phone")] if x]),
            "phone_bucket": "mobile" if mobile and not phone else ("phone" if phone and not mobile else ("mobile+phone" if mobile and phone else "")),
            "skip_reason": skip_reason,
            "errors": errors,
            "warnings": warnings,
        }
        if skip_reason:
            item["warnings"] = [skip_reason] + item["warnings"]
        if errors or warnings or skip_reason or not email_usable:
            all_messages.append({
                "row_number": row_number,
                "site_member_id": member_number,
                "member_number": member_number,
                "card_number": card_number,
                "email": email,
                "email_raw": raw_email,
                "errors": errors,
                "warnings": item["warnings"],
            })
        rows.append(item)
    return rows, all_messages

def classify_import_row(row: Dict[str, Any]) -> Dict[str, Any]:
    existing_user = find_cognito_user_by_email(row.get("email", "")) if row.get("email_usable") and row.get("email") else None
    if existing_user:
        summary = format_user_summary(existing_user)
        return {"action": "update_cognito_member", "sub": summary["sub"], "username": summary.get("username") or summary.get("email") or "", "email": summary.get("email") or row.get("email") or ""}

    # Imported records use a deterministic key, so check that directly first.
    # This avoids scanning the metadata table once for every row during re-imports.
    existing_imported = get_imported_member_metadata_by_site_member_id(row.get("site_member_id", ""))
    if existing_imported:
        sub = str(existing_imported.get("sub") or "").strip()
        return {"action": "update_imported_member", "sub": sub, "username": str(existing_imported.get("username") or row.get("username") or ""), "email": str(existing_imported.get("email") or row.get("email") or "")}

    # Fallback for rare older/manual records that have a SiteMemberId attached to
    # an existing Cognito-backed profile but no matching email.
    existing_meta = get_metadata_by_site_member_id(row.get("site_member_id", ""))
    if existing_meta:
        sub = str(existing_meta.get("sub") or "").strip()
        return {"action": "update_imported_member" if sub.startswith(IMPORTED_MEMBER_SUB_PREFIX) else "update_existing_metadata", "sub": sub, "username": str(existing_meta.get("username") or row.get("username") or ""), "email": str(existing_meta.get("email") or row.get("email") or "")}
    return {"action": "create_imported_member", "sub": IMPORTED_MEMBER_SUB_PREFIX + str(row.get("site_member_id") or "").strip(), "username": row.get("username") or row.get("email") or "", "email": row.get("email") or ""}



def import_history_key(batch_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": "ADMIN#MEMBER_IMPORTS"}, "sk": {"S": f"IMPORT#{batch_id}"}}


def save_member_import_history(batch_id: str, claims: Dict[str, Any], *, started_at: str | None = None, finished_at: str | None = None, counts: Dict[str, Any] | None = None, source: str = "member-form-data-csv-v1") -> Dict[str, Any]:
    require_metadata_table()
    batch = str(batch_id or "").strip()
    if not batch:
        return {}
    key = import_history_key(batch)
    existing_resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=key, ConsistentRead=True)
    existing = item_to_python(existing_resp.get("Item", {})) if existing_resp.get("Item") else {}
    now = utc_now()
    import_started = str(started_at or existing.get("import_started_at") or now)
    item = {
        "pk": "ADMIN#MEMBER_IMPORTS",
        "sk": f"IMPORT#{batch}",
        "item_type": "member_import_history",
        "import_batch_id": batch,
        "import_source": source,
        "import_started_at": import_started,
        "recovery_restore_time": str(existing.get("recovery_restore_time") or import_started),
        "updated_at": now,
        "updated_by": str(claims.get("email") or claims.get("sub") or "admin"),
    }
    if finished_at:
        item["import_finished_at"] = finished_at
    elif existing.get("import_finished_at"):
        item["import_finished_at"] = existing.get("import_finished_at")
    merged_counts = dict(existing.get("counts") or {}) if isinstance(existing.get("counts"), dict) else {}
    if counts:
        for k, v in counts.items():
            try:
                merged_counts[str(k)] = int(v)
            except Exception:
                merged_counts[str(k)] = str(v)
    if merged_counts:
        item["counts"] = merged_counts
        item["members_processed"] = int(merged_counts.get("processed") or merged_counts.get("created", 0) + merged_counts.get("updated", 0) or 0)
        item["members_created"] = int(merged_counts.get("created") or 0)
        item["members_updated"] = int(merged_counts.get("updated") or 0)
        item["vehicles_processed"] = int(merged_counts.get("vehicles") or 0)
        item["rows_skipped_no_member_number"] = int(merged_counts.get("skipped_expired") or 0)
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return item


def list_member_import_history(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    require_metadata_table()
    items: List[Dict[str, Any]] = []
    next_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": "ADMIN#MEMBER_IMPORTS"}, ":prefix": {"S": "IMPORT#"}},
            "ScanIndexForward": False,
            "Limit": 25,
        }
        if next_key:
            kwargs["ExclusiveStartKey"] = next_key
        resp = ddb.query(**kwargs)
        for raw in resp.get("Items", []):
            item = item_to_python(raw)
            counts = item.get("counts") if isinstance(item.get("counts"), dict) else {}
            items.append({
                "import_batch_id": str(item.get("import_batch_id") or ""),
                "import_source": str(item.get("import_source") or ""),
                "import_started_at": str(item.get("import_started_at") or ""),
                "import_finished_at": str(item.get("import_finished_at") or ""),
                "recovery_restore_time": str(item.get("recovery_restore_time") or item.get("import_started_at") or ""),
                "members_processed": int(item.get("members_processed") or counts.get("processed") or 0),
                "members_created": int(item.get("members_created") or counts.get("created") or 0),
                "members_updated": int(item.get("members_updated") or counts.get("updated") or 0),
                "vehicles_processed": int(item.get("vehicles_processed") or counts.get("vehicles") or 0),
                "rows_skipped_no_member_number": int(item.get("rows_skipped_no_member_number") or counts.get("skipped_expired") or 0),
            })
        next_key = resp.get("LastEvaluatedKey")
        if not next_key or len(items) >= 25:
            break
    return response(200, {"items": items[:25]})


def member_import_preview(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    rows, messages = parse_member_import_csv(str(body.get("csv_text") or body.get("csvText") or ""))
    issue_items: List[Dict[str, Any]] = []
    counts = {"rows": len(rows), "previewed": 0, "skipped_expired": 0, "errors": 0, "warnings": 0, "new_members": 0, "updates": 0, "no_email": 0, "email_issues": 0, "mobiles": 0, "phones": 0, "vehicles": 0}
    existing_site_ids = existing_site_member_id_set()
    for row in rows:
        if row.get("skip_reason"):
            counts["skipped_expired"] += 1
            # Rows without member_number are intentionally quiet. They are old/non-importable
            # export rows and should not clutter the import analysis.
            continue
        if row["errors"]:
            action = "blocked"
        elif row.get("site_member_id") in existing_site_ids:
            action = "update_existing_site_member_id"
        else:
            action = "create_imported_member"
        counts["previewed"] += 1
        if row["errors"]:
            counts["errors"] += 1
        if row["warnings"]:
            counts["warnings"] += 1
        if not row.get("email_usable"):
            counts["no_email"] += 1
            counts["email_issues"] += 1
        if row.get("mobile"):
            counts["mobiles"] += 1
        if row.get("phone"):
            counts["phones"] += 1
        if row.get("vehicles"):
            counts["vehicles"] += len(row.get("vehicles") or [])
        if action == "create_imported_member":
            counts["new_members"] += 1
        elif action != "blocked":
            counts["updates"] += 1
        # Do not return the full valid import list. Only records that need attention
        # are returned for the issues CSV/admin display.
        if row["errors"]:
            preview_item = dict(row)
            preview_item["action"] = action
            preview_item["roles_raw"] = row.get("club_roles_raw", "")
            preview_item["roles"] = row.get("club_roles", [])
            issue_items.append(preview_item)
    return response(200, {"counts": counts, "items": issue_items, "messages": messages, "can_commit": counts["errors"] == 0})


def member_import_commit(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    body = parse_body(event)
    confirm = str(body.get("confirm") or "").strip().upper()
    if confirm != "IMPORT":
        raise ValueError("confirm must be IMPORT.")
    rows, _messages = parse_member_import_csv(str(body.get("csv_text") or body.get("csvText") or ""))
    bad_rows = [row for row in rows if row["errors"]]
    if bad_rows:
        raise ValueError(f"Import blocked: {len(bad_rows)} row(s) have errors. Run preview and fix the CSV first.")

    # Import in small chunks.  The frontend calls this endpoint repeatedly so API Gateway
    # does not time out on larger member lists while Cognito/DynamoDB lookups are performed.
    try:
        offset = max(0, int(body.get("offset") or 0))
    except Exception:
        offset = 0
    try:
        limit = int(body.get("limit") or body.get("batch_size") or body.get("batchSize") or 25)
    except Exception:
        limit = 25
    limit = min(max(limit, 1), 50)

    importable_rows = [row for row in rows if not row.get("skip_reason")]
    skipped_expired_total = sum(1 for row in rows if row.get("skip_reason"))
    total_importable = len(importable_rows)
    batch_id = str(body.get("batch_id") or body.get("batchId") or "").strip()
    if not batch_id:
        batch_id = "import-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)

    imported_by = claims.get("email") or claims.get("sub") or "admin"
    if offset == 0:
        save_member_import_history(batch_id, claims, started_at=utc_now(), counts={"rows": len(rows), "previewed": total_importable, "skipped_expired": skipped_expired_total}, source="member-form-data-csv-v1")
    counts = {"created": 0, "updated": 0, "skipped": 0, "skipped_expired": 0, "no_email": 0, "email_issues": 0, "mobiles": 0, "phones": 0, "vehicles": 0, "vehicles_updated": 0, "processed": 0, "total": total_importable}
    items: List[Dict[str, Any]] = []
    chunk = importable_rows[offset:offset + limit]
    for row in chunk:
        classification = classify_import_row(row)
        sub = classification["sub"]
        if not sub:
            counts["skipped"] += 1
            continue
        is_imported_only = classification["action"] == "create_imported_member" or sub.startswith(IMPORTED_MEMBER_SUB_PREFIX)
        existing_metadata = get_member_metadata(sub) if not is_imported_only else {}
        # The CSV import should not mark already-active Cognito members as needing an invite.
        # "Invited" means "does this member still require the later invite flow?"
        # Imported-only members start as N; existing/linked Cognito members are already through that gate.
        if is_imported_only:
            invited_value = "N"
        else:
            invited_value = "Y"
        if str(existing_metadata.get("invited") or "").strip().upper() == "Y":
            invited_value = "Y"
        payload = {
            "site_member_id": row["site_member_id"],
            "first_name": row["first_name"],
            "middle_name": row.get("middle_name", ""),
            "last_name": row["last_name"],
            "title": row.get("title", ""),
            "name": row["name"],
            "email": row["email"],
            "email_raw": row.get("email_raw", ""),
            "email_usable": bool(row.get("email_usable")),
            "invite_eligible": bool(row.get("invite_eligible")),
            "username": row["username"] or classification.get("username") or row["email"] or row["site_member_id"],
            "gender": row.get("gender", ""),
            "date_of_birth_raw": row.get("date_of_birth_raw", ""),
            "date_of_birth": row.get("date_of_birth", ""),
            "company_name": row.get("company_name", ""),
            "membership_type": row.get("membership_type", ""),
            "membership_status": row.get("membership_status", ""),
            "membership_expiry": row.get("membership_expiry", ""),
            "membership_level": row.get("membership_level", ""),
            "membership_product": row.get("membership_product", ""),
            "current_full_product_name": row.get("current_full_product_name", ""),
            "membership_amount_paid": row.get("membership_amount_paid", ""),
            "membership_amount_outstanding": row.get("membership_amount_outstanding", ""),
            "membership_level_start_date_raw": row.get("membership_level_start_date_raw", ""),
            "membership_level_start_date": row.get("membership_level_start_date", ""),
            "approve_status": row.get("approve_status", ""),
            "printed_magazine": row.get("printed_magazine", ""),
            "import_agreement": row.get("import_agreement", ""),
            "form_updated_at_raw": row.get("form_updated_at_raw", ""),
            "form_updated_at": row.get("form_updated_at", ""),
            "member_created_date_raw": row["member_created_date_raw"],
            "member_created_date": row["member_created_date"],
            "join_date_raw": row.get("join_date_raw", ""),
            "join_date": row.get("join_date", ""),
            "expiry_date_raw": row.get("expiry_date_raw", ""),
            "expiry_date": row.get("expiry_date", ""),
            "card_number": row.get("card_number", ""),
            "party_id": row.get("party_id", ""),
            "member_type": row.get("member_type", ""),
            "primary_first_name": row.get("primary_first_name", ""),
            "primary_last_name": row.get("primary_last_name", ""),
            "primary_member_number": row.get("primary_member_number", ""),
            "profile_image": row.get("profile_image", ""),
            "ice_name": row.get("ice_name", ""),
            "ice_phone_number": row.get("ice_phone_number", ""),
            "ice_phone_raw": row.get("ice_phone_raw", ""),
            "dietary_requirements_allergies": row.get("dietary_requirements_allergies", ""),
            "activated": row["activated"],
            "club_roles_raw": row["club_roles_raw"],
            "club_roles": row["club_roles"],
            "address1": row["address1"],
            "address2": row["address2"],
            "city": row["city"],
            "state": row["state"],
            "country": row.get("country", ""),
            "postcode": row["postcode"],
            "postal_address1": row.get("postal_address1", ""),
            "postal_address2": row.get("postal_address2", ""),
            "postal_city": row.get("postal_city", ""),
            "postal_state": row.get("postal_state", ""),
            "postal_country": row.get("postal_country", ""),
            "postal_postcode": row.get("postal_postcode", ""),
            "mobile": row["mobile"],
            "phone": row["phone"],
            "import_batch_id": batch_id,
            "imported_at": utc_now(),
            "imported_by": imported_by,
            "import_source": "member-form-data-csv-v1",
            "invited": invited_value,
            "imported_member": is_imported_only,
        }
        advance_member_number_counter_at_least(payload.get("site_member_id"))
        if classification["action"] == "update_cognito_member":
            payload["cognito_sub"] = sub
            payload["cognito_username"] = classification.get("username") or ""
            if classification.get("email"):
                payload["email"] = classification["email"]
        metadata = save_member_metadata(sub, payload, claims, account_status="active")
        saved_vehicles: List[Dict[str, Any]] = []
        for vehicle in row.get("vehicles") or []:
            result = save_imported_member_vehicle(sub, row.get("member_number") or row.get("site_member_id") or "", vehicle, claims, batch_id)
            if result.get("saved"):
                saved_vehicles.append(result)
                counts["vehicles"] += 1
                if result.get("updated"):
                    counts["vehicles_updated"] += 1
        items.append({"sub": sub, "site_member_id": row["site_member_id"], "email": payload.get("email", ""), "name": row["name"], "action": classification["action"], "invited": metadata.get("invited", "N"), "vehicles": saved_vehicles})
        if not row.get("email_usable"):
            counts["no_email"] += 1
            counts["email_issues"] += 1
        if row.get("mobile"):
            counts["mobiles"] += 1
        if row.get("phone"):
            counts["phones"] += 1
        if classification["action"] == "create_imported_member":
            counts["created"] += 1
        else:
            counts["updated"] += 1
        counts["processed"] += 1

    next_offset = offset + len(chunk)
    complete = next_offset >= total_importable
    counts["skipped_expired"] = skipped_expired_total if complete else 0
    history_counts = dict(counts)
    history_counts["rows"] = len(rows)
    history_counts["previewed"] = total_importable
    save_member_import_history(batch_id, claims, finished_at=utc_now() if complete else None, counts=history_counts, source="member-form-data-csv-v1")
    message = "Member CSV import complete." if complete else "Member CSV import chunk complete."
    return response(200, {
        "message": message,
        "batch_id": batch_id,
        "counts": counts,
        "items": items,
        "offset": offset,
        "next_offset": next_offset,
        "limit": limit,
        "total": total_importable,
        "complete": complete,
    })


def rollback_uninvited_imported_members(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    raise ValueError("In-app member import rollback is disabled. Use DynamoDB PITR recovery from the stored import start time, then rerun the CSV import.")


def chat_room_pk(room_id: str) -> str:
    clean_room_id = str(room_id or "").strip()
    if not clean_room_id:
        clean_room_id = "general-chat"
    return f"ROOM#{clean_room_id}"


def chat_room_meta_key(room_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": chat_room_pk(room_id)}, "sk": {"S": "META"}}


def chat_room_membership_key(room_id: str, sub: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": chat_room_pk(room_id)}, "sk": {"S": f"MEMBER#{sub}"}}


def user_pk(sub: str) -> str:
    return f"USER#{sub}"


def push_subscription_key(sub: str, endpoint_hash: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": user_pk(sub)}, "sk": {"S": f"PUSH#{endpoint_hash}"}}


def hash_endpoint(endpoint: str) -> str:
    return hashlib.sha256(str(endpoint or "").encode("utf-8")).hexdigest()[:32]


def list_push_subscriptions_for_user(sub: str, *, active_only: bool = False) -> List[Dict[str, Any]]:
    require_chat_table()
    items=[]
    start_key=None
    while True:
        kwargs={
            "TableName": CHAT_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {
                ":pk": {"S": user_pk(sub)},
                ":prefix": {"S": "PUSH#"},
            },
        }
        if start_key:
            kwargs["ExclusiveStartKey"]=start_key
        resp=ddb.query(**kwargs)
        items.extend(item_to_python(item) for item in resp.get("Items", []))
        start_key=resp.get("LastEvaluatedKey")
        if not start_key:
            break
    if active_only:
        items = [item for item in items if is_push_subscription_item_active(item)]
    return items


def is_push_subscription_item_active(item: Dict[str, Any]) -> bool:
    if not item:
        return False
    if item.get("active") is False:
        return False
    status = str(item.get("push_subscription_status") or item.get("status") or "active").strip().lower()
    if status in {"inactive", "expired", "gone", "dead", "unsubscribed", "disabled"}:
        return False
    subscription = item.get("subscription") if isinstance(item.get("subscription"), dict) else {}
    keys = subscription.get("keys") if isinstance(subscription.get("keys"), dict) else {}
    return bool(str(subscription.get("endpoint") or "").strip() and str(keys.get("p256dh") or "").strip() and str(keys.get("auth") or "").strip())


def save_push_subscription(sub: str, claims: Dict[str, Any], subscription: Dict[str, Any], vapid_public_key: str = "") -> Dict[str, Any]:
    require_chat_table()
    endpoint = str(subscription.get("endpoint") or "").strip()
    keys = subscription.get("keys") or {}
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        raise ValueError("A complete push subscription is required.")
    endpoint_hash = hash_endpoint(endpoint)
    now = utc_now_precise()
    existing: Dict[str, Any] = {}
    try:
        resp = ddb.get_item(TableName=CHAT_TABLE, Key=push_subscription_key(sub, endpoint_hash), ConsistentRead=True)
        existing = item_to_python(resp.get("Item", {})) if resp.get("Item") else {}
    except Exception:
        existing = {}
    payload = {
        "pk": user_pk(sub),
        "sk": f"PUSH#{endpoint_hash}",
        "type": "PUSH_SUBSCRIPTION",
        "user_sub": sub,
        "endpoint_hash": endpoint_hash,
        "endpoint": endpoint,
        "subscription": {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        },
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
        "last_seen_at": now,
        "last_registered_at": now,
        "active": True,
        "push_subscription_status": "active",
        "display_name": get_member_display_label(claims),
        "email": str(claims.get("email") or "").strip(),
    }
    if existing.get("last_success_at"):
        payload["last_success_at"] = str(existing.get("last_success_at"))
    vapid_public_key = str(vapid_public_key or "").strip()
    if vapid_public_key:
        payload["vapid_public_key_hash"] = hashlib.sha256(vapid_public_key.encode("utf-8")).hexdigest()
    ddb.put_item(TableName=CHAT_TABLE, Item=python_to_item(payload))
    return payload


def remove_push_subscription(sub: str, endpoint: str) -> None:
    require_chat_table()
    endpoint_hash = hash_endpoint(endpoint)
    ddb.delete_item(TableName=CHAT_TABLE, Key=push_subscription_key(sub, endpoint_hash))


def list_joined_room_memberships(room_id: str) -> List[Dict[str, Any]]:
    require_chat_table()
    items=[]
    start_key=None
    while True:
        kwargs={
            "TableName": CHAT_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {
                ":pk": {"S": chat_room_pk(room_id)},
                ":prefix": {"S": "MEMBER#"},
            },
        }
        if start_key:
            kwargs["ExclusiveStartKey"]=start_key
        resp=ddb.query(**kwargs)
        for item in resp.get("Items", []):
            value=item_to_python(item)
            if str(value.get("state") or "").strip().lower()=="joined":
                items.append(value)
        start_key=resp.get("LastEvaluatedKey")
        if not start_key:
            break
    return items


def enqueue_chat_notification(room: Dict[str, Any], message: Dict[str, Any]) -> None:
    if not CHAT_NOTIFICATION_QUEUE_URL:
        return
    if bool(message.get("system")) and not bool(message.get("notify_members")):
        return
    payload = {
        "type": "chat_message",
        "room_id": str(room.get("room_id") or ""),
        "room_title": str(room.get("title") or room.get("room_id") or "Chat"),
        "required_any_groups": [str(x).strip() for x in (room.get("required_any_groups") or []) if str(x).strip()],
        "sender_sub": str(message.get("author_sub") or ""),
        "sender_label": str(message.get("author_label") or "Member"),
        # Keep sender included by default so single-user/self tests behave like SGARS.
        "include_sender": bool(message.get("include_sender", True)),
        "body": str(message.get("body") or ""),
        "created_at": str(message.get("created_at") or utc_now_precise()),
    }
    sqs.send_message(QueueUrl=CHAT_NOTIFICATION_QUEUE_URL, MessageBody=json.dumps(payload))


def enqueue_direct_push_notification(user_sub: str, title: str, body: str, data: Dict[str, Any] | None = None, tag: str = "lroc-notification") -> bool:
    """Queue a direct PWA push notification for a single Cognito user subject."""
    user_sub = str(user_sub or "").strip()
    if not user_sub or not CHAT_NOTIFICATION_QUEUE_URL:
        return False
    payload = {
        "type": str(tag or "direct_notification"),
        "user_sub": user_sub,
        "title": str(title or "LROC notification"),
        "body": str(body or ""),
        "tag": str(tag or "lroc-notification"),
        "data": dict(data or {}),
        "created_at": utc_now_precise(),
    }
    sqs.send_message(QueueUrl=CHAT_NOTIFICATION_QUEUE_URL, MessageBody=json.dumps(payload))
    return True


def usable_push_subscription_exists(user_sub: str) -> bool:
    user_sub = str(user_sub or "").strip()
    if not user_sub or not CHAT_TABLE:
        return False
    try:
        for item in list_push_subscriptions_for_user(user_sub, active_only=True):
            subscription = item.get("subscription") if isinstance(item.get("subscription"), dict) else {}
            keys = subscription.get("keys") if isinstance(subscription.get("keys"), dict) else {}
            if str(subscription.get("endpoint") or "").strip() and str(keys.get("p256dh") or "").strip() and str(keys.get("auth") or "").strip():
                return True
    except Exception:
        return False
    return False


def add_months_to_date(value: Any, months: int) -> Any:
    months = max(1, int(months or 1))
    year = value.year + ((value.month - 1 + months) // 12)
    month = ((value.month - 1 + months) % 12) + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)



def vehicle_registration_reminder_key(sub: str, vehicle_id: str, expiry_date: str, notice_kind: str, notice_date: str) -> Dict[str, Dict[str, str]]:
    safe_kind = re.sub(r"[^A-Za-z0-9_-]+", "_", str(notice_kind or "reminder"))[:40]
    return {
        "pk": {"S": member_pk(sub)},
        "sk": {"S": f"REMINDER#VEHICLE_REGISTRATION#{vehicle_id}#{expiry_date}#{safe_kind}#{notice_date}"},
    }


def mark_vehicle_registration_reminder_sent(sub: str, vehicle_id: str, expiry_date: str, notice_kind: str, notice_date: str, triggered_by: str) -> bool:
    """Create a once-only reminder marker. Returns False if this notice was already sent."""
    require_metadata_table()
    now = utc_now()
    item = {
        "pk": member_pk(sub),
        "sk": f"REMINDER#VEHICLE_REGISTRATION#{vehicle_id}#{expiry_date}#{re.sub(r'[^A-Za-z0-9_-]+', '_', str(notice_kind or 'reminder'))[:40]}#{notice_date}",
        "item_type": "vehicle_registration_reminder",
        "member_sub": sub,
        "vehicle_id": vehicle_id,
        "registration_expiry_date": expiry_date,
        "notice_kind": str(notice_kind or "reminder"),
        "notice_date": str(notice_date or ""),
        "triggered_by": str(triggered_by or "scheduler"),
        "sent_at": now,
        "created_at": now,
    }
    try:
        ddb.put_item(
            TableName=MEMBER_METADATA_TABLE,
            Item=python_to_item(item),
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def scan_vehicle_registration_candidates() -> List[Dict[str, Any]]:
    require_metadata_table()
    items: List[Dict[str, Any]] = []
    start_key = None
    while True:
        kwargs = {
            "TableName": MEMBER_METADATA_TABLE,
            "FilterExpression": "begins_with(#sk, :vehicle_prefix) AND attribute_exists(#expiry) AND #expiry <> :blank",
            "ExpressionAttributeNames": {"#sk": "sk", "#expiry": "registration_expiry_date"},
            "ExpressionAttributeValues": {":vehicle_prefix": {"S": "VEHICLE#"}, ":blank": {"S": ""}},
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        resp = ddb.scan(**kwargs)
        items.extend(item_to_python(item) for item in resp.get("Items", []))
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            break
    return items


def scan_vehicles_due_for_registration_reminder(target_date: Any) -> List[Dict[str, Any]]:
    # Backwards-compatible helper retained for manual/testing callers.
    target_text = target_date.isoformat()
    return [item for item in scan_vehicle_registration_candidates() if clean_vehicle_text(item.get("registration_expiry_date"), 10) == target_text]


def vehicle_reminder_title(vehicle: Dict[str, Any]) -> str:
    parts = [str(vehicle.get(key) or "").strip() for key in ["year", "make", "model", "variant"]]
    title = " ".join(part for part in parts if part)
    rego = str(vehicle.get("rego_number") or "").strip()
    if rego:
        title = f"{title} ({rego})" if title else rego
    return title or "your vehicle"


def is_vehicle_registration_reminder_active(vehicle: Dict[str, Any]) -> bool:
    if normalise_vehicle_status(vehicle.get("vehicle_status") or vehicle.get("status") or "active") == "disposed":
        return False
    if vehicle.get("registration_reminders_enabled") is False:
        return False
    if clean_vehicle_text(vehicle.get("registration_reminder_status"), 40) == "stopped":
        return False
    return True


def determine_vehicle_registration_notice(vehicle: Dict[str, Any], today: Any, target_date: Any) -> Dict[str, Any] | None:
    expiry = parse_vehicle_expiry_date(vehicle.get("registration_expiry_date"))
    if not expiry or not is_vehicle_registration_reminder_active(vehicle):
        return None
    expiry_text = expiry.isoformat()
    final_notice_date = add_months_to_date(expiry, VEHICLE_REGISTRATION_FINAL_NOTICE_MONTHS_AFTER)
    final_sent = bool(clean_vehicle_text(vehicle.get("registration_final_notice_sent_at"), 32)) or clean_vehicle_text(vehicle.get("registration_reminders_stopped_reason"), 80) == "expired_more_than_3_months"

    if today >= final_notice_date and not final_sent:
        return {
            "kind": "final_notice",
            "notice_date": today.isoformat(),
            "title": "Vehicle registration final notice",
            "body": VEHICLE_REGISTRATION_FINAL_NOTICE_TEXT,
            "next_reminder_date": "",
            "status": "stopped",
            "stop_reason": "expired_more_than_3_months",
            "expiry_text": expiry_text,
        }

    if expiry == target_date and not clean_vehicle_text(vehicle.get("registration_last_reminder_sent_at"), 32):
        if ENABLE_HISTORIC_REGISTRATION_REMINDERS and bool(vehicle.get("historic_classic")):
            return {
                "kind": "historic_classic_due_soon",
                "notice_date": today.isoformat(),
                "title": "Historic / Classic registration due soon",
                "body": HISTORIC_REGO_RENEWAL_NOTICE_TEXT or f"Historic / Classic registration for {vehicle_reminder_title(vehicle)} expires on {expiry_text}. Please submit the registration pack through the LROC Vehicle Registration page.",
                "next_reminder_date": expiry_text,
                "status": "pending_confirmation",
                "expiry_text": expiry_text,
            }
        return {
            "kind": "due_soon",
            "notice_date": today.isoformat(),
            "title": "Vehicle registration due soon",
            "body": f"Registration for {vehicle_reminder_title(vehicle)} expires on {expiry_text}. Tap to confirm when renewed, defer, or mark it no longer owned.",
            "next_reminder_date": expiry_text,
            "status": "pending_confirmation",
            "expiry_text": expiry_text,
        }

    next_text = clean_vehicle_text(vehicle.get("registration_next_reminder_date"), 10)
    next_date = parse_vehicle_expiry_date(next_text) if next_text else expiry
    if today >= expiry and today >= next_date and today < final_notice_date:
        return {
            "kind": "renewal_check",
            "notice_date": today.isoformat(),
            "title": "Vehicle registration renewal check",
            "body": f"Has registration for {vehicle_reminder_title(vehicle)} been renewed? Tap to update the vehicle registry or defer this reminder.",
            "next_reminder_date": add_months_to_date(today, 1).isoformat(),
            "status": "pending_confirmation",
            "expiry_text": expiry_text,
        }
    return None


def apply_vehicle_registration_notice_state(vehicle: Dict[str, Any], notice: Dict[str, Any], triggered_by: str) -> None:
    now = utc_now()
    vehicle["registration_reminders_enabled"] = notice.get("status") != "stopped"
    vehicle["registration_reminder_status"] = str(notice.get("status") or "pending_confirmation")
    vehicle["registration_next_reminder_date"] = str(notice.get("next_reminder_date") or "")
    vehicle["registration_last_reminder_sent_at"] = now
    vehicle["registration_reminder_count"] = int(vehicle.get("registration_reminder_count") or 0) + 1
    if notice.get("kind") == "final_notice":
        vehicle["registration_final_notice_sent_at"] = now
        vehicle["registration_reminders_stopped_reason"] = str(notice.get("stop_reason") or "expired_more_than_3_months")
    vehicle["updated_at"] = now
    vehicle["updated_by"] = str(triggered_by or "scheduler")
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(vehicle))


def vehicle_registration_email_url(vehicle_id: str) -> str:
    path = f"/profile.html?registration_vehicle_id={vehicle_id}#vehicles"
    if SITE_BASE_URL:
        return f"{SITE_BASE_URL}{path}"
    return path


def historic_registration_page_url() -> str:
    path = "/historic-registration.html"
    if SITE_BASE_URL:
        return f"{SITE_BASE_URL}{path}"
    return path


def build_vehicle_registration_reminder_email(member: Dict[str, Any], vehicle: Dict[str, Any], notice: Dict[str, Any]) -> Dict[str, str]:
    vehicle_title = vehicle_reminder_title(vehicle)
    expiry = str(notice.get("expiry_text") or vehicle.get("registration_expiry_date") or "").strip()
    notice_kind = str(notice.get("kind") or "reminder")
    if notice_kind == "final_notice":
        subject = f"LROC vehicle registration final notice - {vehicle_title}"
        intro = str(notice.get("body") or VEHICLE_REGISTRATION_FINAL_NOTICE_TEXT)
        url = vehicle_registration_email_url(str(vehicle.get("vehicle_id") or ""))
        action_text = "Open My Vehicles to confirm the registration has been renewed, ask to be reminded again in one month, or mark the vehicle as no longer owned."
        link_text = f"My Vehicles: {url}"
    elif notice_kind == "renewal_check":
        subject = f"LROC vehicle registration renewal check - {vehicle_title}"
        intro = str(notice.get("body") or f"Has registration for {vehicle_title} been renewed?")
        url = vehicle_registration_email_url(str(vehicle.get("vehicle_id") or ""))
        action_text = "Open My Vehicles to confirm the registration has been renewed, ask to be reminded again in one month, or mark the vehicle as no longer owned."
        link_text = f"My Vehicles: {url}"
    elif notice_kind == "historic_classic_due_soon":
        subject = f"LROC Historic / Classic registration renewal - {vehicle_title}"
        intro = str(notice.get("body") or HISTORIC_REGO_RENEWAL_NOTICE_TEXT or f"Historic / Classic registration for {vehicle_title} expires on {expiry}.")
        url = historic_registration_page_url()
        action_text = "Open the Vehicle Registration page to submit your inspection certificate and required vehicle photos to the Historic Registrar. The Registrar will review the submission and complete the offline club process."
        link_text = f"Vehicle Registration page: {url}"
    else:
        subject = f"LROC vehicle registration due soon - {vehicle_title}"
        intro = str(notice.get("body") or f"Registration for {vehicle_title} expires on {expiry}.")
        url = vehicle_registration_email_url(str(vehicle.get("vehicle_id") or ""))
        action_text = "Open My Vehicles to confirm the registration has been renewed, ask to be reminded again in one month, or mark the vehicle as no longer owned."
        link_text = f"My Vehicles: {url}"
    paragraphs = [
        intro,
        action_text,
        link_text,
    ]
    rows = [
        ("Member number", member_number_from_metadata(member)),
        ("Vehicle", vehicle_title),
        ("Registration number", str(vehicle.get("rego_number") or "").strip()),
        ("Registration expiry", expiry),
        ("Notice type", notice_kind.replace("_", " ").title()),
    ]
    text = "Land Rover Owners Club of Australia Inc\n\n" + "\n\n".join(paragraphs) + "\n\n" + "\n".join(f"{label}: {value or 'Not supplied'}" for label, value in rows)
    html_body = simple_html_email(subject, paragraphs, rows)
    return {"subject": subject, "text": text, "html": html_body}


def send_vehicle_registration_reminder_email(user_sub: str, vehicle: Dict[str, Any], notice: Dict[str, Any]) -> Dict[str, Any]:
    if not ses_email_available():
        return {"sent": False, "skipped": True, "reason": "ses_not_configured"}
    member = get_member_metadata(user_sub)
    to_email = member_email_from_metadata(member)
    if not to_email:
        return {"sent": False, "skipped": True, "reason": "member_email_not_configured"}
    guard = system_email_guard_status({**member, "sub": user_sub, "user_sub": user_sub, "email": to_email}, context="vehicle_registration_reminder")
    if not guard.get("allowed"):
        return {"sent": False, "skipped": True, "reason": str(guard.get("reason") or "system_email_guard"), "email_guard": guard}
    mail = build_vehicle_registration_reminder_email(member, vehicle, notice)
    return safe_send_email_via_ses([to_email], mail["subject"], mail["text"], mail["html"])


def scan_historic_classic_active_vehicles() -> List[Dict[str, Any]]:
    require_metadata_table()
    items: List[Dict[str, Any]] = []
    start_key = None
    while True:
        kwargs = {
            "TableName": MEMBER_METADATA_TABLE,
            "FilterExpression": "begins_with(#sk, :vehicle_prefix) AND #historic = :yes",
            "ExpressionAttributeNames": {"#sk": "sk", "#historic": "historic_classic"},
            "ExpressionAttributeValues": {":vehicle_prefix": {"S": "VEHICLE#"}, ":yes": {"BOOL": True}},
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        resp = ddb.scan(**kwargs)
        for item in resp.get("Items", []):
            vehicle = item_to_python(item)
            if normalise_vehicle_status(vehicle.get("vehicle_status") or vehicle.get("status") or "active") != "disposed":
                items.append(vehicle)
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            break
    return items


def member_is_financial_for_historic_registration(member: Dict[str, Any], today: Any) -> bool | None:
    membership_type = str(member.get("membership_type") or member.get("member_type") or "").strip().lower()
    status = str(member.get("membership_status") or "").strip().lower().replace(" ", "_").replace("-", "_")
    if membership_type == "life" or status == "life":
        return True
    if status in {"financial", "current", "active"}:
        return True
    if status in {"expired", "lapsed", "due", "pending_payment", "pending", "inactive", "cancelled", "unfinancial", "non_financial", "not_financial"}:
        return False
    expiry_text = str(member.get("membership_expiry") or member.get("expiry_date") or "").strip()
    expiry = parse_vehicle_expiry_date(expiry_text)
    if expiry:
        return expiry >= today
    return None


def historic_financial_notice_key(sub: str, period_key: str) -> Dict[str, Dict[str, str]]:
    safe_period = re.sub(r"[^A-Za-z0-9_-]+", "_", str(period_key or "unknown"))[:120]
    return {"pk": {"S": member_pk(sub)}, "sk": {"S": f"REMINDER#HISTORIC_FINANCIAL#{safe_period}"}}


def mark_historic_financial_notice_sent(sub: str, period_key: str, triggered_by: str) -> bool:
    require_metadata_table()
    now = utc_now()
    item = {
        "pk": member_pk(sub),
        "sk": f"REMINDER#HISTORIC_FINANCIAL#{re.sub(r'[^A-Za-z0-9_-]+', '_', str(period_key or 'unknown'))[:120]}",
        "item_type": "historic_financial_notice",
        "member_sub": sub,
        "period_key": str(period_key or "unknown"),
        "triggered_by": str(triggered_by or "scheduler"),
        "sent_at": now,
        "created_at": now,
    }
    try:
        ddb.put_item(
            TableName=MEMBER_METADATA_TABLE,
            Item=python_to_item(item),
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def build_historic_financial_member_email(member: Dict[str, Any], vehicles: List[Dict[str, Any]], coordinator_advised: bool) -> Dict[str, str]:
    name = member_display_name_from_metadata(member, {})
    status = str(member.get("membership_status") or "not financial").strip() or "not financial"
    vehicle_lines = [f"- {vehicle_reminder_title(v)}" for v in vehicles]
    subject = "LROC historic/classic registration and membership status"
    coordinator_text = "The Historic Vehicle Registration coordinator has been advised." if coordinator_advised else "The Historic Vehicle Registration coordinator could not be automatically advised because the role email is not configured."
    paragraphs = [
        f"Dear {name},",
        f"Your LROC membership is currently recorded as {status}.",
        "Historic/classic registrations for vehicles in your registry are not valid until you bring your membership back to a financial state.",
        coordinator_text,
        "Historic/classic vehicles recorded against your profile:\n" + "\n".join(vehicle_lines),
    ]
    rows = [
        ("Member number", member_number_from_metadata(member)),
        ("Membership status", status),
        ("Vehicles", ", ".join(vehicle_reminder_title(v) for v in vehicles)),
    ]
    text = "Land Rover Owners Club of Australia Inc\n\n" + "\n\n".join(paragraphs)
    html_body = simple_html_email(subject, paragraphs, rows)
    return {"subject": subject, "text": text, "html": html_body}


def build_historic_financial_coordinator_email(member: Dict[str, Any], vehicles: List[Dict[str, Any]], member_advised: bool) -> Dict[str, str]:
    name = member_display_name_from_metadata(member, {})
    status = str(member.get("membership_status") or "not financial").strip() or "not financial"
    subject = f"Historic/classic member no longer financial - {name}"
    vehicle_lines = [f"- {vehicle_reminder_title(v)}" for v in vehicles]
    paragraphs = [
        f"{name} is recorded as {status} and has historic/classic vehicles in the member vehicle registry.",
        "The member has been advised that their historic/classic registrations are not valid until their membership is returned to a financial state." if member_advised else "The member could not be automatically advised because their email address is not configured.",
        "Vehicles:\n" + "\n".join(vehicle_lines),
    ]
    rows = [
        ("Member name", name),
        ("Member number", member_number_from_metadata(member)),
        ("Member email", member_email_from_metadata(member)),
        ("Mobile", str(member.get("mobile") or "").strip()),
        ("Phone", str(member.get("phone") or member.get("phone_number") or "").strip()),
        ("Membership status", status),
        ("Membership expiry", str(member.get("membership_expiry") or member.get("expiry_date") or "").strip()),
        ("Vehicles", ", ".join(vehicle_reminder_title(v) for v in vehicles)),
    ]
    text = "Land Rover Owners Club of Australia Inc\n\n" + "\n\n".join(paragraphs) + "\n\n" + "\n".join(f"{label}: {value or 'Not supplied'}" for label, value in rows)
    html_body = simple_html_email(subject, paragraphs, rows)
    return {"subject": subject, "text": text, "html": html_body}


def run_historic_financial_status_scan(triggered_by: str = "scheduler") -> Dict[str, Any]:
    today = current_club_date()
    result: Dict[str, Any] = {
        "enabled": True,
        "scanned_vehicles": 0,
        "members_with_historic_classic_vehicles": 0,
        "matched_non_financial_members": 0,
        "member_emails_sent": 0,
        "coordinator_emails_sent": 0,
        "skipped_ses_not_configured": 0,
        "skipped_duplicate": 0,
        "skipped_member_email_missing": 0,
        "skipped_email_guard": 0,
        "skipped_coordinator_email_missing": 0,
        "skipped_financial_or_unknown": 0,
        "send_failures": 0,
        "email_guard": system_email_guard_summary(),
    }
    vehicles = scan_historic_classic_active_vehicles()
    result["scanned_vehicles"] = len(vehicles)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for vehicle in vehicles:
        user_sub = str(vehicle.get("member_sub") or str(vehicle.get("pk") or "").replace("MEMBER#", "", 1)).strip()
        if user_sub:
            grouped.setdefault(user_sub, []).append(vehicle)
    result["members_with_historic_classic_vehicles"] = len(grouped)
    if not ses_email_available():
        result["skipped_ses_not_configured"] = len(grouped)
        return result
    position = resolve_historic_rego_position()
    coordinator_email = normalise_email_address((position or {}).get("email_address") or "")
    coordinator_valid = valid_email_address(coordinator_email) and (position or {}).get("active", True) is not False
    if not coordinator_valid:
        result["skipped_coordinator_email_missing"] = len(grouped)
    for user_sub, member_vehicles in grouped.items():
        member = get_member_metadata(user_sub)
        financial = member_is_financial_for_historic_registration(member, today)
        if financial is not False:
            result["skipped_financial_or_unknown"] += 1
            continue
        result["matched_non_financial_members"] += 1
        status = str(member.get("membership_status") or "unknown").strip().lower().replace(" ", "_") or "unknown"
        expiry = str(member.get("membership_expiry") or member.get("expiry_date") or "no_expiry").strip() or "no_expiry"
        period_key = f"{status}#{expiry}"
        if not mark_historic_financial_notice_sent(user_sub, period_key, triggered_by):
            result["skipped_duplicate"] += 1
            continue
        member_email = member_email_from_metadata(member)
        any_sent = False
        coordinator_sent = False
        if not member_email:
            result["skipped_member_email_missing"] += 1
        if coordinator_valid:
            coordinator_guard = system_email_guard_status({"email": coordinator_email, "name": "Historic Registrar", "cognito_sub": "role-address"}, context="historic_financial_coordinator")
            if not coordinator_guard.get("allowed"):
                result["skipped_email_guard"] += 1
            else:
                coordinator_mail = build_historic_financial_coordinator_email(member, member_vehicles, bool(member_email))
                sent = safe_send_email_via_ses([coordinator_email], coordinator_mail["subject"], coordinator_mail["text"], coordinator_mail["html"])
                if sent.get("sent"):
                    result["coordinator_emails_sent"] += 1
                    any_sent = True
                    coordinator_sent = True
                else:
                    result["send_failures"] += 1
        if member_email:
            member_guard = system_email_guard_status({**member, "sub": user_sub, "user_sub": user_sub, "email": member_email}, context="historic_financial_member")
            if not member_guard.get("allowed"):
                result["skipped_email_guard"] += 1
            else:
                member_mail = build_historic_financial_member_email(member, member_vehicles, coordinator_sent)
                sent = safe_send_email_via_ses([member_email], member_mail["subject"], member_mail["text"], member_mail["html"])
                if sent.get("sent"):
                    result["member_emails_sent"] += 1
                    any_sent = True
                else:
                    result["send_failures"] += 1
        if not any_sent:
            # Retry later if nothing actually left the system.
            try:
                ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=historic_financial_notice_key(user_sub, period_key))
            except Exception:
                pass
    return result



def parse_historic_rego_request_date(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    return parse_vehicle_expiry_date(text[:10])


def historic_rego_update_reminder_key(request_id: str, due_date: str) -> Dict[str, Dict[str, str]]:
    safe_request = historic_rego_safe_segment(request_id, "request")
    safe_due = re.sub(r"[^0-9-]+", "", str(due_date or ""))[:10] or "unknown"
    return {"pk": {"S": "HISTORIC_REGISTRATION#REMINDERS"}, "sk": {"S": f"UPDATE#{safe_request}#{safe_due}"}}


def mark_historic_rego_update_reminder_sent(request_id: str, due_date: str, member_sub: str, triggered_by: str) -> bool:
    require_metadata_table()
    now = utc_now()
    item = {
        "pk": "HISTORIC_REGISTRATION#REMINDERS",
        "sk": f"UPDATE#{historic_rego_safe_segment(request_id, 'request')}#{re.sub(r'[^0-9-]+', '', str(due_date or ''))[:10] or 'unknown'}",
        "item_type": "historic_registration_update_reminder",
        "request_id": str(request_id or ""),
        "member_sub": str(member_sub or ""),
        "due_date": str(due_date or ""),
        "triggered_by": str(triggered_by or "scheduler"),
        "sent_at": now,
        "created_at": now,
    }
    try:
        ddb.put_item(
            TableName=MEMBER_METADATA_TABLE,
            Item=python_to_item(item),
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def scan_historic_registration_requests_for_update() -> List[Dict[str, Any]]:
    require_metadata_table()
    requests: List[Dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": MEMBER_METADATA_TABLE,
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {":pk": {"S": "HISTORIC_REGISTRATION#QUEUE"}, ":prefix": {"S": "REQUEST#"}},
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = ddb.query(**kwargs)
        for raw in resp.get("Items") or []:
            item = item_to_python(raw)
            if str(item.get("status") or "submitted").strip().lower() == "processed":
                requests.append(item)
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return requests


def historic_rego_update_due_for_request(request: Dict[str, Any]) -> Dict[str, Any] | None:
    vehicle = request.get("vehicle_snapshot") if isinstance(request.get("vehicle_snapshot"), dict) else {}
    expiry = parse_vehicle_expiry_date(vehicle.get("registration_expiry_date"))
    if expiry:
        base = expiry
        source = "registration_expiry_date"
    else:
        base = parse_historic_rego_request_date(request.get("submitted_at") or request.get("created_at"))
        source = "request_date"
    if not base:
        return None
    due = add_months_to_date(base, HISTORIC_REGO_UPDATE_REMINDER_MONTHS_AFTER)
    return {"base_date": base.isoformat(), "due_date": due.isoformat(), "source": source}


def historic_rego_member_vehicle_details_updated(request: Dict[str, Any]) -> bool:
    sub = str(request.get("member_sub") or "").strip()
    vehicle_id = str(request.get("vehicle_id") or "").strip()
    if not sub or not vehicle_id:
        return False
    current = get_member_vehicle(sub, vehicle_id)
    if not current:
        return False
    current_expiry = parse_vehicle_expiry_date(current.get("registration_expiry_date"))
    current_plate = str(current.get("rego_number") or "").strip()
    current_historic = bool(current.get("historic_classic"))
    snapshot = request.get("vehicle_snapshot") if isinstance(request.get("vehicle_snapshot"), dict) else {}
    old_expiry = parse_vehicle_expiry_date(snapshot.get("registration_expiry_date"))
    old_plate = str(snapshot.get("rego_number") or "").strip()
    if old_expiry:
        # Existing historic/classic renewals are considered complete once the member records a later expiry date.
        return bool(current_expiry and current_expiry > old_expiry and current_historic)
    # New/manual or conversion requests need the member to record all historic/classic registration details.
    return bool(current_historic and current_plate and current_expiry and (not old_plate or current_plate != old_plate or current_expiry))


def build_historic_rego_update_reminder_email(member: Dict[str, Any], request: Dict[str, Any], due: Dict[str, Any]) -> Dict[str, str]:
    vehicle = request.get("vehicle_snapshot") if isinstance(request.get("vehicle_snapshot"), dict) else {}
    title = historic_rego_vehicle_title(vehicle)
    url = vehicle_registration_email_url(str(request.get("vehicle_id") or ""))
    subject = f"LROC Historic / Classic vehicle details update reminder - {title}"
    paragraphs = [
        f"The club has processed the Historic / Classic registration request for {title}.",
        "Please update your My Vehicles record so the club registry shows the current Historic / Classic registration details.",
        "Please check the next registration expiry date, registration plate number, and Historic / Classic checkbox. For a conversion from full registration, make sure the vehicle is now marked as Historic / Classic.",
        f"My Vehicles: {url}",
    ]
    rows = [
        ("Request ID", str(request.get("request_id") or "")),
        ("Member number", member_number_from_metadata(member)),
        ("Vehicle", title),
        ("Original expiry", str(vehicle.get("registration_expiry_date") or "")),
        ("Reminder due", str(due.get("due_date") or "")),
        ("Due basis", "Registration expiry date" if due.get("source") == "registration_expiry_date" else "Request date"),
    ]
    text = "Land Rover Owners Club of Australia Inc\n\n" + "\n\n".join(paragraphs) + "\n\n" + "\n".join(f"{label}: {value or 'Not supplied'}" for label, value in rows)
    html_body = simple_html_email(subject, paragraphs, rows)
    return {"subject": subject, "text": text, "html": html_body}


def run_historic_registration_update_reminder_scan(triggered_by: str = "scheduler") -> Dict[str, Any]:
    today = current_club_date()
    result: Dict[str, Any] = {
        "enabled": bool(ENABLE_HISTORIC_REGISTRATION_REMINDERS),
        "triggered_by": str(triggered_by or "scheduler"),
        "today": today.isoformat(),
        "months_after": HISTORIC_REGO_UPDATE_REMINDER_MONTHS_AFTER,
        "scanned_requests": 0,
        "matched_due": 0,
        "sent_emails": 0,
        "skipped_not_due": 0,
        "skipped_already_updated": 0,
        "skipped_duplicate": 0,
        "skipped_member_email_missing": 0,
        "skipped_email_guard": 0,
        "skipped_ses_not_configured": 0,
        "send_failures": 0,
        "email_guard": system_email_guard_summary(),
    }
    if not ENABLE_HISTORIC_REGISTRATION_REMINDERS:
        return result
    if not ses_email_available():
        result["skipped_ses_not_configured"] = len(scan_historic_registration_requests_for_update())
        return result
    for request in scan_historic_registration_requests_for_update():
        result["scanned_requests"] += 1
        due = historic_rego_update_due_for_request(request)
        if not due:
            result["skipped_not_due"] += 1
            continue
        due_date = parse_vehicle_expiry_date(due.get("due_date"))
        if not due_date or today < due_date:
            result["skipped_not_due"] += 1
            continue
        if historic_rego_member_vehicle_details_updated(request):
            result["skipped_already_updated"] += 1
            continue
        result["matched_due"] += 1
        request_id = str(request.get("request_id") or "").strip()
        member_sub = str(request.get("member_sub") or "").strip()
        member = get_member_metadata(member_sub) if member_sub else {}
        member_email = member_email_from_metadata(member)
        if not member_email:
            result["skipped_member_email_missing"] += 1
            continue
        guard = system_email_guard_status({**member, "sub": member_sub, "user_sub": member_sub, "email": member_email}, context="historic_registration_update")
        if not guard.get("allowed"):
            result["skipped_email_guard"] += 1
            continue
        if not mark_historic_rego_update_reminder_sent(request_id, str(due.get("due_date") or ""), member_sub, triggered_by):
            result["skipped_duplicate"] += 1
            continue
        mail = build_historic_rego_update_reminder_email(member, request, due)
        sent = safe_send_email_via_ses([member_email], mail["subject"], mail["text"], mail["html"])
        if sent.get("sent"):
            result["sent_emails"] += 1
        else:
            result["send_failures"] += 1
            try:
                ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=historic_rego_update_reminder_key(request_id, str(due.get("due_date") or "")))
            except Exception:
                pass
    return result


def run_vehicle_registration_reminder_scan(triggered_by: str = "scheduler") -> Dict[str, Any]:
    today = current_club_date()
    target_date = add_months_to_date(today, VEHICLE_REGISTRATION_REMINDER_MONTHS_BEFORE)
    result: Dict[str, Any] = {
        "enabled": bool(ENABLE_VEHICLE_REGISTRATION_PUSH_REMINDERS),
        "triggered_by": str(triggered_by or "scheduler"),
        "today": today.isoformat(),
        "target_registration_expiry_date": target_date.isoformat(),
        "months_before": VEHICLE_REGISTRATION_REMINDER_MONTHS_BEFORE,
        "final_notice_months_after_expiry": VEHICLE_REGISTRATION_FINAL_NOTICE_MONTHS_AFTER,
        "scanned_vehicles": 0,
        "matched_vehicles": 0,
        "queued_notifications": 0,
        "queued_push_notifications": 0,
        "registration_emails_sent": 0,
        "final_notices_queued": 0,
        "final_notice_emails_sent": 0,
        "skipped_inactive_or_disposed": 0,
        "skipped_no_member_sub": 0,
        "skipped_invalid_expiry": 0,
        "skipped_not_due": 0,
        "skipped_no_push_subscription": 0,
        "skipped_no_member_email": 0,
        "skipped_email_not_configured": 0,
        "skipped_email_failed": 0,
        "skipped_email_guard": 0,
        "skipped_duplicate": 0,
        "skipped_queue_unavailable": 0,
        "skipped_no_delivery_channel": 0,
        "email_guard": system_email_guard_summary(),
        "historic_registration_update_reminders": {},
        "historic_classic_financial_status": {},
    }
    if not ENABLE_VEHICLE_REGISTRATION_PUSH_REMINDERS:
        return result

    vehicles = scan_vehicle_registration_candidates()
    result["scanned_vehicles"] = len(vehicles)
    for vehicle in vehicles:
        user_sub = str(vehicle.get("member_sub") or str(vehicle.get("pk") or "").replace("MEMBER#", "", 1)).strip()
        vehicle_id = str(vehicle.get("vehicle_id") or str(vehicle.get("sk") or "").replace("VEHICLE#", "", 1)).strip()
        expiry_date = clean_vehicle_text(vehicle.get("registration_expiry_date"), 10)
        if not user_sub or not vehicle_id:
            result["skipped_no_member_sub"] += 1
            continue
        if not parse_vehicle_expiry_date(expiry_date):
            result["skipped_invalid_expiry"] += 1
            continue
        if not is_vehicle_registration_reminder_active(vehicle):
            result["skipped_inactive_or_disposed"] += 1
            continue
        notice = determine_vehicle_registration_notice(vehicle, today, target_date)
        if not notice:
            result["skipped_not_due"] += 1
            continue
        result["matched_vehicles"] += 1
        has_push_subscription = usable_push_subscription_exists(user_sub)
        can_queue_push = bool(CHAT_NOTIFICATION_QUEUE_URL and has_push_subscription)
        if not has_push_subscription:
            result["skipped_no_push_subscription"] += 1
        elif not CHAT_NOTIFICATION_QUEUE_URL:
            result["skipped_queue_unavailable"] += 1

        email_possible = False
        if not ses_email_available():
            result["skipped_email_not_configured"] += 1
        else:
            try:
                member = get_member_metadata(user_sub)
                email_possible = bool(member_email_from_metadata(member))
            except Exception:
                email_possible = False
            if not email_possible:
                result["skipped_no_member_email"] += 1

        if not can_queue_push and not email_possible:
            result["skipped_no_delivery_channel"] += 1
            continue

        notice_kind = str(notice.get("kind") or "reminder")
        notice_date = str(notice.get("notice_date") or today.isoformat())
        if not mark_vehicle_registration_reminder_sent(user_sub, vehicle_id, expiry_date, notice_kind, notice_date, triggered_by):
            result["skipped_duplicate"] += 1
            continue

        push_queued = False
        email_sent = False
        try:
            if can_queue_push:
                push_queued = enqueue_direct_push_notification(
                    user_sub,
                    str(notice.get("title") or "Vehicle registration reminder"),
                    str(notice.get("body") or "Tap to review your vehicle registration."),
                    data={
                        "url": "/historic-registration.html" if notice_kind == "historic_classic_due_soon" else f"/profile.html?registration_vehicle_id={vehicle_id}#vehicles",
                        "kind": "vehicle_registration_reminder",
                        "notice_kind": notice_kind,
                        "vehicle_id": vehicle_id,
                        "registration_expiry_date": expiry_date,
                    },
                    tag=f"vehicle-registration-{notice_kind}-{vehicle_id}-{expiry_date}",
                )
            if email_possible:
                email_result = send_vehicle_registration_reminder_email(user_sub, vehicle, notice)
                if email_result.get("sent"):
                    email_sent = True
                elif email_result.get("reason") == "member_email_not_configured":
                    result["skipped_no_member_email"] += 1
                elif email_result.get("reason") == "ses_not_configured":
                    result["skipped_email_not_configured"] += 1
                elif email_result.get("reason") in {"system_email_test_mode", "no_cognito_presence", "system_email_mode_off"}:
                    result["skipped_email_guard"] += 1
                else:
                    result["skipped_email_failed"] += 1
        except Exception:
            ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=vehicle_registration_reminder_key(user_sub, vehicle_id, expiry_date, notice_kind, notice_date))
            raise

        if push_queued or email_sent:
            apply_vehicle_registration_notice_state(vehicle, notice, triggered_by)
            if push_queued:
                result["queued_notifications"] += 1
                result["queued_push_notifications"] += 1
            if email_sent:
                result["registration_emails_sent"] += 1
            if notice_kind == "final_notice":
                if push_queued:
                    result["final_notices_queued"] += 1
                if email_sent:
                    result["final_notice_emails_sent"] += 1
        else:
            ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=vehicle_registration_reminder_key(user_sub, vehicle_id, expiry_date, notice_kind, notice_date))
            result["skipped_no_delivery_channel"] += 1

    try:
        result["historic_registration_update_reminders"] = run_historic_registration_update_reminder_scan(triggered_by=triggered_by)
    except Exception as exc:
        result["historic_registration_update_reminders"] = {"error": str(exc)[:500]}

    try:
        result["historic_classic_financial_status"] = run_historic_financial_status_scan(triggered_by=triggered_by)
    except Exception as exc:
        result["historic_classic_financial_status"] = {"error": str(exc)[:500]}
    return result


def set_room_notification_muted(room_id: str, sub: str, claims: Dict[str, Any], muted: bool, existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    existing = existing or get_chat_membership_item(room_id, sub) or {}
    state = str(existing.get("state") or "joined").strip().lower()
    if state != "joined":
        raise PermissionError("Join this chatroom first.")
    payload = save_chat_membership(room_id, sub, claims, state, existing=existing)
    payload["notifications_muted"] = bool(muted)
    ddb.put_item(TableName=CHAT_TABLE, Item=python_to_item(payload))
    return payload


def room_slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text[:48] or "room"


def get_member_display_label(claims: Dict[str, Any]) -> str:
    lookup_id = str(claims.get("sub") or claims.get("email") or claims.get("cognito:username") or "").strip()
    if lookup_id:
        try:
            summary = resolve_user_summary(lookup_id)
            label = format_chat_member_label(
                summary.get("name") or summary.get("preferred_username") or summary.get("email") or summary.get("cognito_username") or "",
                summary.get("display_callsign") or summary.get("callsign") or "",
            ) or str(summary.get("email") or "").strip()
            if label:
                return label
        except Exception:
            pass
    label = format_chat_member_label(
        str(claims.get("name") or claims.get("preferred_username") or claims.get("email") or claims.get("cognito:username") or "").strip(),
        str(claims.get("callsign") or "").strip(),
    )
    return label or "LROC Member"

def current_club_date() -> Any:
    return datetime.now(ZoneInfo(CLUB_TIME_ZONE)).date()


def parse_event_date_value(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text]
    if "T" in text:
        candidates.append(text.split("T", 1)[0])
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def chat_message_id() -> str:
    return f"MSG#{utc_now_precise()}#{secrets.token_hex(4)}"


def default_chat_rooms() -> List[Dict[str, Any]]:
    member_scope = sorted(CHAT_MEMBER_GROUPS)
    return [
        {
            "room_id": "general-chat",
            "title": "General Chat",
            "description": "Club-wide chat for members, room announcements, and general conversation.",
            "room_kind": "default",
            "required_any_groups": member_scope,
            "default_joined": False,
            "active": True,
            "created_at": "",
            "sort_order": 10,
        },
        {
            "room_id": "committee",
            "title": "Committee",
            "description": "Committee coordination and planning.",
            "room_kind": "default",
            "required_any_groups": sorted(CHAT_COMMITTEE_GROUPS),
            "default_joined": False,
            "active": True,
            "created_at": "",
            "sort_order": 20,
        },
        {
            "room_id": "admin",
            "title": "Admin",
            "description": "Admin and webmaster coordination.",
            "room_kind": "default",
            "required_any_groups": sorted(CHAT_ADMIN_GROUPS),
            "default_joined": False,
            "active": True,
            "created_at": "",
            "sort_order": 30,
        },
    ]


def event_chat_rooms() -> List[Dict[str, Any]]:
    """Return active event-backed chat rooms.

    Historically this function tried to include a separate calendar-event source, but
    LROC currently stores event/trip/meeting rows through list_trip_events().  The
    old calendar helper is not present in this Lambda, so do not call it from the
    chatroom bootstrap path; otherwise the page fails during login with
    ``name 'list_calendar_events' is not defined``.
    """
    rooms: List[Dict[str, Any]] = []
    today = current_club_date()
    try:
        for idx, item in enumerate(list_trip_events(admin=False)):
            room = trip_event_chat_room(item, idx)
            if not room:
                continue
            live_until = parse_event_date_value(room.get("live_until"))
            if live_until and today > live_until:
                continue
            rooms.append(room)
    except Exception:
        pass
    return rooms


def get_chat_room_meta_item(room_id: str) -> Dict[str, Any] | None:
    require_chat_table()
    resp = ddb.get_item(TableName=CHAT_TABLE, Key=chat_room_meta_key(room_id), ConsistentRead=True)
    if not resp.get("Item"):
        return None
    return item_to_python(resp["Item"])


def list_chat_room_meta_items() -> Dict[str, Dict[str, Any]]:
    require_chat_table()
    items: Dict[str, Dict[str, Any]] = {}
    start_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": CHAT_TABLE,
            "IndexName": "gsi1",
            "KeyConditionExpression": "gsi1pk = :pk",
            "ExpressionAttributeValues": {
                ":pk": {"S": "ROOMS"},
            },
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        resp = ddb.query(**kwargs)
        for item in resp.get("Items", []):
            value = item_to_python(item)
            room_id = str(value.get("room_id") or "").strip()
            if room_id:
                items[room_id] = value
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            break
    return items


def list_chat_memberships_for_user(sub: str) -> Dict[str, Dict[str, Any]]:
    require_chat_table()
    items: Dict[str, Dict[str, Any]] = {}
    start_key = None
    while True:
        kwargs: Dict[str, Any] = {
            "TableName": CHAT_TABLE,
            "IndexName": "gsi1",
            "KeyConditionExpression": "gsi1pk = :pk",
            "ExpressionAttributeValues": {
                ":pk": {"S": f"USER#{sub}"},
            },
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        resp = ddb.query(**kwargs)
        for item in resp.get("Items", []):
            value = item_to_python(item)
            room_id = str(value.get("room_id") or "").strip()
            if room_id:
                items[room_id] = value
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            break
    return items


def get_chat_membership_item(room_id: str, sub: str) -> Dict[str, Any] | None:
    require_chat_table()
    resp = ddb.get_item(TableName=CHAT_TABLE, Key=chat_room_membership_key(room_id, sub), ConsistentRead=True)
    if not resp.get("Item"):
        return None
    return item_to_python(resp["Item"])


def merge_room_overlay(base: Dict[str, Any], overlay: Dict[str, Any] | None) -> Dict[str, Any]:
    if not overlay:
        return dict(base)
    merged = dict(base)
    for key in [
        "title",
        "description",
        "room_kind",
        "required_any_groups",
        "default_joined",
        "created_at",
        "created_by",
        "created_by_label",
        "event_date",
        "live_until",
        "active",
        "closed_at",
        "closed_by",
        "invitation_note",
        "sort_order",
    ]:
        if key in overlay:
            merged[key] = overlay[key]
    return merged


def build_chat_room_catalog() -> Dict[str, Dict[str, Any]]:
    rooms: Dict[str, Dict[str, Any]] = {room["room_id"]: room for room in default_chat_rooms()}
    overlays = list_chat_room_meta_items()
    for room in event_chat_rooms():
        rooms[room["room_id"]] = merge_room_overlay(room, overlays.get(room["room_id"]))
    for room_id, item in overlays.items():
        room_kind = str(item.get("room_kind") or "custom").strip() or "custom"
        if room_kind == "custom":
            rooms[room_id] = merge_room_overlay({
                "room_id": room_id,
                "title": str(item.get("title") or room_id).strip() or room_id,
                "description": str(item.get("description") or "").strip(),
                "room_kind": "custom",
                "required_any_groups": sorted(CHAT_MEMBER_GROUPS),
                "default_joined": False,
                "active": True,
                "created_at": str(item.get("created_at") or ""),
                "sort_order": 2000,
            }, item)
            continue
        if room_id in rooms:
            rooms[room_id] = merge_room_overlay(rooms[room_id], item)
    return rooms


def is_room_active(room: Dict[str, Any]) -> bool:
    if str(room.get("closed_at") or "").strip():
        return False
    kind = str(room.get("room_kind") or "custom").strip() or "custom"
    if kind == "event":
        live_until = parse_event_date_value(room.get("live_until"))
        return bool(live_until and current_club_date() <= live_until)
    return bool(room.get("active", True))


def is_user_allowed_in_room(room: Dict[str, Any], groups: set[str]) -> bool:
    allowed = {str(x).strip() for x in (room.get("required_any_groups") or []) if str(x).strip()}
    return bool(groups.intersection(allowed))


def room_joined_state(room: Dict[str, Any], membership: Dict[str, Any] | None) -> bool:
    state = str((membership or {}).get("state") or "").strip().lower()
    if state == "joined":
        return True
    if state == "left":
        return False
    return bool(room.get("default_joined"))


def can_close_chat_room(claims: Dict[str, Any], room: Dict[str, Any]) -> bool:
    if not get_groups(claims).intersection(CHAT_MODERATOR_GROUPS):
        return False
    return str(room.get("room_kind") or "").strip() in {"custom", "event"}


def chat_room_summary(room: Dict[str, Any], membership: Dict[str, Any] | None, claims: Dict[str, Any]) -> Dict[str, Any]:
    joined = room_joined_state(room, membership)
    return {
        "room_id": str(room.get("room_id") or ""),
        "title": str(room.get("title") or ""),
        "description": str(room.get("description") or ""),
        "room_kind": str(room.get("room_kind") or "custom"),
        "event_date": str(room.get("event_date") or ""),
        "live_until": str(room.get("live_until") or ""),
        "created_at": str(room.get("created_at") or ""),
        "created_by": str(room.get("created_by") or ""),
        "created_by_label": str(room.get("created_by_label") or ""),
        "invitation_note": str(room.get("invitation_note") or ""),
        "joined": joined,
        "join_available": not joined,
        "leave_available": joined,
        "default_joined": bool(room.get("default_joined")),
        "can_close": can_close_chat_room(claims, room),
        "notifications_muted": bool((membership or {}).get("notifications_muted", False)),
    }


def room_sort_tuple(room: Dict[str, Any]) -> tuple[Any, ...]:
    kind = str(room.get("room_kind") or "custom")
    if kind == "default":
        return (0, int(room.get("sort_order") or 0), str(room.get("title") or "").lower())
    if kind == "event":
        return (1, str(room.get("event_date") or "9999-12-31"), str(room.get("title") or "").lower())
    return (2, str(room.get("title") or "").lower(), str(room.get("created_at") or ""))


def save_chat_room_meta(room: Dict[str, Any]) -> Dict[str, Any]:
    require_chat_table()
    payload = {
        "pk": chat_room_pk(str(room.get("room_id") or "")),
        "sk": "META",
        "type": "ROOM",
        "room_id": str(room.get("room_id") or ""),
        "title": str(room.get("title") or "").strip(),
        "description": str(room.get("description") or "").strip(),
        "room_kind": str(room.get("room_kind") or "custom").strip() or "custom",
        "required_any_groups": [str(x).strip() for x in (room.get("required_any_groups") or []) if str(x).strip()],
        "default_joined": bool(room.get("default_joined")),
        "active": bool(room.get("active", True)),
        "created_at": str(room.get("created_at") or ""),
        "created_by": str(room.get("created_by") or ""),
        "created_by_label": str(room.get("created_by_label") or ""),
        "event_date": str(room.get("event_date") or ""),
        "live_until": str(room.get("live_until") or ""),
        "closed_at": str(room.get("closed_at") or ""),
        "closed_by": str(room.get("closed_by") or ""),
        "invitation_note": str(room.get("invitation_note") or ""),
        "sort_order": int(room.get("sort_order") or 0),
        "gsi1pk": "ROOMS",
        "gsi1sk": f"ROOM#{str(room.get('room_id') or '')}",
    }
    ddb.put_item(TableName=CHAT_TABLE, Item=python_to_item(payload))
    return payload


def save_chat_membership(room_id: str, sub: str, claims: Dict[str, Any], state: str, existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    require_chat_table()
    now = utc_now_precise()
    existing = existing or {}
    joined_at = str(existing.get("joined_at") or now)
    payload = {
        "pk": chat_room_pk(room_id),
        "sk": f"MEMBER#{sub}",
        "type": "MEMBERSHIP",
        "room_id": room_id,
        "user_sub": sub,
        "state": state,
        "joined_at": joined_at,
        "last_joined_at": now if state == "joined" else str(existing.get("last_joined_at") or joined_at),
        "left_at": now if state == "left" else "",
        "display_name": get_member_display_label(claims),
        "email": str(claims.get("email") or "").strip(),
        "gsi1pk": f"USER#{sub}",
        "gsi1sk": f"ROOM#{room_id}",
        "notifications_muted": bool(existing.get("notifications_muted", False)),
    }
    ddb.put_item(TableName=CHAT_TABLE, Item=python_to_item(payload))
    return payload


def append_chat_message(
    room_id: str,
    body: str,
    *,
    claims: Dict[str, Any] | None = None,
    system: bool = False,
    system_label: str = "System",
    reply_to: Dict[str, Any] | None = None,
    attachments: List[Dict[str, Any]] | None = None,
    message_type: str = "",
    event_room_id: str = "",
    expires_at: str = "",
    notify_members: bool = False,
) -> Dict[str, Any]:
    require_chat_table()
    text = str(body or "").strip()
    clean_attachments = normalise_chat_attachments(attachments or [])
    if not text and not clean_attachments:
        raise ValueError("Message text or an attachment is required.")
    if len(text) > MAX_CHAT_MESSAGE_LENGTH:
        raise ValueError(f"Messages may be at most {MAX_CHAT_MESSAGE_LENGTH} characters.")
    created_at = utc_now_precise()
    clean_reply: Dict[str, Any] = {}
    if isinstance(reply_to, dict):
        reply_text = re.sub(r"\s+", " ", str(reply_to.get("body") or reply_to.get("text") or "").strip())[:240]
        reply_author = re.sub(r"\s+", " ", str(reply_to.get("author_label") or reply_to.get("author") or "Member").strip())[:80]
        reply_id = str(reply_to.get("message_id") or reply_to.get("sk") or "").strip()[:120]
        if reply_text:
            clean_reply = {"message_id": reply_id, "author_label": reply_author or "Member", "body": reply_text}
    payload = {
        "pk": chat_room_pk(room_id),
        "sk": chat_message_id(),
        "type": "MESSAGE",
        "room_id": room_id,
        "body": text,
        "created_at": created_at,
        "system": bool(system),
        "author_sub": "" if system else str((claims or {}).get("sub") or ""),
        "author_label": system_label if system else get_member_display_label(claims or {}),
    }
    if clean_reply:
        payload["reply_to"] = clean_reply
    if clean_attachments:
        payload["attachments"] = clean_attachments
    if message_type:
        payload["message_type"] = str(message_type).strip()[:80]
    if event_room_id:
        payload["event_room_id"] = str(event_room_id).strip()[:160]
    if expires_at:
        payload["expires_at"] = str(expires_at).strip()[:40]
    if notify_members:
        payload["notify_members"] = True
    ddb.put_item(TableName=CHAT_TABLE, Item=python_to_item(payload))
    return payload


def list_chat_messages(room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    require_chat_table()
    limit = max(1, min(MAX_CHAT_HISTORY_LIMIT, int(limit or 50)))
    resp = ddb.query(
        TableName=CHAT_TABLE,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": {"S": chat_room_pk(room_id)},
            ":prefix": {"S": "MSG#"},
        },
        ScanIndexForward=False,
        Limit=limit,
    )
    items = [item_to_python(item) for item in resp.get("Items", [])]
    items.reverse()
    return items


def resolve_chat_room_for_user(room_id: str, claims: Dict[str, Any], *, require_joined: bool = False, include_inactive: bool = False) -> tuple[Dict[str, Any], Dict[str, Any] | None, str]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    catalog = build_chat_room_catalog()
    room = catalog.get(room_id)
    if room is None and include_inactive:
        meta = get_chat_room_meta_item(room_id)
        if meta:
            room = merge_room_overlay({
                "room_id": room_id,
                "title": str(meta.get("title") or room_id),
                "description": str(meta.get("description") or ""),
                "room_kind": str(meta.get("room_kind") or "custom") or "custom",
                "required_any_groups": meta.get("required_any_groups") or sorted(CHAT_MEMBER_GROUPS),
                "default_joined": bool(meta.get("default_joined")),
                "active": bool(meta.get("active", True)),
                "created_at": str(meta.get("created_at") or ""),
                "sort_order": int(meta.get("sort_order") or 0),
            }, meta)
    if room is None:
        raise ValueError("Chatroom not found.")
    if not is_user_allowed_in_room(room, get_groups(claims)):
        raise PermissionError("You are not allowed to access that chatroom.")
    if not include_inactive and not is_room_active(room):
        raise ValueError("That chatroom is not currently available.")
    membership = get_chat_membership_item(room_id, sub)
    if require_joined and not room_joined_state(room, membership):
        raise PermissionError("Join this chatroom first.")
    return room, membership, sub


def list_chat_rooms_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    _ = event
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    groups = get_groups(claims)
    memberships = list_chat_memberships_for_user(sub)
    items: List[Dict[str, Any]] = []
    for room in sorted(build_chat_room_catalog().values(), key=room_sort_tuple):
        if not is_room_active(room):
            continue
        if not is_user_allowed_in_room(room, groups):
            continue
        items.append(chat_room_summary(room, memberships.get(str(room.get("room_id") or "")), claims))
    joined = [item for item in items if item.get("joined")]
    available = [item for item in items if not item.get("joined")]
    return response(200, {
        "items": items,
        "joined_rooms": joined,
        "available_rooms": available,
        "checked_at": utc_now_precise(),
        "member": get_member_display_label(claims),
        "groups": sorted(groups),
    })


def parse_utc_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def extract_join_room_id_from_body(body: Any) -> str:
    match = re.search(r"\[\[join:([^|\]]+)\|", str(body or ""))
    return str(match.group(1)).strip() if match else ""


def is_expired_event_invite(message: Dict[str, Any]) -> bool:
    now = datetime.now(timezone.utc)
    expires = parse_utc_datetime(message.get("expires_at"))
    if expires:
        return now > expires
    created = parse_utc_datetime(message.get("created_at"))
    if created:
        return now > (created + timedelta(days=CHAT_EVENT_INVITE_TTL_DAYS))
    return False


def filter_general_chat_messages_for_user(messages: List[Dict[str, Any]], claims: Dict[str, Any]) -> List[Dict[str, Any]]:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        return messages
    memberships = list_chat_memberships_for_user(sub)
    catalog = build_chat_room_catalog()
    filtered: List[Dict[str, Any]] = []
    for message in messages:
        msg_type = str(message.get("message_type") or "").strip()
        event_room_id = str(message.get("event_room_id") or "").strip()
        if not event_room_id and msg_type in {"", "event_room_invite"}:
            candidate = extract_join_room_id_from_body(message.get("body"))
            if candidate.startswith("event-"):
                event_room_id = candidate
        is_event_invite = msg_type == "event_room_invite" or event_room_id.startswith("event-")
        if is_event_invite:
            room = catalog.get(event_room_id)
            if not room or not is_room_active(room):
                continue
            if room_joined_state(room, memberships.get(event_room_id)):
                continue
            if is_expired_event_invite(message):
                continue
        filtered.append(message)
    return filtered


def create_chat_attachment_upload_url_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    _room, _membership, sub = resolve_chat_room_for_user(room_id, claims, require_joined=True)
    body = parse_body(event)
    filename = validate_chat_attachment_filename(body.get("filename") or "attachment.bin")
    content_type = str(body.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream").strip()[:120]
    size = int(body.get("size") or 0)
    if size and size > CHAT_ATTACHMENT_MAX_BYTES:
        raise ValueError(f"Chat attachments may be at most {human_size(CHAT_ATTACHMENT_MAX_BYTES)}.")
    temp_key = build_chat_attachment_temp_key(room_id, sub, filename)
    metadata = build_chat_attachment_metadata(sub, room_id, filename, packaged=False)
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": BUCKET,
            "Key": temp_key,
            "ContentType": content_type,
            "Metadata": metadata,
        },
        ExpiresIn=UPLOAD_EXPIRY,
        HttpMethod="PUT",
    )
    return response(200, {
        "upload_url": url,
        "temp_key": temp_key,
        "required_headers": {"Content-Type": content_type, **{f"x-amz-meta-{k}": v for k, v in metadata.items()}},
        "max_bytes": CHAT_ATTACHMENT_MAX_BYTES,
    })


def complete_chat_attachment_upload_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    _room, _membership, sub = resolve_chat_room_for_user(room_id, claims, require_joined=True)
    body = parse_body(event)
    temp_key = str(body.get("temp_key") or "").strip()
    filename = validate_chat_attachment_filename(body.get("filename") or "attachment.bin")
    content_type = str(body.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream").strip()[:120]
    expected_prefix = f"{CHAT_ATTACHMENTS_PREFIX}tmp/{safe_key_segment(sub, 'member')}/"
    if not temp_key.startswith(expected_prefix):
        raise ValueError("Invalid chat attachment upload key.")
    try:
        head = s3.head_object(Bucket=BUCKET, Key=temp_key)
    except ClientError as exc:
        raise ValueError("Uploaded attachment was not found.") from exc
    size = int(head.get("ContentLength") or 0)
    if size <= 0:
        raise ValueError("Uploaded attachment was empty.")
    if size > CHAT_ATTACHMENT_MAX_BYTES:
        s3.delete_object(Bucket=BUCKET, Key=temp_key)
        raise ValueError(f"Chat attachments may be at most {human_size(CHAT_ATTACHMENT_MAX_BYTES)}.")
    attachment_id = secrets.token_hex(8)
    if is_image_attachment(filename, content_type):
        final_key = build_chat_attachment_final_key(room_id, sub, filename)
        s3.copy_object(
            Bucket=BUCKET,
            Key=final_key,
            CopySource={"Bucket": BUCKET, "Key": temp_key},
            ContentType=content_type,
            Metadata=build_chat_attachment_metadata(sub, room_id, filename, packaged=False),
            MetadataDirective="REPLACE",
        )
        s3.delete_object(Bucket=BUCKET, Key=temp_key)
        attachment = {
            "id": attachment_id,
            "kind": "image",
            "filename": filename,
            "original_filename": filename,
            "content_type": content_type,
            "size": size,
            "key": final_key,
            "packaged": False,
        }
    else:
        obj = s3.get_object(Bucket=BUCKET, Key=temp_key)
        raw = obj["Body"].read()
        zip_name = f"{os.path.splitext(filename)[0] or 'attachment'}.zip"
        zipped = zip_single_file(filename, raw)
        final_key = build_chat_attachment_final_key(room_id, sub, zip_name)
        s3.put_object(
            Bucket=BUCKET,
            Key=final_key,
            Body=zipped,
            ContentType="application/zip",
            Metadata=build_chat_attachment_metadata(sub, room_id, filename, packaged=True),
        )
        s3.delete_object(Bucket=BUCKET, Key=temp_key)
        attachment = {
            "id": attachment_id,
            "kind": "file",
            "filename": zip_name,
            "original_filename": filename,
            "content_type": "application/zip",
            "size": len(zipped),
            "key": final_key,
            "packaged": True,
        }
    return response(200, {"message": "Attachment ready.", "attachment": attachment})


def create_chat_attachment_download_url_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    resolve_chat_room_for_user(room_id, claims, require_joined=True)
    body = parse_body(event)
    key = str(body.get("key") or "").strip()
    expected_prefix = f"{CHAT_ATTACHMENTS_PREFIX}final/{safe_key_segment(room_id, 'room')}/"
    if not key.startswith(expected_prefix):
        raise ValueError("Invalid chat attachment key.")
    filename = safe_filename(body.get("filename") or os.path.basename(key) or "attachment.bin")
    disposition_type = "inline" if bool(body.get("inline")) else "attachment"
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'{disposition_type}; filename="{filename}"',
        },
        ExpiresIn=DOWNLOAD_EXPIRY,
        HttpMethod="GET",
    )
    return response(200, {"url": url})


def get_chat_room_messages_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    room, membership, _sub = resolve_chat_room_for_user(room_id, claims)
    params = get_query_params(event)
    limit = int(params.get("limit") or 50)
    messages = list_chat_messages(room_id, limit=limit)
    if room_id == "general-chat":
        messages = filter_general_chat_messages_for_user(messages, claims)
    return response(200, {
        "room": chat_room_summary(room, membership, claims),
        "messages": messages,
        "loaded_at": utc_now_precise(),
    })


def join_chat_room_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    room, membership, sub = resolve_chat_room_for_user(room_id, claims)
    saved = save_chat_membership(room_id, sub, claims, "joined", existing=membership)
    return response(200, {
        "message": f"Joined {room.get('title') or room_id}.",
        "room": chat_room_summary(room, saved, claims),
    })


def leave_chat_room_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    room, membership, sub = resolve_chat_room_for_user(room_id, claims)
    saved = save_chat_membership(room_id, sub, claims, "left", existing=membership)
    return response(200, {
        "message": f"Left {room.get('title') or room_id}. You can rejoin later and your earlier activity will still be there.",
        "room": chat_room_summary(room, saved, claims),
    })


def create_chat_room_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    title = re.sub(r"\s+", " ", str(body.get("title") or "").strip())
    description = re.sub(r"\s+", " ", str(body.get("description") or "").strip())
    invitation_note = re.sub(r"\s+", " ", str(body.get("invitation_note") or "").strip())
    if not title:
        raise ValueError("Room title is required.")
    if len(title) > MAX_CHAT_ROOM_TITLE_LENGTH:
        raise ValueError(f"Room titles may be at most {MAX_CHAT_ROOM_TITLE_LENGTH} characters.")
    if len(description) > MAX_CHAT_ROOM_DESCRIPTION_LENGTH:
        raise ValueError(f"Room descriptions may be at most {MAX_CHAT_ROOM_DESCRIPTION_LENGTH} characters.")
    if len(invitation_note) > MAX_CHAT_ROOM_DESCRIPTION_LENGTH:
        raise ValueError(f"Invitation notes may be at most {MAX_CHAT_ROOM_DESCRIPTION_LENGTH} characters.")
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    created_at = utc_now_precise()
    room_id = f"room-{room_slug(title)}-{secrets.token_hex(2)}"
    room = save_chat_room_meta({
        "room_id": room_id,
        "title": title,
        "description": description,
        "room_kind": "custom",
        "required_any_groups": sorted(CHAT_MEMBER_GROUPS),
        "default_joined": False,
        "active": True,
        "created_at": created_at,
        "created_by": sub,
        "created_by_label": get_member_display_label(claims),
        "invitation_note": invitation_note,
        "sort_order": 2000,
    })
    membership = get_chat_membership_item(room_id, sub)
    append_chat_message(room_id, f"{get_member_display_label(claims)} created this room.", system=True, system_label="Room")
    announcement_parts = [f"New room created: {title}."]
    if description:
        announcement_parts.append(description)
    if invitation_note:
        announcement_parts.append(f"Invite note: {invitation_note}")
    announcement_parts.append(f"[[join:{room_id}|Join this room]]")
    append_chat_message("general-chat", " ".join(announcement_parts), system=True, system_label="Room")
    return response(200, {
        "message": "Room created.",
        "room": chat_room_summary(room, membership, claims),
    })


def post_chat_message_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    room, _membership, _sub = resolve_chat_room_for_user(room_id, claims, require_joined=True)
    body = parse_body(event)
    message = append_chat_message(
        room_id,
        body.get("message") or body.get("body") or "",
        claims=claims,
        reply_to=body.get("reply_to") if isinstance(body.get("reply_to"), dict) else None,
        attachments=body.get("attachments") if isinstance(body.get("attachments"), list) else [],
    )
    enqueue_chat_notification(room, message)
    return response(200, {
        "message": "Message sent.",
        "room": chat_room_summary(room, get_chat_membership_item(room_id, str(claims.get('sub') or '')), claims),
        "item": message,
    })


def subscribe_push_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    item = save_push_subscription(sub, claims, body.get("subscription") or body, body.get("vapid_public_key") or "")
    return response(200, {"message": "Push subscription saved.", "item": item})


def unsubscribe_push_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    subscription = body.get("subscription") or body
    endpoint = str((subscription or {}).get("endpoint") or "").strip()
    if not endpoint:
        raise ValueError("Push subscription endpoint is required.")
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise PermissionError("Missing user subject in token claims.")
    remove_push_subscription(sub, endpoint)
    return response(200, {"message": "Push subscription removed."})


def mute_chat_notifications_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    room, membership, sub = resolve_chat_room_for_user(room_id, claims, require_joined=True)
    saved = set_room_notification_muted(room_id, sub, claims, True, existing=membership)
    return response(200, {"message": f"Notifications muted for {room.get('title') or room_id}.", "room": chat_room_summary(room, saved, claims)})


def unmute_chat_notifications_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    room, membership, sub = resolve_chat_room_for_user(room_id, claims, require_joined=True)
    saved = set_room_notification_muted(room_id, sub, claims, False, existing=membership)
    return response(200, {"message": f"Notifications enabled for {room.get('title') or room_id}.", "room": chat_room_summary(room, saved, claims)})


def close_chat_room_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    room_id = str((event.get("pathParameters") or {}).get("room_id") or "").strip()
    room, membership, _sub = resolve_chat_room_for_user(room_id, claims, include_inactive=True)
    if not can_close_chat_room(claims, room):
        raise PermissionError("Only committee, admin, or webmaster users can close that room.")
    room["active"] = False
    room["closed_at"] = utc_now_precise()
    room["closed_by"] = str(claims.get("email") or claims.get("sub") or "")
    saved = save_chat_room_meta(room)
    append_chat_message("general-chat", f"Room closed: {str(room.get('title') or room_id)}.", system=True, system_label="Room")
    return response(200, {
        "message": f"Closed {room.get('title') or room_id}.",
        "room": chat_room_summary(saved, membership, claims),
    })


def member_session_check_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    return response(200, {
        "ok": True,
        "checked_at": utc_now(),
        "member": str(claims.get("email") or claims.get("sub") or "member"),
        "groups": sorted(get_groups(claims)),
    })


# ---------------------------------------------------------------------------
# LROC browser meeting / Amazon Chime SDK MVP
# ---------------------------------------------------------------------------

CHIME_MEETING_PK = "CHIME#MEETING"
CHIME_ACTIVE_SK = "ACTIVE"
CHIME_MEETING_MAX_AGE_HOURS = 12


def chime_active_key() -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": CHIME_MEETING_PK}, "sk": {"S": CHIME_ACTIVE_SK}}


def chime_meeting_key(meeting_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": CHIME_MEETING_PK}, "sk": {"S": f"MEETING#{meeting_id}"}}


def chime_attendee_key(meeting_id: str, attendee_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": f"CHIME#ATTENDEES#{meeting_id}"}, "sk": {"S": f"ATTENDEE#{attendee_id}"}}


def chime_chat_key(meeting_id: str) -> str:
    return f"CHIME#CHAT#{meeting_id}"


def chime_control_key(meeting_id: str) -> str:
    return f"CHIME#CONTROL#{meeting_id}"


def chime_vote_key(meeting_id: str) -> str:
    return f"CHIME#VOTE#{meeting_id}"


def chime_agenda_key(meeting_id: str) -> str:
    return f"CHIME#AGENDA#{meeting_id}"


def chime_history_key(meeting_id: str) -> str:
    return f"CHIME#HISTORY#{meeting_id}"


def chime_guest_pk(meeting_id: str) -> str:
    return f"CHIME#GUESTS#{meeting_id}"


def chime_guest_secret_hash(secret: str) -> str:
    return hashlib.sha256(str(secret or "").encode("utf-8")).hexdigest()


def chime_guests_allowed(active: Dict[str, Any] | None) -> bool:
    meeting_type = normalise_chime_meeting_type((active or {}).get("meeting_type"))
    return meeting_type not in {"general", "agm"}


def chime_guest_policy_message(active: Dict[str, Any] | None) -> str:
    meeting_type = normalise_chime_meeting_type((active or {}).get("meeting_type"))
    if meeting_type == "general":
        return "Guests are not permitted for General Meetings."
    if meeting_type == "agm":
        return "Guests are not permitted for Annual General Meetings."
    return "Guests are permitted for this meeting type."


def chime_make_guest_token(meeting_id: str, guest_id: str, secret: str) -> str:
    payload = json.dumps({"m": meeting_id, "g": guest_id, "s": secret}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def chime_parse_guest_token(token: Any) -> Dict[str, str]:
    text = str(token or "").strip()
    if not text:
        raise ValueError("Guest token is required.")
    padded = text + ("=" * (-len(text) % 4))
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        raise ValueError("Guest token is invalid.")
    meeting_id = str(payload.get("m") or "").strip()
    guest_id = str(payload.get("g") or "").strip()
    secret = str(payload.get("s") or "").strip()
    if not meeting_id or not guest_id or not secret:
        raise ValueError("Guest token is invalid.")
    return {"meeting_id": meeting_id, "guest_id": guest_id, "secret": secret}


def chime_guest_key(meeting_id: str, guest_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": chime_guest_pk(meeting_id)}, "sk": {"S": f"GUEST#{meeting_agenda_safe_id(guest_id)}"}}


def chime_get_guest_by_token(token: Any) -> Dict[str, Any]:
    parsed = chime_parse_guest_token(token)
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=chime_guest_key(parsed["meeting_id"], parsed["guest_id"]), ConsistentRead=True)
    item = item_to_python(resp.get("Item") or {}) if resp.get("Item") else {}
    if not item:
        raise ValueError("Guest request was not found.")
    if str(item.get("secret_hash") or "") != chime_guest_secret_hash(parsed["secret"]):
        raise PermissionError("Guest token is not authorised.")
    if str(item.get("status") or "waiting") == "expired":
        raise PermissionError("Guest request has expired.")
    return item


def chime_list_guest_requests(meeting_id: str) -> List[Dict[str, Any]]:
    if not meeting_id:
        return []
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": chime_guest_pk(meeting_id)}},
        Limit=200,
    )
    items = [item_to_python(x) for x in resp.get("Items") or []]
    items.sort(key=lambda x: str(x.get("requested_at") or ""))
    return items


def chime_guest_public(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "guest_id": str(item.get("guest_id") or ""),
        "guest_name": str(item.get("guest_name") or "Guest"),
        "guest_email": str(item.get("guest_email") or ""),
        "notes": str(item.get("notes") or ""),
        "status": str(item.get("status") or "waiting"),
        "requested_at": str(item.get("requested_at") or ""),
        "admitted_at": str(item.get("admitted_at") or ""),
        "denied_at": str(item.get("denied_at") or ""),
        "joined_at": str(item.get("joined_at") or ""),
    }


def guest_chime_request_route(event: Dict[str, Any]) -> Dict[str, Any]:
    require_chime_meetings()
    active = get_active_chime_meeting()
    if not active:
        raise ValueError("No LROC meeting is currently active.")
    body = parse_body(event)
    name = re.sub(r"\s+", " ", str(body.get("guest_name") or body.get("name") or "").strip())[:120]
    email = normalise_email_address(body.get("guest_email") or body.get("email") or "")
    notes = str(body.get("notes") or "").strip()[:300]
    if not name:
        raise ValueError("Guest name is required.")
    meeting_id = str(active.get("meeting_id") or "")
    guest_id = uuid.uuid4().hex
    secret = base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).decode("ascii").rstrip("=")
    now = utc_now_precise()
    item = {
        "item_type": "chime_guest_request",
        "meeting_id": meeting_id,
        "guest_id": guest_id,
        "guest_name": name,
        "guest_email": email,
        "notes": notes,
        "status": "waiting",
        "secret_hash": chime_guest_secret_hash(secret),
        "requested_at": now,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=CHIME_MEETING_MAX_AGE_HOURS)).isoformat(),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": chime_guest_pk(meeting_id), "sk": f"GUEST#{guest_id}"}))
    token = chime_make_guest_token(meeting_id, guest_id, secret)
    return response(200, {"message": "Your request has been sent to the meeting host.", "guest_token": token, "guest": chime_guest_public(item), "meeting": chime_public_meeting_summary(active)})


def guest_chime_status_route(event: Dict[str, Any]) -> Dict[str, Any]:
    params = get_query_params(event)
    token = params.get("token") or (parse_body(event).get("guest_token") if event.get("body") else "")
    item = chime_get_guest_by_token(token)
    active = get_active_chime_meeting()
    if not active or str(active.get("meeting_id") or "") != str(item.get("meeting_id") or ""):
        return response(200, {"guest": chime_guest_public({**item, "status": "ended"}), "meeting": {"active": False}, "can_join": False})
    guests_allowed = chime_guests_allowed(active)
    return response(200, {"guest": chime_guest_public(item), "meeting": chime_public_meeting_summary(active), "guests_allowed": guests_allowed, "guest_policy_message": chime_guest_policy_message(active), "can_join": guests_allowed and str(item.get("status") or "") == "admitted"})


def guest_chime_join_route(event: Dict[str, Any]) -> Dict[str, Any]:
    require_chime_meetings()
    body = parse_body(event)
    item = chime_get_guest_by_token(body.get("guest_token") or body.get("token"))
    active = get_active_chime_meeting()
    if not active or str(active.get("meeting_id") or "") != str(item.get("meeting_id") or ""):
        raise ValueError("This meeting is no longer active.")
    if str(item.get("status") or "") != "admitted":
        raise PermissionError("The meeting host has not admitted this guest yet.")
    meeting_id = str(active.get("meeting_id") or "")
    chime_meeting_id = str(active.get("chime_meeting_id") or "")
    if not chime_meeting_id:
        raise RuntimeError("Active meeting is missing its Chime meeting ID.")
    safe_name = re.sub(r'[^A-Za-z0-9_.-]+', '-', str(item.get("guest_name") or "Guest")).strip('-')[:28] or 'guest'
    external_user_id = f"guest-{safe_name}-{str(item.get('guest_id') or '')[:12]}-{uuid.uuid4().hex[:6]}"[:64]
    attendee_resp = chime.create_attendee(MeetingId=chime_meeting_id, ExternalUserId=external_user_id)
    attendee = attendee_resp.get("Attendee") or attendee_resp
    attendee_id = str(attendee.get("AttendeeId") or uuid.uuid4().hex)
    record = {
        "item_type": "chime_attendee",
        "meeting_id": meeting_id,
        "chime_meeting_id": chime_meeting_id,
        "attendee_id": attendee_id,
        "external_user_id": external_user_id,
        "member_sub": f"guest:{item.get('guest_id')}",
        "member_email": str(item.get("guest_email") or ""),
        "member_name": f"Guest - {str(item.get('guest_name') or 'Guest')}",
        "joined_at": utc_now_precise(),
        "attendance_type": "guest_online",
        "guest_id": str(item.get("guest_id") or ""),
        "voting_eligible": False,
        "committee_eligible": False,
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**record, "pk": f"CHIME#ATTENDEES#{meeting_id}", "sk": f"ATTENDEE#{attendee_id}"}))
    item["status"] = "joined"
    item["joined_at"] = record["joined_at"]
    item["attendee_id"] = attendee_id
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": chime_guest_pk(meeting_id), "sk": f"GUEST#{item.get('guest_id')}"}))
    return response(200, {"message": "Joining LROC meeting as guest.", "meeting": {"Meeting": active.get("meeting") or {}}, "attendee": {"Attendee": attendee}, "meeting_summary": chime_public_meeting_summary(active), "guest_name": str(item.get("guest_name") or "Guest")})


def chime_guest_lobby_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = chime_active_or_error()
    require_chime_launcher(claims)
    meeting_id = str(active.get("meeting_id") or "")
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "POST":
        body = parse_body(event)
        action = str(body.get("action") or "").strip().lower()
        if not guests_allowed and action in {"admit", "admit_all", "reset"}:
            raise PermissionError(chime_guest_policy_message(active))
        guests = chime_list_guest_requests(meeting_id)
        target_id = str(body.get("guest_id") or "").strip()
        now = utc_now_precise()
        changed = 0
        for item in guests:
            if action == "admit_all" and str(item.get("status") or "") == "waiting":
                item["status"] = "admitted"; item["admitted_at"] = now; item["admitted_by_name"] = chime_member_name(claims); changed += 1
            elif target_id and str(item.get("guest_id") or "") == target_id and action in {"admit", "deny", "reset"}:
                if action == "admit":
                    item["status"] = "admitted"; item["admitted_at"] = now; item["admitted_by_name"] = chime_member_name(claims)
                elif action == "deny":
                    item["status"] = "denied"; item["denied_at"] = now; item["denied_by_name"] = chime_member_name(claims)
                elif action == "reset":
                    item["status"] = "waiting"; item.pop("denied_at", None); item.pop("admitted_at", None)
                changed += 1
            else:
                continue
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": chime_guest_pk(meeting_id), "sk": f"GUEST#{item.get('guest_id')}"}))
        if action not in {"admit", "deny", "reset", "admit_all"}:
            raise ValueError("Unsupported guest lobby action.")
        return response(200, {"message": f"Guest lobby updated ({changed}).", "guests_allowed": guests_allowed, "guest_policy_message": chime_guest_policy_message(active), "guests": [chime_guest_public(x) for x in chime_list_guest_requests(meeting_id)], "meeting": chime_public_meeting_summary(active)})
    return response(200, {"guests": [chime_guest_public(x) for x in chime_list_guest_requests(meeting_id)], "guests_allowed": guests_allowed, "guest_policy_message": chime_guest_policy_message(active), "meeting": chime_public_meeting_summary(active), "guest_url": "/guest-meeting.html"})


def chime_active_or_error() -> Dict[str, Any]:
    active = get_active_chime_meeting()
    if not active:
        raise ValueError("No LROC meeting is currently active.")
    return active


def require_chime_meetings() -> None:
    require_metadata_table()
    if not CHIME_MEETINGS_ENABLED:
        raise RuntimeError("LROC browser meetings are not enabled.")


def chime_position_ids_for_member(claims: Dict[str, Any]) -> set[str]:
    summary = get_current_member_summary(claims)
    ids = set()
    for key in ["committee_position_id", "official_position_id", "club_position_id"]:
        pid = normalise_position_id(summary.get(key) or "")
        if pid:
            ids.add(pid)
    for key in ["assigned_role_ids", "system_roles"]:
        values = summary.get(key)
        if isinstance(values, list):
            for value in values:
                pid = normalise_position_id(value)
                if pid:
                    ids.add(pid)
    for key in ["committee_position_name", "official_position_name", "club_position_name"]:
        pid = normalise_position_id(summary.get(key) or "")
        if pid:
            ids.add(pid)
    return ids


def can_launch_chime_meeting(claims: Dict[str, Any]) -> bool:
    return bool(chime_position_ids_for_member(claims).intersection(CHIME_LAUNCH_POSITION_IDS))


def require_chime_launcher(claims: Dict[str, Any]) -> None:
    if not can_launch_chime_meeting(claims):
        raise PermissionError("Only the President, Vice President, Secretary, or Treasurer can launch or end an LROC meeting.")


def chime_member_name(claims: Dict[str, Any]) -> str:
    summary = get_current_member_summary(claims)
    return str(summary.get("name") or summary.get("email") or claims.get("email") or claims.get("sub") or "LROC member").strip()


CHIME_FORMAL_MEETING_TYPES = {"committee", "general", "agm"}
CHIME_MEETING_TYPE_LABELS = {
    "monthly": "Monthly meeting",
    "committee": "Committee meeting",
    "general": "General meeting",
    "agm": "Annual General Meeting",
}

def normalise_chime_meeting_type(value: Any) -> str:
    text = str(value or "monthly").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "month": "monthly",
        "members": "monthly",
        "member": "monthly",
        "general_meeting": "general",
        "annual_general_meeting": "agm",
        "annual": "agm",
    }
    text = aliases.get(text, text)
    return text if text in CHIME_MEETING_TYPE_LABELS else "monthly"

def chime_meeting_is_formal(item: Dict[str, Any] | None) -> bool:
    return normalise_chime_meeting_type((item or {}).get("meeting_type")) in CHIME_FORMAL_MEETING_TYPES

def chime_member_is_financial(claims: Dict[str, Any]) -> bool:
    try:
        summary = get_current_member_summary(claims)
        value = member_is_financial_for_historic_registration(summary, current_club_date())
        return value is True
    except Exception:
        return False


def chime_member_id_from_summary(summary: Dict[str, Any]) -> str:
    return str(summary.get("sub") or summary.get("member_sub") or summary.get("cognito_sub") or summary.get("username") or summary.get("email") or "").strip()


def chime_current_member_id(claims: Dict[str, Any]) -> str:
    summary = get_current_member_summary(claims)
    return chime_member_id_from_summary(summary) or str(claims.get("sub") or claims.get("cognito:username") or claims.get("email") or "").strip()


def chime_member_voting_eligible(member: Dict[str, Any]) -> bool:
    try:
        return member_is_financial_for_historic_registration(member, current_club_date()) is True
    except Exception:
        return False


def chime_member_committee_eligible(member: Dict[str, Any]) -> bool:
    if not isinstance(member, dict):
        return False
    for key in ["committee_position_id", "official_position_id", "club_position_id"]:
        pid = normalise_position_id(member.get(key) or "")
        if pid and (get_club_position(pid) or {}).get("is_committee_position"):
            return True
    if str(member.get("committee_position_name") or "").strip():
        return True
    roles = member.get("assigned_role_ids") if isinstance(member.get("assigned_role_ids"), list) else []
    for value in roles:
        pid = normalise_position_id(value)
        if pid and (get_club_position(pid) or {}).get("is_committee_position"):
            return True
    return False


def chime_member_summary_by_id(member_id: str) -> Dict[str, Any]:
    ident = str(member_id or "").strip()
    if not ident:
        return {}
    try:
        meta = get_member_metadata(ident) or {}
        if meta:
            meta["sub"] = ident
            if not meta.get("name"):
                meta["name"] = " ".join([str(meta.get("first_name") or ""), str(meta.get("last_name") or "")]).strip()
            return normalise_membership_metadata(meta)
    except Exception:
        pass
    try:
        return resolve_user_summary(ident)
    except Exception:
        return {"sub": ident, "name": ident}


def chime_attendance_key(meeting_id: str, attendance_id: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": f"CHIME#ATTENDANCE#{meeting_id}"}, "sk": {"S": f"ATTEND#{attendance_id}"}}


def chime_attendance_pk(meeting_id: str) -> str:
    return f"CHIME#ATTENDANCE#{meeting_id}"


def list_chime_manual_attendance(meeting_id: str) -> List[Dict[str, Any]]:
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": chime_attendance_pk(meeting_id)}},
        Limit=500,
    )
    items = [item_to_python(x) for x in resp.get("Items") or []]
    items.sort(key=lambda x: (str(x.get("attendance_type") or ""), str(x.get("member_name") or x.get("guest_name") or "")))
    return items


def chime_total_voting_members() -> int:
    total = 0
    try:
        for member in list_member_summaries(""):
            if chime_member_voting_eligible(member):
                total += 1
    except Exception:
        return 0
    return total


def chime_total_committee_members() -> int:
    total = 0
    try:
        seen = set()
        for member in list_member_summaries(""):
            mid = chime_member_id_from_summary(member)
            if mid and mid in seen:
                continue
            if chime_member_committee_eligible(member):
                total += 1
                if mid:
                    seen.add(mid)
    except Exception:
        return 0
    return total


def chime_present_member_ids(meeting_id: str) -> set[str]:
    ids: set[str] = set()
    for attendee in list_chime_attendees(meeting_id):
        mid = str(attendee.get("member_sub") or attendee.get("member_id") or "").strip()
        if mid:
            ids.add(mid)
    for entry in list_chime_manual_attendance(meeting_id):
        if str(entry.get("attendance_type") or "") == "in_person":
            mid = str(entry.get("member_id") or "").strip()
            if mid:
                ids.add(mid)
    return ids


def chime_current_member_is_present(meeting_id: str, claims: Dict[str, Any]) -> bool:
    member_id = chime_current_member_id(claims)
    return bool(member_id and member_id in chime_present_member_ids(meeting_id))


def chime_member_is_marked_in_person(meeting_id: str, member_id: str) -> bool:
    mid = str(member_id or "").strip()
    if not mid:
        return False
    for entry in list_chime_manual_attendance(meeting_id):
        if str(entry.get("attendance_type") or "") == "in_person" and str(entry.get("member_id") or "") == mid:
            return True
    return False


def chime_build_quorum(active: Dict[str, Any], online_attendees: List[Dict[str, Any]], manual_attendees: List[Dict[str, Any]]) -> Dict[str, Any]:
    meeting_type = normalise_chime_meeting_type(active.get("meeting_type"))
    online_by_member: Dict[str, Dict[str, Any]] = {}
    in_person_by_member: Dict[str, Dict[str, Any]] = {}
    guests = [x for x in manual_attendees if str(x.get("attendance_type") or "") == "guest"]
    online_guests = [x for x in online_attendees if str(x.get("attendance_type") or "").startswith("guest")]
    for attendee in online_attendees:
        mid = str(attendee.get("member_sub") or attendee.get("member_id") or "").strip()
        if not mid:
            continue
        online_by_member[mid] = attendee
    for entry in manual_attendees:
        if str(entry.get("attendance_type") or "") != "in_person":
            continue
        mid = str(entry.get("member_id") or "").strip()
        if mid:
            in_person_by_member[mid] = entry
    all_present_ids = set(online_by_member) | set(in_person_by_member)
    eligible_ids = set()
    committee_ids = set()
    present_member_summaries: Dict[str, Dict[str, Any]] = {}
    for mid in all_present_ids:
        member = chime_member_summary_by_id(mid)
        present_member_summaries[mid] = member
        if chime_member_voting_eligible(member):
            eligible_ids.add(mid)
        if chime_member_committee_eligible(member):
            committee_ids.add(mid)
    online_eligible = len([mid for mid in online_by_member if mid in eligible_ids and mid not in in_person_by_member])
    in_person_eligible = len([mid for mid in in_person_by_member if mid in eligible_ids])
    non_voting_present = max(0, len(all_present_ids) - len(eligible_ids))
    total_committee = chime_total_committee_members()
    total_voting = chime_total_voting_members()
    if meeting_type == "committee":
        required = (total_committee // 2) + 1 if total_committee else 0
        present = len(committee_ids)
        met = bool(required and present >= required)
        label = "Committee quorum"
        total_eligible = total_committee
    elif meeting_type in {"general", "agm"}:
        required = int(math.ceil(total_voting * 0.10)) if total_voting else 0
        present = len(eligible_ids)
        met = bool(required and present >= required)
        label = "General meeting quorum" if meeting_type == "general" else "AGM quorum"
        total_eligible = total_voting
    else:
        required = 0
        present = len(eligible_ids)
        met = False
        label = "No formal quorum required"
        total_eligible = total_voting
    return {
        "meeting_type": meeting_type,
        "label": label,
        "required": required,
        "present_eligible": present,
        "online_eligible": online_eligible,
        "in_person_eligible": in_person_eligible,
        "online_total": len(online_by_member),
        "in_person_total": len(in_person_by_member),
        "total_present_deduped": len(all_present_ids),
        "non_voting_present": non_voting_present,
        "guests_present": len(guests) + len(online_guests),
        "total_eligible_voting_members": total_voting,
        "total_committee_members": total_committee,
        "total_eligible_for_quorum": total_eligible,
        "met": met,
        "eligible_member_ids": sorted(eligible_ids),
        "committee_member_ids": sorted(committee_ids),
    }



MEETING_AGENDA_TYPES = {"committee", "general", "agm"}
MEETING_AGENDA_LABELS = {
    "committee": "Committee Meeting",
    "general": "General Meeting",
    "agm": "Annual General Meeting",
}
MEETING_AGENDA_PK = "MEETING#AGENDA"
MEETING_AGENDA_MINUTES_PK = "MEETING#MINUTES"
MEETING_AGENDA_SUGGESTIONS_PK = "MEETING#SUGGESTIONS"
MEETING_AGENDA_SECTIONS = [
    {"id": "opening", "label": "Opening / Welcome"},
    {"id": "attendance", "label": "Attendance"},
    {"id": "apologies", "label": "Apologies"},
    {"id": "previous-minutes", "label": "Confirmation of previous minutes"},
    {"id": "reports", "label": "Reports"},
    {"id": "business-arising", "label": "Business arising"},
    {"id": "motions", "label": "Motions / voting items"},
    {"id": "general-business", "label": "General business"},
    {"id": "actions", "label": "Actions"},
    {"id": "next-meeting", "label": "Next meeting"},
    {"id": "close", "label": "Close"},
]


def pdf_escape(text: str) -> str:
    return str(text or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_pdf_text(text: str, width: int = 90) -> List[str]:
    words = re.split(r"\s+", str(text or "").strip())
    lines: List[str] = []
    current = ""
    for word in words:
        if not word:
            continue
        if len(current) + len(word) + (1 if current else 0) <= width:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word[:width]
    if current:
        lines.append(current)
    return lines or [""]


def build_simple_pdf(pages: List[List[str]]) -> bytes:
    objects: List[bytes] = []
    page_obj_nums: List[int] = []
    font_obj_num = 3
    for lines in pages:
        content_lines = ["BT", "/F1 10 Tf", "72 780 Td", "14 TL"]
        for idx, line in enumerate(lines):
            if idx:
                content_lines.append("T*")
            content_lines.append(f"({pdf_escape(line)}) Tj")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", "replace")
        content_obj_num = len(objects) + 4
        page_obj_num = len(objects) + 5
        objects.append(f"{content_obj_num} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream\nendobj\n")
        objects.append(f"{page_obj_num} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_obj_num} 0 R >> >> /Contents {content_obj_num} 0 R >>\nendobj\n".encode("ascii"))
        page_obj_nums.append(page_obj_num)
    catalog = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    pages_obj = f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_nums)} >>\nendobj\n".encode("ascii")
    font_obj = b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    all_objs = [catalog, pages_obj, font_obj] + objects
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in all_objs:
        offsets.append(out.tell())
        out.write(obj)
    xref_pos = out.tell()
    total = len(all_objs) + 1
    out.write(f"xref\n0 {total}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("ascii"))
    out.write(f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii"))
    return out.getvalue()


def normalise_meeting_agenda_type(value: Any) -> str:
    text = str(value or "committee").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "general_meeting": "general",
        "annual_general_meeting": "agm",
        "annual": "agm",
        "committee_meeting": "committee",
    }
    text = aliases.get(text, text)
    return text if text in MEETING_AGENDA_TYPES else "committee"


def meeting_agenda_label(meeting_type: str) -> str:
    return MEETING_AGENDA_LABELS.get(normalise_meeting_agenda_type(meeting_type), "Meeting")


def meeting_agenda_current_key(meeting_type: str) -> Dict[str, Dict[str, str]]:
    return {"pk": {"S": f"{MEETING_AGENDA_PK}#{normalise_meeting_agenda_type(meeting_type).upper()}"}, "sk": {"S": "CURRENT"}}


def meeting_agenda_item_pk(meeting_type: str, meeting_id: str) -> str:
    return f"{MEETING_AGENDA_PK}#{normalise_meeting_agenda_type(meeting_type).upper()}#{meeting_agenda_safe_id(meeting_id)}"


def meeting_agenda_safe_id(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value or "").strip()).strip("-._:")
    return text[:96] or uuid.uuid4().hex


def meeting_agenda_minutes_source_pk(meeting_type: str, meeting_id: str) -> str:
    return f"{MEETING_AGENDA_MINUTES_PK}#SOURCE#{normalise_meeting_agenda_type(meeting_type).upper()}#{meeting_agenda_safe_id(meeting_id)}"


def meeting_agenda_minutes_filename(agenda: Dict[str, Any], minutes_id: str) -> str:
    mt = normalise_meeting_agenda_type(agenda.get("meeting_type"))
    label = meeting_agenda_label(mt).lower().replace("annual general meeting", "annual-general-meeting").replace("general meeting", "general-meeting").replace("committee meeting", "committee-meeting")
    date_text = str(agenda.get("scheduled_at") or agenda.get("created_at") or datetime.now(ZoneInfo(CLUB_TIME_ZONE)).date().isoformat()).strip()
    match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
    day = match.group(0) if match else datetime.now(ZoneInfo(CLUB_TIME_ZONE)).date().isoformat()
    return f"{day}-{label}-minutes-{meeting_agenda_safe_id(minutes_id)[:16]}.pdf"


def meeting_agenda_minutes_s3_key(agenda: Dict[str, Any], minutes_id: str) -> str:
    mt = normalise_meeting_agenda_type(agenda.get("meeting_type"))
    year = datetime.now(ZoneInfo(CLUB_TIME_ZONE)).strftime("%Y")
    scheduled = str(agenda.get("scheduled_at") or "")
    match = re.search(r"(\d{4})-\d{2}-\d{2}", scheduled)
    if match:
        year = match.group(1)
    return f"{MEETING_MINUTES_PREFIX}{mt}/{year}/{meeting_agenda_minutes_filename(agenda, minutes_id)}"


def meeting_agenda_preview_s3_key(agenda: Dict[str, Any]) -> str:
    mt = normalise_meeting_agenda_type(agenda.get("meeting_type"))
    year = datetime.now(ZoneInfo(CLUB_TIME_ZONE)).strftime("%Y")
    scheduled = str(agenda.get("scheduled_at") or "")
    match = re.search(r"(\d{4})-\d{2}-\d{2}", scheduled)
    if match:
        year = match.group(1)
    meeting_id = meeting_agenda_safe_id(agenda.get("meeting_id") or uuid.uuid4().hex)
    label = meeting_agenda_label(mt).lower().replace("annual general meeting", "annual-general-meeting").replace("general meeting", "general-meeting").replace("committee meeting", "committee-meeting")
    return f"{MEETING_MINUTES_PREFIX}_preview/{mt}/{year}/{meeting_id}-{label}-agenda-preview.pdf"


def meeting_agenda_latest_source_history(meeting_type: str, meeting_id: str) -> List[Dict[str, Any]]:
    pk = meeting_agenda_minutes_source_pk(meeting_type, meeting_id)
    try:
        resp = ddb.query(
            TableName=MEMBER_METADATA_TABLE,
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": {"S": pk}},
            ScanIndexForward=False,
            Limit=200,
        )
        return [item_to_python(raw) for raw in resp.get("Items") or []]
    except Exception as exc:
        print(f"Could not load meeting agenda source history: {exc}")
        return []


def meeting_agenda_put_source_history(meeting_type: str, meeting_id: str, item: Dict[str, Any]) -> None:
    mt = normalise_meeting_agenda_type(meeting_type)
    source_id = meeting_agenda_safe_id(meeting_id)
    if not source_id:
        return
    sk = str(item.get("sk") or f"HISTORY#{utc_now_precise()}#{uuid.uuid4().hex}")
    mirror = {**item, "pk": meeting_agenda_minutes_source_pk(mt, source_id), "sk": sk, "source_meeting_type": mt, "source_agenda_id": source_id}
    try:
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(mirror))
    except Exception as exc:
        print(f"Could not store meeting agenda source history mirror: {exc}")


def meeting_agenda_mailbox_address() -> str:
    return f"{MEETING_AGENDA_SERVICE_LOCAL_PART}@{webmail_inbound_domain()}"


def meeting_agenda_member_permissions(claims: Dict[str, Any]) -> Dict[str, Any]:
    summary = get_current_member_summary(claims)
    groups = get_groups(claims)
    position_ids = chime_position_ids_for_member(claims)
    is_admin_user = is_admin(claims)
    is_committee = bool(groups.intersection({"committee", "admins"})) or bool((get_club_position(summary.get("committee_position_id") or "") or {}).get("is_committee_position"))
    can_manage = is_admin_user or bool(position_ids.intersection(CHIME_LAUNCH_POSITION_IDS)) or is_committee
    can_close = is_admin_user or bool(position_ids.intersection({"president", "secretary", "treasurer"}))
    return {
        "member": summary,
        "is_committee": is_committee,
        "can_manage": can_manage,
        "can_close": can_close,
        "can_view_draft": can_manage,
        "can_vote": chime_member_is_financial(claims),
    }


def require_meeting_agenda_manage(claims: Dict[str, Any]) -> Dict[str, Any]:
    perms = meeting_agenda_member_permissions(claims)
    if not perms.get("can_manage"):
        raise PermissionError("Only authorised office bearers or committee members can manage meeting agendas.")
    return perms


def require_meeting_agenda_close(claims: Dict[str, Any]) -> Dict[str, Any]:
    perms = meeting_agenda_member_permissions(claims)
    if not perms.get("can_close"):
        raise PermissionError("This role is not allowed to finalise meeting minutes.")
    return perms


def meeting_agenda_default_items(meeting_type: str, agenda: Dict[str, Any], claims: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    mt = normalise_meeting_agenda_type(meeting_type)
    if mt == "agm":
        seed = [
            (1, "opening", "Welcome", ""),
            (2, "attendance", "Attendance", ""),
            (3, "apologies", "Apologies", ""),
            (4, "previous-minutes", "Confirmation of previous AGM minutes", ""),
            (5, "reports", "President's report", ""),
            (6, "reports", "Treasurer's report", ""),
            (7, "motions", "Elections / motions", ""),
            (8, "close", "Close", ""),
        ]
    elif mt == "general":
        seed = [
            (1, "opening", "Welcome", ""),
            (2, "attendance", "Attendance", ""),
            (3, "apologies", "Apologies", ""),
            (4, "previous-minutes", "Confirmation of previous minutes", ""),
            (5, "reports", "Reports", ""),
            (6, "motions", "Motions", ""),
            (7, "general-business", "General business", ""),
            (8, "close", "Close", ""),
        ]
    else:
        seed = [
            (1, "opening", "Welcome", ""),
            (2, "apologies", "Apologies", ""),
            (3, "previous-minutes", "Confirmation of previous minutes", ""),
            (4, "business-arising", "Business arising", ""),
            (5, "reports", "Reports", ""),
            (6, "general-business", "General business", ""),
            (7, "actions", "Actions", ""),
            (8, "next-meeting", "Next meeting", ""),
            (9, "close", "Close", ""),
        ]
    now = utc_now_precise()
    member = get_current_member_summary(claims or {}) if claims else {}
    items: List[Dict[str, Any]] = []
    for number, section_id, title, detail in seed:
        item_id = meeting_agenda_safe_id(f"{section_id}-{number}")
        items.append({
            "pk": meeting_agenda_item_pk(mt, agenda["meeting_id"]),
            "sk": f"ITEM#{item_id}",
            "item_type": "meeting_agenda_item",
            "meeting_type": mt,
            "meeting_id": agenda["meeting_id"],
            "item_id": item_id,
            "section_id": section_id,
            "sort_order": number,
            "title": title,
            "agenda_text": detail,
            "motion_text": "",
            "voting_enabled": False,
            "minute_text": "",
            "action_text": "",
            "action_assigned_to": "",
            "action_due": "",
            "status": "open",
            "system_item_key": item_id if title in {"Welcome", "Apologies", "Attendance"} else "",
            "raised_by_member_id": str(member.get("sub") or ""),
            "raised_by_name": str(member.get("name") or member.get("email") or ""),
            "created_at": now,
            "updated_at": now,
        })
    return items


def ensure_current_meeting_agenda(meeting_type: str, claims: Dict[str, Any] | None = None) -> Dict[str, Any]:
    require_metadata_table()
    mt = normalise_meeting_agenda_type(meeting_type)
    key = meeting_agenda_current_key(mt)
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=key, ConsistentRead=True)
    if resp.get("Item"):
        agenda = item_to_python(resp["Item"])
        if not meeting_agenda_list_items(mt, agenda.get("meeting_id") or ""):
            for item in meeting_agenda_default_items(mt, agenda, claims):
                ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
        return agenda
    now = utc_now_precise()
    member = get_current_member_summary(claims or {}) if claims else {}
    today = datetime.now(ZoneInfo(CLUB_TIME_ZONE)).date().isoformat()
    meeting_id = f"{mt}-{today}-{uuid.uuid4().hex[:8]}"
    agenda = {
        "pk": key["pk"]["S"],
        "sk": "CURRENT",
        "item_type": "meeting_current_agenda",
        "meeting_type": mt,
        "meeting_id": meeting_id,
        "title": meeting_agenda_label(mt),
        "scheduled_at": "",
        "start_time": "",
        "end_time": "",
        "location": "Hybrid / Chime",
        "chair": "",
        "secretary": "",
        "status": "draft",
        "sections": MEETING_AGENDA_SECTIONS,
        "created_at": now,
        "created_by": str(member.get("sub") or ""),
        "created_by_name": str(member.get("name") or member.get("email") or ""),
        "updated_at": now,
        "updated_by": str(member.get("sub") or ""),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(agenda))
    for item in meeting_agenda_default_items(mt, agenda, claims):
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return agenda


def meeting_agenda_item_sort_value(value: Any, default: int = 999999) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def meeting_agenda_list_items(meeting_type: str, meeting_id: str) -> List[Dict[str, Any]]:
    if not meeting_id:
        return []
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": {"S": meeting_agenda_item_pk(meeting_type, meeting_id)}, ":prefix": {"S": "ITEM#"}},
    )
    items = [item_to_python(raw) for raw in resp.get("Items") or []]
    items.sort(key=lambda item: (meeting_agenda_item_sort_value(item.get("sort_order")), str(item.get("section_id") or ""), str(item.get("title") or "")))
    return items


def meeting_agenda_clean_text(value: Any, limit: int = 5000) -> str:
    return re.sub(r"\r\n?", "\n", str(value or "").strip())[:limit]


def meeting_agenda_write_numbered_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(items, key=lambda item: (meeting_agenda_item_sort_value(item.get("sort_order")), str(item.get("title") or "")))
    for idx, item in enumerate(ordered, start=1):
        item["sort_order"] = idx
        item["updated_at"] = utc_now_precise()
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return ordered


def meeting_agenda_save_item_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    perms = require_meeting_agenda_manage(claims)
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type") or get_query_params(event).get("type"))
    agenda = ensure_current_meeting_agenda(mt, claims)
    item_id = meeting_agenda_safe_id(body.get("item_id") or uuid.uuid4().hex)
    existing_resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": meeting_agenda_item_pk(mt, agenda["meeting_id"])}, "sk": {"S": f"ITEM#{item_id}"}}, ConsistentRead=True)
    existing = item_to_python(existing_resp.get("Item") or {}) if existing_resp.get("Item") else {}
    member = perms.get("member") or {}
    item = {
        **existing,
        "pk": meeting_agenda_item_pk(mt, agenda["meeting_id"]),
        "sk": f"ITEM#{item_id}",
        "item_type": "meeting_agenda_item",
        "meeting_type": mt,
        "meeting_id": agenda["meeting_id"],
        "item_id": item_id,
        "section_id": meeting_agenda_safe_id(body.get("section_id") or existing.get("section_id") or "general-business"),
        "sort_order": meeting_agenda_item_sort_value(body.get("sort_order") or existing.get("sort_order"), 1),
        "title": meeting_agenda_clean_text(body.get("title") or existing.get("title") or "Agenda item", 240),
        "agenda_text": meeting_agenda_clean_text(body.get("agenda_text") if "agenda_text" in body else existing.get("agenda_text"), 4000),
        "motion_text": meeting_agenda_clean_text(body.get("motion_text") if "motion_text" in body else existing.get("motion_text"), 2000),
        "voting_enabled": bool(body.get("voting_enabled", existing.get("voting_enabled", False))),
        "minute_text": meeting_agenda_clean_text(body.get("minute_text") if "minute_text" in body else existing.get("minute_text"), 6000),
        "action_text": meeting_agenda_clean_text(body.get("action_text") if "action_text" in body else existing.get("action_text"), 2000),
        "action_assigned_to": meeting_agenda_clean_text(body.get("action_assigned_to") if "action_assigned_to" in body else existing.get("action_assigned_to"), 240),
        "action_due": meeting_agenda_clean_text(body.get("action_due") if "action_due" in body else existing.get("action_due"), 80),
        "status": meeting_agenda_clean_text(body.get("status") or existing.get("status") or "open", 80),
        "raised_by_member_id": meeting_agenda_clean_text(body.get("raised_by_member_id") or existing.get("raised_by_member_id") or member.get("sub") or "", 200),
        "raised_by_name": meeting_agenda_clean_text(body.get("raised_by_name") or existing.get("raised_by_name") or member.get("name") or member.get("email") or "", 240),
        "created_at": existing.get("created_at") or utc_now_precise(),
        "updated_at": utc_now_precise(),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    items = meeting_agenda_write_numbered_items(meeting_agenda_list_items(mt, agenda["meeting_id"]))
    return response(200, {"message": "Agenda item saved.", "item": item, "items": items})


def meeting_agenda_delete_item_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_meeting_agenda_manage(claims)
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type") or get_query_params(event).get("type"))
    agenda = ensure_current_meeting_agenda(mt, claims)
    item_id = meeting_agenda_safe_id(body.get("item_id") or "")
    if not item_id:
        raise ValueError("Agenda item id is required.")
    ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": meeting_agenda_item_pk(mt, agenda["meeting_id"])}, "sk": {"S": f"ITEM#{item_id}"}})
    items = meeting_agenda_write_numbered_items(meeting_agenda_list_items(mt, agenda["meeting_id"]))
    return response(200, {"message": "Agenda item deleted.", "items": items})


def meeting_agenda_current_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    params = get_query_params(event)
    mt = normalise_meeting_agenda_type(params.get("type"))
    agenda = ensure_current_meeting_agenda(mt, claims)
    items = meeting_agenda_list_items(mt, agenda.get("meeting_id") or "")
    perms = meeting_agenda_member_permissions(claims)
    return response(200, {
        "agenda": agenda,
        "items": items,
        "sections": MEETING_AGENDA_SECTIONS,
        "meeting_types": [{"id": key, "label": value} for key, value in MEETING_AGENDA_LABELS.items()],
        "permissions": {k: bool(perms.get(k)) for k in ["is_committee", "can_manage", "can_view_draft", "can_close", "can_vote"]},
        "suggestion_email": meeting_agenda_mailbox_address(),
    })


def meeting_agenda_save_meeting_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_meeting_agenda_manage(claims)
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type"))
    agenda = ensure_current_meeting_agenda(mt, claims)
    for key in ["title", "scheduled_at", "start_time", "end_time", "location", "chair", "secretary", "status"]:
        if key in body:
            agenda[key] = meeting_agenda_clean_text(body.get(key), 500)
    agenda["updated_at"] = utc_now_precise()
    agenda["updated_by"] = str((get_current_member_summary(claims)).get("sub") or "")
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(agenda))
    return response(200, {"message": "Meeting details saved.", "agenda": agenda})


def meeting_agenda_create_suggestion_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type"))
    title = meeting_agenda_clean_text(body.get("title"), 240)
    details = meeting_agenda_clean_text(body.get("details"), 5000)
    if not title:
        raise ValueError("Suggestion title is required.")
    member = get_current_member_summary(claims)
    now = utc_now_precise()
    sid = meeting_agenda_safe_id(f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:10]}")
    item = {
        "pk": f"{MEETING_AGENDA_SUGGESTIONS_PK}#{mt.upper()}",
        "sk": f"SUGGESTION#{now}#{sid}",
        "item_type": "meeting_agenda_suggestion",
        "meeting_type": mt,
        "suggestion_id": sid,
        "title": title,
        "details": details,
        "section_id": meeting_agenda_safe_id(body.get("section_id") or "general-business"),
        "status": "open",
        "raised_by_member_id": str(member.get("sub") or ""),
        "raised_by_name": str(member.get("name") or member.get("email") or ""),
        "created_at": now,
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
    return response(200, {"message": "Agenda suggestion submitted.", "item": item})


def meeting_agenda_list_suggestions(meeting_type: str, status: str = "open") -> List[Dict[str, Any]]:
    mt = normalise_meeting_agenda_type(meeting_type)
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": {"S": f"{MEETING_AGENDA_SUGGESTIONS_PK}#{mt.upper()}"}, ":prefix": {"S": "SUGGESTION#"}},
        ScanIndexForward=False,
        Limit=100,
    )
    items = [item_to_python(raw) for raw in resp.get("Items") or []]
    if status and status != "all":
        items = [item for item in items if str(item.get("status") or "open") == status]
    return items


def meeting_agenda_suggestions_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_meeting_agenda_manage(claims)
    params = get_query_params(event)
    mt = normalise_meeting_agenda_type(params.get("type"))
    status = str(params.get("status") or "open")
    return response(200, {"items": meeting_agenda_list_suggestions(mt, status), "suggestion_email": meeting_agenda_mailbox_address()})


def meeting_agenda_add_suggestion_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type"))
    sid = str(body.get("suggestion_id") or "")
    suggestion = None
    for item in meeting_agenda_list_suggestions(mt, "all"):
        if str(item.get("suggestion_id") or "") == sid:
            suggestion = item
            break
    if not suggestion:
        raise ValueError("Suggestion not found.")
    save_event = {"body": json.dumps({
        "meeting_type": mt,
        "section_id": suggestion.get("section_id") or "general-business",
        "sort_order": body.get("sort_order") or 9999,
        "title": suggestion.get("title") or "Agenda suggestion",
        "agenda_text": suggestion.get("details") or "",
        "raised_by_member_id": suggestion.get("raised_by_member_id") or "",
        "raised_by_name": suggestion.get("raised_by_name") or "",
        "status": "open",
    })}
    result = meeting_agenda_save_item_route(save_event, claims)
    suggestion["status"] = "added"
    suggestion["added_at"] = utc_now_precise()
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(suggestion))
    return result


def meeting_agenda_dismiss_suggestion_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_meeting_agenda_manage(claims)
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type"))
    sid = str(body.get("suggestion_id") or "")
    for item in meeting_agenda_list_suggestions(mt, "all"):
        if str(item.get("suggestion_id") or "") == sid:
            item["status"] = "dismissed"
            item["dismissed_at"] = utc_now_precise()
            item["dismissal_note"] = meeting_agenda_clean_text(body.get("note") or "", 500)
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
            return response(200, {"message": "Suggestion dismissed.", "item": item})
    raise ValueError("Suggestion not found.")


def meeting_agenda_source_history_summary(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    attendance = []
    votes = []
    flagged_chat = []
    for item in history:
        item_type = str(item.get("item_type") or "")
        if item_type == "chime_attendance_snapshot":
            attendance.append(item)
        elif item_type == "chime_vote_result":
            votes.append(item)
        elif item_type == "chime_flagged_chat":
            flagged_chat.append(item)
    attendance.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    votes.sort(key=lambda x: str(x.get("closed_at") or x.get("created_at") or ""))
    flagged_chat.sort(key=lambda x: str(x.get("created_at") or ""))
    return {"latest_attendance": attendance[0] if attendance else {}, "vote_results": votes, "flagged_chat": flagged_chat}


def meeting_agenda_pdf_pages_from_lines(lines: List[str], width: int = 92, page_size: int = 50) -> List[List[str]]:
    pages: List[List[str]] = []
    page: List[str] = []
    for raw in lines:
        text = str(raw or "")
        wrapped = wrap_pdf_text(text, width) if len(text) > width else [text]
        for line in wrapped:
            page.append(line)
            if len(page) >= page_size:
                pages.append(page)
                page = []
    if page:
        pages.append(page)
    return pages or [["LROC Meeting Minutes"]]


def build_meeting_minutes_pdf(agenda: Dict[str, Any], items: List[Dict[str, Any]], finalised_by: str, finalised_at: str, history: List[Dict[str, Any]] | None = None) -> bytes:
    section_labels = {s["id"]: s["label"] for s in MEETING_AGENDA_SECTIONS}
    mt = normalise_meeting_agenda_type(agenda.get("meeting_type"))
    meeting_label = meeting_agenda_label(mt)
    title = agenda.get("title") or meeting_label
    history_summary = meeting_agenda_source_history_summary(history or [])
    attendance = history_summary.get("latest_attendance") or {}
    quorum = attendance.get("quorum") if isinstance(attendance.get("quorum"), dict) else {}
    lines: List[str] = [
        "LAND ROVER OWNERS CLUB OF AUSTRALIA, SYDNEY BRANCH INC.",
        f"{meeting_label.upper()} MINUTES",
        "=" * 72,
        "",
        f"Meeting: {title}",
        f"Date/time: {agenda.get('scheduled_at') or 'Not specified'}",
        f"Start time: {agenda.get('start_time') or 'Not specified'}",
        f"End time: {agenda.get('end_time') or 'Not specified'}",
        f"Location: {agenda.get('location') or 'Not specified'}",
        f"Chair: {agenda.get('chair') or 'Not specified'}",
        f"Secretary / minute taker: {agenda.get('secretary') or 'Not specified'}",
        f"Finalised: {finalised_at}",
        f"Finalised by: {finalised_by}",
        "",
    ]
    if quorum:
        lines.extend([
            "QUORUM AND ATTENDANCE SUMMARY",
            "-" * 72,
            f"Quorum rule: {quorum.get('label') or 'Not recorded'}",
            f"Eligible pool: {quorum.get('total_eligible_for_quorum', quorum.get('total_eligible_voting_members', 'Not recorded'))}",
            f"Required quorum: {quorum.get('required', 'Not recorded')}",
            f"Eligible members present: {quorum.get('present_eligible', 'Not recorded')}",
            f"Online eligible: {quorum.get('online_eligible', 0)}",
            f"In-person eligible: {quorum.get('in_person_eligible', 0)}",
            f"Non-voting members present: {quorum.get('non_voting_present', 0)}",
            f"Guests present: {quorum.get('guests_present', 0)}",
            f"Quorum status: {'Met' if quorum.get('met') else 'Not met / not recorded as met'}",
            "",
        ])
        online = attendance.get("online_attendees") if isinstance(attendance.get("online_attendees"), list) else []
        in_person = attendance.get("in_person_attendees") if isinstance(attendance.get("in_person_attendees"), list) else []
        guests = attendance.get("guests") if isinstance(attendance.get("guests"), list) else []
        if online:
            lines.append("Online attendees")
            for person in online:
                lines.append(f"  - {person.get('member_name') or 'LROC member'}{' (voting eligible)' if person.get('voting_eligible') else ''}")
        if in_person:
            lines.append("In-person attendees")
            for person in in_person:
                num = f" #{person.get('member_number')}" if person.get("member_number") else ""
                lines.append(f"  - {person.get('member_name') or 'LROC member'}{num}{' (voting eligible)' if person.get('voting_eligible') else ''}")
        if guests:
            lines.append("Guests")
            for guest in guests:
                lines.append(f"  - {guest.get('guest_name') or 'Guest'}{': ' + str(guest.get('notes')) if guest.get('notes') else ''}")
        lines.append("")
    else:
        lines.extend(["QUORUM AND ATTENDANCE SUMMARY", "-" * 72, "No attendance/quorum snapshot was linked to this agenda before finalisation.", ""])

    lines.extend(["AGENDA, MOTIONS AND MINUTES", "=" * 72])
    current_section = None
    for item in sorted(items, key=lambda x: (meeting_agenda_item_sort_value(x.get("sort_order")), str(x.get("section_id") or ""), str(x.get("title") or ""))):
        section = str(item.get("section_id") or "general-business")
        if section != current_section:
            current_section = section
            lines.extend(["", section_labels.get(section, section.replace("-", " ").title()).upper(), "-" * 72])
        lines.append(f"{item.get('sort_order') or ''}. {item.get('title') or 'Agenda item'}")
        if item.get("agenda_text"):
            lines.append(f"  Background: {item.get('agenda_text')}")
        if item.get("motion_text"):
            lines.append(f"  Motion: {item.get('motion_text')}")
        last_vote = item.get("last_vote_result") if isinstance(item.get("last_vote_result"), dict) else {}
        if last_vote:
            results = last_vote.get("results") if isinstance(last_vote.get("results"), dict) else {}
            result_text = "; ".join([f"{k}: {v}" for k, v in results.items()])
            lines.append(f"  Secret ballot result: {result_text}. Total votes: {last_vote.get('total_votes', sum(int(v or 0) for v in results.values()))}")
        if item.get("minute_text"):
            lines.append(f"  Minute/outcome: {item.get('minute_text')}")
        if item.get("action_text"):
            action = f"  Action: {item.get('action_text')}"
            if item.get("action_assigned_to"):
                action += f" | Assigned to: {item.get('action_assigned_to')}"
            if item.get("action_due"):
                action += f" | Due: {item.get('action_due')}"
            lines.append(action)
        if item.get("status"):
            lines.append(f"  Status: {item.get('status')}")
    flagged = history_summary.get("flagged_chat") or []
    if flagged:
        lines.extend(["", "FLAGGED CHAT ITEMS", "=" * 72])
        for msg in flagged:
            lines.append(f"- {msg.get('member_name') or 'Member'} at {msg.get('created_at') or ''}: {msg.get('message') or ''}")
    lines.extend(["", "DOCUMENT CONTROL", "=" * 72, "This PDF was generated by the LROC member system from the finalised meeting agenda and linked formal meeting records."])
    return build_simple_pdf(meeting_agenda_pdf_pages_from_lines(lines))


def meeting_agenda_finalise_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    perms = require_meeting_agenda_close(claims)
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type") or get_query_params(event).get("type"))
    agenda = ensure_current_meeting_agenda(mt, claims)
    items = meeting_agenda_list_items(mt, agenda["meeting_id"])
    if not items:
        raise ValueError("The current agenda has no items to finalise.")
    member_name = str((perms.get("member") or {}).get("name") or (perms.get("member") or {}).get("email") or "Authorised member")
    finalised_at = utc_now_precise()
    source_history = meeting_agenda_latest_source_history(mt, agenda.get("meeting_id") or "")
    pdf_bytes = build_meeting_minutes_pdf(agenda, items, member_name, finalised_at, source_history)
    minutes_id = meeting_agenda_safe_id(f"{agenda['meeting_id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    key = meeting_agenda_minutes_s3_key(agenda, minutes_id)
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
        ServerSideEncryption="AES256",
        Metadata={"meeting-type": mt, "meeting-id": str(agenda.get("meeting_id") or ""), "minutes-id": minutes_id},
    )
    minutes_item = {
        "pk": f"{MEETING_AGENDA_MINUTES_PK}#{mt.upper()}",
        "sk": f"MINUTES#{finalised_at}#{minutes_id}",
        "item_type": "meeting_minutes",
        "meeting_type": mt,
        "minutes_id": minutes_id,
        "meeting_id": agenda["meeting_id"],
        "title": agenda.get("title") or meeting_agenda_label(mt),
        "scheduled_at": agenda.get("scheduled_at") or "",
        "start_time": agenda.get("start_time") or "",
        "end_time": agenda.get("end_time") or "",
        "location": agenda.get("location") or "",
        "chair": agenda.get("chair") or "",
        "secretary": agenda.get("secretary") or "",
        "finalised_at": finalised_at,
        "finalised_by": str((perms.get("member") or {}).get("sub") or ""),
        "finalised_by_name": member_name,
        "pdf_key": key,
        "pdf_filename": os.path.basename(key),
        "s3_prefix": "/".join(key.split("/")[:-1]) + "/",
        "history_item_count": len(source_history),
        "item_count": len(items),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(minutes_item))
    for item in items:
        ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": str(item.get("pk"))}, "sk": {"S": str(item.get("sk"))}})
    ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=meeting_agenda_current_key(mt))
    new_agenda = ensure_current_meeting_agenda(mt, claims)
    next_number = len(meeting_agenda_list_items(mt, new_agenda["meeting_id"])) + 1
    for old in items:
        if str(old.get("system_item_key") or ""):
            continue
        if str(old.get("status") or "").lower() in {"open", "deferred", "rolled-forward"}:
            try:
                meeting_agenda_save_item_route({"body": json.dumps({
                    "meeting_type": mt,
                    "section_id": old.get("section_id") or "general-business",
                    "sort_order": next_number,
                    "title": old.get("title") or "Rolled forward item",
                    "agenda_text": old.get("action_text") or old.get("agenda_text") or "",
                    "motion_text": old.get("motion_text") or "",
                    "voting_enabled": bool(old.get("voting_enabled")),
                    "raised_by_member_id": old.get("raised_by_member_id") or "",
                    "raised_by_name": old.get("raised_by_name") or "",
                    "status": "open",
                })}, claims)
                next_number += 1
            except Exception:
                pass
    return response(200, {"message": "Meeting minutes finalised and the next current agenda has been created.", "minutes": minutes_item, "next_agenda": new_agenda})


def meeting_agenda_preview_pdf_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_meeting_agenda_manage(claims)
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type") or get_query_params(event).get("type"))
    agenda = ensure_current_meeting_agenda(mt, claims)
    items = meeting_agenda_list_items(mt, agenda.get("meeting_id") or "")
    if not items:
        raise ValueError("The current agenda has no items to preview.")
    member = get_current_member_summary(claims)
    generated_by = str(member.get("name") or member.get("email") or "Authorised member")
    generated_at = utc_now_precise()
    source_history = meeting_agenda_latest_source_history(mt, agenda.get("meeting_id") or "")
    # Use the same renderer as finalised minutes so the preview closely matches the production output.
    pdf_bytes = build_meeting_minutes_pdf(agenda, items, generated_by, f"Preview generated {generated_at}", source_history)
    key = meeting_agenda_preview_s3_key(agenda)
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
        ServerSideEncryption="AES256",
        Metadata={"meeting-type": mt, "meeting-id": str(agenda.get("meeting_id") or ""), "preview": "true"},
    )
    filename = os.path.basename(key)
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key, "ResponseContentDisposition": f'inline; filename="{filename}"', "ResponseContentType": "application/pdf"},
        ExpiresIn=DOWNLOAD_EXPIRY,
    )
    return response(200, {"url": url, "key": key, "filename": filename, "message": "Agenda preview PDF generated."})


def meeting_agenda_list_minutes(meeting_type: str, limit: int = 50) -> List[Dict[str, Any]]:
    mt = normalise_meeting_agenda_type(meeting_type)
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": {"S": f"{MEETING_AGENDA_MINUTES_PK}#{mt.upper()}"}, ":prefix": {"S": "MINUTES#"}},
        ScanIndexForward=False,
        Limit=limit,
    )
    return [item_to_python(raw) for raw in resp.get("Items") or []]


def meeting_agenda_minutes_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    params = get_query_params(event)
    mt = normalise_meeting_agenda_type(params.get("type"))
    limit = int(params.get("limit") or 50)
    perms = meeting_agenda_member_permissions(claims)
    return response(200, {"items": meeting_agenda_list_minutes(mt, limit), "permissions": {k: bool(perms.get(k)) for k in ["is_committee", "can_manage", "can_view_draft", "can_close"]}})


def meeting_agenda_minutes_download_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    mt = normalise_meeting_agenda_type(body.get("meeting_type") or get_query_params(event).get("type"))
    minutes_id = meeting_agenda_safe_id(body.get("minutes_id") or "")
    found = None
    for item in meeting_agenda_list_minutes(mt, 100):
        if str(item.get("minutes_id") or "") == minutes_id:
            found = item
            break
    if not found:
        raise ValueError("Minutes record not found.")
    key = str(found.get("pdf_key") or "")
    if not key.startswith(MEETING_MINUTES_PREFIX):
        raise PermissionError("Invalid minutes file key.")
    url = s3.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": key, "ResponseContentDisposition": f'attachment; filename="{minutes_id}.pdf"'}, ExpiresIn=DOWNLOAD_EXPIRY)
    return response(200, {"url": url})


def meeting_agenda_items_for_chime(meeting_type: str) -> List[Dict[str, Any]]:
    mt = normalise_meeting_agenda_type(meeting_type)
    agenda = ensure_current_meeting_agenda(mt, None)
    out: List[Dict[str, Any]] = []
    for item in meeting_agenda_list_items(mt, agenda.get("meeting_id") or ""):
        out.append({
            "item_id": str(item.get("item_id") or ""),
            "number": meeting_agenda_item_sort_value(item.get("sort_order")),
            "title": str(item.get("title") or "Agenda item"),
            "detail": str(item.get("agenda_text") or ""),
            "motion_text": str(item.get("motion_text") or ""),
            "voting_enabled": bool(item.get("voting_enabled")),
            "vote_title": str(item.get("motion_text") or item.get("title") or "Agenda item"),
            "source_agenda_id": str(agenda.get("meeting_id") or ""),
            "source_meeting_type": mt,
        })
    return out

def chime_public_meeting_summary(item: Dict[str, Any] | None = None) -> Dict[str, Any]:
    item = dict(item or {})
    if not item:
        return {"active": False}
    return {
        "active": str(item.get("status") or "") == "active",
        "meeting_id": str(item.get("meeting_id") or ""),
        "title": str(item.get("title") or CHIME_DEFAULT_MEETING_TITLE),
        "created_at": str(item.get("created_at") or ""),
        "created_by_name": str(item.get("created_by_name") or ""),
        "media_region": str(item.get("media_region") or CHIME_MEDIA_REGION),
        "meeting_type": normalise_chime_meeting_type(item.get("meeting_type")),
        "meeting_type_label": CHIME_MEETING_TYPE_LABELS.get(normalise_chime_meeting_type(item.get("meeting_type")), "Monthly meeting"),
        "formal_controls_enabled": chime_meeting_is_formal(item),
    }


def get_active_chime_meeting() -> Dict[str, Any] | None:
    require_chime_meetings()
    resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=chime_active_key(), ConsistentRead=True)
    item = item_to_python(resp.get("Item") or {}) if resp.get("Item") else None
    if not item or str(item.get("status") or "") != "active":
        return None
    created_at = str(item.get("created_at") or "")
    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - created_dt > timedelta(hours=CHIME_MEETING_MAX_AGE_HOURS):
            ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=chime_active_key())
            item["status"] = "expired"
            item["ended_at"] = utc_now_precise()
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item | {"sk": f"MEETING#{item.get('meeting_id') or ''}"}))
            return None
    except Exception:
        pass
    return item


def save_active_chime_meeting(item: Dict[str, Any]) -> None:
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": CHIME_MEETING_PK, "sk": CHIME_ACTIVE_SK}))
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": CHIME_MEETING_PK, "sk": f"MEETING#{item['meeting_id']}"}))


def chime_status_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = get_active_chime_meeting()
    return response(200, {
        "enabled": CHIME_MEETINGS_ENABLED,
        "can_launch": can_launch_chime_meeting(claims),
        "can_end": can_launch_chime_meeting(claims),
        "launch_position_ids": sorted(CHIME_LAUNCH_POSITION_IDS),
        "meeting": chime_public_meeting_summary(active),
        "member_name": chime_member_name(claims),
        "member_is_financial": chime_member_is_financial(claims),
        "meeting_type_options": [{"value": key, "label": label, "formal": key in CHIME_FORMAL_MEETING_TYPES} for key, label in CHIME_MEETING_TYPE_LABELS.items()],
        "checked_at": utc_now_precise(),
    })


def launch_chime_meeting_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_chime_meetings()
    require_chime_launcher(claims)
    body = parse_body(event)
    existing = get_active_chime_meeting()
    if existing:
        return response(200, {"message": "An LROC meeting is already active.", "meeting": chime_public_meeting_summary(existing), "can_launch": True, "can_end": True})
    meeting_id = uuid.uuid4().hex
    meeting_type = normalise_chime_meeting_type(body.get("meeting_type"))
    title = str(body.get("title") or CHIME_MEETING_TYPE_LABELS.get(meeting_type) or CHIME_DEFAULT_MEETING_TITLE).strip()[:120] or CHIME_DEFAULT_MEETING_TITLE
    external_meeting_id = f"lroc-{meeting_id[:24]}"
    meeting_resp = chime.create_meeting(
        ClientRequestToken=meeting_id,
        MediaRegion=CHIME_MEDIA_REGION,
        ExternalMeetingId=external_meeting_id,
    )
    meeting = meeting_resp.get("Meeting") or meeting_resp
    summary = get_current_member_summary(claims)
    item = {
        "item_type": "chime_meeting",
        "meeting_id": meeting_id,
        "title": title,
        "meeting_type": meeting_type,
        "formal_controls_enabled": meeting_type in CHIME_FORMAL_MEETING_TYPES,
        "status": "active",
        "created_at": utc_now_precise(),
        "created_by_sub": str(claims.get("sub") or ""),
        "created_by_email": str(summary.get("email") or claims.get("email") or ""),
        "created_by_name": chime_member_name(claims),
        "media_region": CHIME_MEDIA_REGION,
        "chime_meeting_id": str(meeting.get("MeetingId") or ""),
        "external_meeting_id": external_meeting_id,
        "meeting": meeting,
    }
    save_active_chime_meeting(item)
    return response(200, {"message": "LROC meeting launched.", "meeting": chime_public_meeting_summary(item), "can_launch": True, "can_end": True})


def chime_mode_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_chime_meetings()
    require_chime_launcher(claims)
    active = chime_active_or_error()
    body = parse_body(event)
    meeting_type = normalise_chime_meeting_type(body.get("meeting_type"))
    title = str(body.get("title") or CHIME_MEETING_TYPE_LABELS.get(meeting_type) or active.get("title") or CHIME_DEFAULT_MEETING_TITLE).strip()[:120]
    updated = dict(active)
    updated["meeting_type"] = meeting_type
    updated["formal_controls_enabled"] = meeting_type in CHIME_FORMAL_MEETING_TYPES
    updated["title"] = title or CHIME_MEETING_TYPE_LABELS.get(meeting_type) or CHIME_DEFAULT_MEETING_TITLE
    updated["updated_at"] = utc_now_precise()
    updated["updated_by_name"] = chime_member_name(claims)
    save_active_chime_meeting(updated)
    return response(200, {"message": "Meeting mode updated.", "meeting": chime_public_meeting_summary(updated), "can_launch": True, "can_end": True})


def join_chime_meeting_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_chime_meetings()
    active = get_active_chime_meeting()
    if not active:
        raise ValueError("No LROC meeting is currently active.")
    meeting_id = str(active.get("meeting_id") or "")
    member_id = chime_current_member_id(claims)
    if chime_meeting_is_formal(active) and chime_member_is_marked_in_person(meeting_id, member_id):
        raise PermissionError("You have been marked as attending this formal meeting in person. Use the PWA meeting page for agenda and voting, but do not join the audio/video session.")
    chime_meeting_id = str(active.get("chime_meeting_id") or "")
    if not chime_meeting_id:
        raise RuntimeError("Active meeting is missing its Chime meeting ID.")
    sub = str(claims.get("sub") or claims.get("cognito:username") or uuid.uuid4().hex).strip()
    safe_name = re.sub(r'[^A-Za-z0-9_.-]+', '-', chime_member_name(claims)).strip('-')[:28] or 'member'
    external_user_id = f"{safe_name}-{sub[:24]}-{uuid.uuid4().hex[:6]}"[:64]
    attendee_resp = chime.create_attendee(MeetingId=chime_meeting_id, ExternalUserId=external_user_id)
    attendee = attendee_resp.get("Attendee") or attendee_resp
    attendee_id = str(attendee.get("AttendeeId") or uuid.uuid4().hex)
    summary = get_current_member_summary(claims)
    record = {
        "item_type": "chime_attendee",
        "meeting_id": meeting_id,
        "chime_meeting_id": chime_meeting_id,
        "attendee_id": attendee_id,
        "external_user_id": external_user_id,
        "member_sub": member_id or sub,
        "member_email": str(summary.get("email") or claims.get("email") or ""),
        "member_name": chime_member_name(claims),
        "joined_at": utc_now_precise(),
        "attendance_type": "online",
        "voting_eligible": chime_member_voting_eligible(summary),
        "committee_eligible": chime_member_committee_eligible(summary),
    }
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**record, "pk": f"CHIME#ATTENDEES#{meeting_id}", "sk": f"ATTENDEE#{attendee_id}"}))
    return response(200, {
        "message": "Joining active LROC meeting.",
        "meeting": {"Meeting": active.get("meeting") or {}},
        "attendee": {"Attendee": attendee},
        "meeting_summary": chime_public_meeting_summary(active),
        "member_name": chime_member_name(claims),
        "no_foyer": True,
    })




def list_chime_attendees(meeting_id: str) -> List[Dict[str, Any]]:
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": f"CHIME#ATTENDEES#{meeting_id}"}},
        Limit=200,
    )
    items = [item_to_python(x) for x in resp.get("Items") or []]
    items.sort(key=lambda x: str(x.get("joined_at") or ""))
    return items


def chime_attendance_member_search(query: str) -> List[Dict[str, Any]]:
    q = str(query or "").strip()
    if len(q) < 2:
        return []
    matches = list_member_summaries(q)[:20]
    out = []
    for member in matches:
        mid = chime_member_id_from_summary(member)
        if not mid:
            continue
        out.append({
            "member_id": mid,
            "name": str(member.get("name") or " ".join([str(member.get("first_name") or ""), str(member.get("last_name") or "")]).strip() or member.get("email") or mid),
            "email": str(member.get("email") or ""),
            "member_number": member_summary_display_number(member),
            "membership_status": str(member.get("membership_status") or ""),
            "voting_eligible": chime_member_voting_eligible(member),
            "committee_eligible": chime_member_committee_eligible(member),
        })
    return out


def chime_attendance_snapshot(active: Dict[str, Any], claims: Dict[str, Any] | None = None) -> Dict[str, Any]:
    meeting_id = str(active.get("meeting_id") or "")
    online = list_chime_attendees(meeting_id)
    manual = list_chime_manual_attendance(meeting_id)
    quorum = chime_build_quorum(active, online, manual)
    in_person = [x for x in manual if str(x.get("attendance_type") or "") == "in_person"]
    guests = [x for x in manual if str(x.get("attendance_type") or "") == "guest"]
    agenda = get_chime_agenda(meeting_id) if meeting_id else {}
    items = agenda.get("items") if isinstance(agenda.get("items"), list) else []
    source_agenda_id = ""
    source_meeting_type = normalise_chime_meeting_type(active.get("meeting_type"))
    for agenda_item in items:
        if agenda_item.get("source_agenda_id"):
            source_agenda_id = str(agenda_item.get("source_agenda_id") or "")
            source_meeting_type = str(agenda_item.get("source_meeting_type") or source_meeting_type)
            break
    return {
        "meeting_id": meeting_id,
        "meeting_type": normalise_chime_meeting_type(active.get("meeting_type")),
        "source_agenda_id": source_agenda_id,
        "source_meeting_type": source_meeting_type,
        "created_at": utc_now_precise(),
        "created_by_name": chime_member_name(claims or {}) if claims else "system",
        "quorum": {k: v for k, v in quorum.items() if k not in {"eligible_member_ids", "committee_member_ids"}},
        "online_attendees": [{
            "member_id": str(a.get("member_sub") or a.get("member_id") or ""),
            "member_name": str(a.get("member_name") or "LROC member"),
            "member_email": str(a.get("member_email") or ""),
            "joined_at": str(a.get("joined_at") or ""),
            "voting_eligible": bool(a.get("voting_eligible")),
            "committee_eligible": bool(a.get("committee_eligible")),
        } for a in online],
        "in_person_attendees": [{
            "member_id": str(a.get("member_id") or ""),
            "member_name": str(a.get("member_name") or "LROC member"),
            "member_email": str(a.get("member_email") or ""),
            "member_number": str(a.get("member_number") or ""),
            "added_at": str(a.get("added_at") or ""),
            "voting_eligible": bool(a.get("voting_eligible")),
            "committee_eligible": bool(a.get("committee_eligible")),
        } for a in in_person],
        "guests": [{
            "guest_name": str(a.get("guest_name") or "Guest"),
            "notes": str(a.get("notes") or ""),
            "added_at": str(a.get("added_at") or ""),
        } for a in guests],
    }


def chime_store_attendance_snapshot(active: Dict[str, Any], claims: Dict[str, Any] | None, reason: str) -> Dict[str, Any]:
    meeting_id = str(active.get("meeting_id") or "")
    snapshot = chime_attendance_snapshot(active, claims)
    snapshot["item_type"] = "chime_attendance_snapshot"
    snapshot["reason"] = str(reason or "snapshot")
    sk = f"ATTENDANCE#{snapshot['created_at']}#{snapshot['reason']}"
    ddb.put_item(
        TableName=MEMBER_METADATA_TABLE,
        Item=python_to_item({**snapshot, "pk": chime_history_key(meeting_id), "sk": sk})
    )
    if snapshot.get("source_agenda_id") and snapshot.get("source_meeting_type"):
        meeting_agenda_put_source_history(str(snapshot.get("source_meeting_type") or ""), str(snapshot.get("source_agenda_id") or ""), {**snapshot, "sk": sk})
    return snapshot


def chime_attendance_payload(active: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    meeting_id = str(active.get("meeting_id") or "")
    online = list_chime_attendees(meeting_id)
    manual = list_chime_manual_attendance(meeting_id)
    quorum = chime_build_quorum(active, online, manual)
    in_person = [x for x in manual if str(x.get("attendance_type") or "") == "in_person"]
    guests = [x for x in manual if str(x.get("attendance_type") or "") == "guest"]
    current_member_id = chime_current_member_id(claims)
    current_in_person = any(str(x.get("member_id") or "") == current_member_id for x in in_person)
    return {
        "meeting": chime_public_meeting_summary(active),
        "can_control": can_launch_chime_meeting(claims),
        "current_member_id": current_member_id,
        "current_member_in_person": current_in_person,
        "quorum": {k: v for k, v in quorum.items() if k != "eligible_member_ids"},
        "attendees": [{
            "attendee_id": str(a.get("attendee_id") or ""),
            "member_id": str(a.get("member_sub") or a.get("member_id") or ""),
            "member_name": str(a.get("member_name") or "LROC member"),
            "member_email": str(a.get("member_email") or ""),
            "joined_at": str(a.get("joined_at") or ""),
            "attendance_type": "online",
            "voting_eligible": bool(a.get("voting_eligible")),
            "committee_eligible": bool(a.get("committee_eligible")),
        } for a in online],
        "in_person": [{
            "attendance_id": str(a.get("attendance_id") or ""),
            "member_id": str(a.get("member_id") or ""),
            "member_name": str(a.get("member_name") or "LROC member"),
            "member_email": str(a.get("member_email") or ""),
            "member_number": str(a.get("member_number") or ""),
            "added_at": str(a.get("added_at") or ""),
            "voting_eligible": bool(a.get("voting_eligible")),
            "committee_eligible": bool(a.get("committee_eligible")),
            "attendance_type": "in_person",
        } for a in in_person],
        "guests": [{
            "attendance_id": str(a.get("attendance_id") or ""),
            "guest_name": str(a.get("guest_name") or "Guest"),
            "notes": str(a.get("notes") or ""),
            "added_at": str(a.get("added_at") or ""),
            "attendance_type": "guest",
        } for a in guests],
    }


def chime_attendance_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = chime_active_or_error()
    meeting_id = str(active.get("meeting_id") or "")
    method = event.get("requestContext", {}).get("http", {}).get("method")
    guests_allowed = chime_guests_allowed(active)
    if method == "POST":
        require_chime_launcher(claims)
        body = parse_body(event)
        action = str(body.get("action") or "").strip().lower()
        if action == "search_members":
            return response(200, {"matches": chime_attendance_member_search(str(body.get("query") or ""))})
        if action == "add_in_person":
            member_id = str(body.get("member_id") or "").strip()
            if not member_id:
                raise ValueError("Member is required.")
            member = chime_member_summary_by_id(member_id)
            if not member:
                raise ValueError("Member record was not found.")
            attendance_id = f"INPERSON#{meeting_agenda_safe_id(member_id)}"
            item = {
                "item_type": "chime_attendance",
                "attendance_id": attendance_id,
                "meeting_id": meeting_id,
                "attendance_type": "in_person",
                "member_id": member_id,
                "member_name": str(member.get("name") or member.get("email") or member_id),
                "member_email": str(member.get("email") or ""),
                "member_number": member_summary_display_number(member),
                "voting_eligible": chime_member_voting_eligible(member),
                "committee_eligible": chime_member_committee_eligible(member),
                "added_at": utc_now_precise(),
                "added_by_name": chime_member_name(claims),
            }
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": chime_attendance_pk(meeting_id), "sk": attendance_id}))
            return response(200, {"message": "Member added as in-person attendee.", **chime_attendance_payload(active, claims)})
        if action == "remove_in_person":
            member_id = str(body.get("member_id") or "").strip()
            attendance_id = str(body.get("attendance_id") or f"INPERSON#{meeting_agenda_safe_id(member_id)}").strip()
            if not attendance_id:
                raise ValueError("Attendance entry is required.")
            ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=chime_attendance_key(meeting_id, attendance_id))
            return response(200, {"message": "In-person attendee removed.", **chime_attendance_payload(active, claims)})
        if action == "add_guest":
            if not chime_guests_allowed(active):
                raise PermissionError(chime_guest_policy_message(active))
            name = str(body.get("guest_name") or "").strip()[:120]
            notes = str(body.get("notes") or "").strip()[:300]
            if not name:
                raise ValueError("Guest name is required.")
            attendance_id = f"GUEST#{uuid.uuid4().hex}"
            item = {
                "item_type": "chime_attendance",
                "attendance_id": attendance_id,
                "meeting_id": meeting_id,
                "attendance_type": "guest",
                "guest_name": name,
                "notes": notes,
                "voting_eligible": False,
                "committee_eligible": False,
                "added_at": utc_now_precise(),
                "added_by_name": chime_member_name(claims),
            }
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": chime_attendance_pk(meeting_id), "sk": attendance_id}))
            return response(200, {"message": "Guest added.", **chime_attendance_payload(active, claims)})
        if action == "remove_guest":
            attendance_id = str(body.get("attendance_id") or "").strip()
            if not attendance_id:
                raise ValueError("Guest entry is required.")
            ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=chime_attendance_key(meeting_id, attendance_id))
            return response(200, {"message": "Guest removed.", **chime_attendance_payload(active, claims)})
        if action == "confirm_quorum":
            snapshot = chime_store_attendance_snapshot(active, claims, "quorum_confirmed")
            message = "Quorum snapshot stored for minutes." if bool((snapshot.get("quorum") or {}).get("met")) else "Attendance snapshot stored; quorum is not yet met."
            return response(200, {"message": message, **chime_attendance_payload(active, claims)})
        raise ValueError("Unsupported attendance action.")
    return response(200, chime_attendance_payload(active, claims))

def chime_chat_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = chime_active_or_error()
    meeting_id = str(active.get("meeting_id") or "")
    if event.get("requestContext", {}).get("http", {}).get("method") == "POST":
        body = parse_body(event)
        text = str(body.get("message") or body.get("text") or "").strip()
        if not text:
            raise ValueError("Message is required.")
        if len(text) > 2000:
            raise ValueError("Meeting chat messages are limited to 2000 characters.")
        summary = get_current_member_summary(claims)
        created = utc_now_precise()
        item = {
            "item_type": "chime_chat_message",
            "meeting_id": meeting_id,
            "message_id": uuid.uuid4().hex,
            "created_at": created,
            "member_sub": str(claims.get("sub") or ""),
            "member_email": str(summary.get("email") or claims.get("email") or ""),
            "member_name": chime_member_name(claims),
            "message": text,
            "include_in_minutes": bool(body.get("include_in_minutes")),
        }
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": chime_chat_key(meeting_id), "sk": f"MSG#{created}#{item['message_id']}"}))
        return response(200, {"message": "Chat message saved.", "chat_message": item})
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": chime_chat_key(meeting_id)}},
        ScanIndexForward=True,
        Limit=100,
    )
    messages = [item_to_python(x) for x in resp.get("Items") or []]
    return response(200, {"meeting": chime_public_meeting_summary(active), "messages": messages})


def chime_control_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = chime_active_or_error()
    meeting_id = str(active.get("meeting_id") or "")
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "POST":
        require_chime_launcher(claims)
        body = parse_body(event)
        action = str(body.get("action") or "").strip().lower()
        target = str(body.get("target_attendee_id") or "").strip()
        if action not in {"mute"}:
            raise ValueError("Unsupported meeting control action.")
        if not target:
            raise ValueError("Target attendee is required.")
        created = utc_now_precise()
        item = {
            "item_type": "chime_control",
            "meeting_id": meeting_id,
            "control_id": uuid.uuid4().hex,
            "action": action,
            "target_attendee_id": target,
            "created_at": created,
            "created_by_name": chime_member_name(claims),
        }
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**item, "pk": chime_control_key(meeting_id), "sk": f"CONTROL#{created}#{item['control_id']}"}))
        return response(200, {"message": "Meeting control sent.", "control": item})
    params = event.get("queryStringParameters") or {}
    attendee_id = str(params.get("attendee_id") or "").strip()
    if not attendee_id:
        return response(200, {"controls": []})
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": chime_control_key(meeting_id)}},
        ScanIndexForward=False,
        Limit=50,
    )
    seen_after = str(params.get("after") or "")
    controls = []
    for raw in resp.get("Items") or []:
        item = item_to_python(raw)
        if str(item.get("target_attendee_id") or "") != attendee_id:
            continue
        if seen_after and str(item.get("created_at") or "") <= seen_after:
            continue
        controls.append(item)
    controls.sort(key=lambda x: str(x.get("created_at") or ""))
    return response(200, {"controls": controls})



def normalise_chime_agenda_items(raw_items: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not isinstance(raw_items, list):
        return items
    for idx, raw in enumerate(raw_items[:80], start=1):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("heading") or "").strip()[:180]
        detail = str(raw.get("detail") or raw.get("description") or raw.get("notes") or "").strip()[:2000]
        motion_text = str(raw.get("motion_text") or raw.get("motion") or "").strip()[:2000]
        if not title and not detail and not motion_text:
            continue
        item_id = str(raw.get("item_id") or raw.get("id") or uuid.uuid4().hex).strip()[:64] or uuid.uuid4().hex
        try:
            number = int(raw.get("number") or idx)
        except Exception:
            number = idx
        vote_title = str(raw.get("vote_title") or title or f"Agenda item {number}").strip()[:180]
        items.append({
            "item_id": item_id,
            "number": number,
            "title": title or f"Agenda item {number}",
            "detail": detail,
            "motion_text": motion_text,
            "voting_enabled": bool(raw.get("voting_enabled")),
            "vote_title": vote_title,
            "source_agenda_id": str(raw.get("source_agenda_id") or ""),
            "source_meeting_type": str(raw.get("source_meeting_type") or ""),
        })
    items.sort(key=lambda x: (int(x.get("number") or 0), str(x.get("title") or "")))
    # Compact numbers for presentation while keeping stable item ids.
    for idx, item in enumerate(items, start=1):
        item["number"] = idx
    return items


def get_chime_agenda(meeting_id: str) -> Dict[str, Any]:
    resp = ddb.get_item(
        TableName=MEMBER_METADATA_TABLE,
        Key={"pk": {"S": chime_agenda_key(meeting_id)}, "sk": {"S": "AGENDA"}},
        ConsistentRead=True,
    )
    item = item_to_python(resp.get("Item") or {}) if resp.get("Item") else {}
    if not item:
        active = get_active_chime_meeting() or {}
        return chime_agenda_from_current_meeting_agenda(active, meeting_id, preserve_showing=False)
    item["items"] = normalise_chime_agenda_items(item.get("items") or [])
    try:
        item["active_index"] = max(0, min(int(item.get("active_index") or 0), max(0, len(item["items"]) - 1)))
    except Exception:
        item["active_index"] = 0
    return item


def save_chime_agenda(meeting_id: str, agenda: Dict[str, Any]) -> None:
    agenda = dict(agenda)
    agenda["item_type"] = "chime_agenda"
    agenda["meeting_id"] = meeting_id
    agenda["items"] = normalise_chime_agenda_items(agenda.get("items") or [])
    try:
        agenda["active_index"] = max(0, min(int(agenda.get("active_index") or 0), max(0, len(agenda["items"]) - 1)))
    except Exception:
        agenda["active_index"] = 0
    try:
        agenda["progress_index"] = max(0, min(int(agenda.get("progress_index") if agenda.get("progress_index") is not None else agenda.get("active_index") or 0), max(0, len(agenda["items"]) - 1)))
    except Exception:
        agenda["progress_index"] = int(agenda.get("active_index") or 0)
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**agenda, "pk": chime_agenda_key(meeting_id), "sk": "AGENDA"}))


def chime_agenda_public(agenda: Dict[str, Any]) -> Dict[str, Any]:
    items = normalise_chime_agenda_items(agenda.get("items") or [])
    active_index = 0
    try:
        active_index = max(0, min(int(agenda.get("active_index") or 0), max(0, len(items) - 1)))
    except Exception:
        active_index = 0
    active_item = items[active_index] if items else None
    try:
        progress_index = max(0, min(int(agenda.get("progress_index") if agenda.get("progress_index") is not None else active_index), max(0, len(items) - 1)))
    except Exception:
        progress_index = active_index
    return {
        "items": items,
        "active_index": active_index,
        "progress_index": progress_index,
        "active_item": active_item,
        "presentation_enabled": bool(agenda.get("presentation_enabled")) and bool(items),
        "agenda_finished": bool(agenda.get("agenda_finished")),
        "agenda_finished_at": str(agenda.get("agenda_finished_at") or ""),
        "source": str(agenda.get("source") or "scratch"),
        "source_meeting_type": str(agenda.get("source_meeting_type") or ""),
        "updated_at": str(agenda.get("updated_at") or ""),
        "updated_by_name": str(agenda.get("updated_by_name") or ""),
    }


def chime_agenda_from_current_meeting_agenda(active: Dict[str, Any], meeting_id: str, preserve_showing: bool = False, existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    meeting_type = normalise_chime_meeting_type(active.get("meeting_type"))
    items = meeting_agenda_items_for_chime(meeting_type) if meeting_type in MEETING_AGENDA_TYPES else []
    prev = existing or {}
    agenda = {
        "item_type": "chime_agenda",
        "meeting_id": meeting_id,
        "items": normalise_chime_agenda_items(items),
        "active_index": min(int(prev.get("active_index") or 0), max(0, len(items) - 1)) if items else 0,
        "progress_index": min(int(prev.get("progress_index") if prev.get("progress_index") is not None else prev.get("active_index") or 0), max(0, len(items) - 1)) if items else 0,
        "presentation_enabled": bool(prev.get("presentation_enabled")) if preserve_showing else False,
        "source": "meeting-agenda" if items else "scratch",
        "source_meeting_type": meeting_type,
        "updated_at": utc_now_precise(),
        "updated_by_name": "Meeting Agenda",
    }
    return agenda


def chime_agenda_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = chime_active_or_error()
    meeting_id = str(active.get("meeting_id") or "")
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "POST":
        require_chime_launcher(claims)
        body = parse_body(event)
        agenda = get_chime_agenda(meeting_id)
        action = str(body.get("action") or "save").strip().lower()
        if action == "save":
            items = normalise_chime_agenda_items(body.get("items") or [])
            agenda.update({
                "items": items,
                "active_index": max(0, min(int(body.get("active_index") or 0), max(0, len(items) - 1))) if items else 0,
                "progress_index": max(0, min(int(body.get("progress_index") if body.get("progress_index") is not None else body.get("active_index") or 0), max(0, len(items) - 1))) if items else 0,
                "presentation_enabled": bool(body.get("presentation_enabled", agenda.get("presentation_enabled"))),
                "agenda_finished": False,
                "agenda_finished_at": "",
                "source": "scratch",
                "source_meeting_type": normalise_chime_meeting_type(active.get("meeting_type")),
                "updated_at": utc_now_precise(),
                "updated_by_name": chime_member_name(claims),
            })
        elif action == "reload_current_agenda":
            agenda = chime_agenda_from_current_meeting_agenda(active, meeting_id, preserve_showing=True, existing=agenda)
            agenda["updated_by_name"] = chime_member_name(claims)
        elif action in {"next", "previous", "set_active", "resume", "show", "hide", "finish_agenda"}:
            items = normalise_chime_agenda_items(agenda.get("items") or [])
            idx = int(agenda.get("active_index") or 0) if items else 0
            try:
                progress_idx = max(0, min(int(agenda.get("progress_index") if agenda.get("progress_index") is not None else idx), max(0, len(items) - 1))) if items else 0
            except Exception:
                progress_idx = idx
            if action == "next" and items:
                idx = min(idx + 1, len(items) - 1)
                progress_idx = max(progress_idx, idx)
                agenda["agenda_finished"] = False
                agenda["agenda_finished_at"] = ""
            elif action == "previous" and items:
                idx = max(idx - 1, 0)
            elif action == "set_active" and items:
                idx = max(0, min(int(body.get("active_index") or 0), len(items) - 1))
            elif action == "resume" and items:
                idx = progress_idx
            elif action == "finish_agenda":
                if items:
                    idx = len(items) - 1
                    progress_idx = len(items) - 1
                agenda["agenda_finished"] = True
                agenda["agenda_finished_at"] = utc_now_precise()
            agenda["active_index"] = idx
            agenda["progress_index"] = progress_idx
            if action == "show":
                agenda["presentation_enabled"] = True
            elif action == "hide":
                agenda["presentation_enabled"] = False
            agenda["updated_at"] = utc_now_precise()
            agenda["updated_by_name"] = chime_member_name(claims)
        else:
            raise ValueError("Unsupported agenda action.")
        save_chime_agenda(meeting_id, agenda)
        return response(200, {"message": "Meeting agenda updated.", "meeting": chime_public_meeting_summary(active), "can_control": True, "agenda": chime_agenda_public(agenda)})
    agenda = get_chime_agenda(meeting_id)
    return response(200, {"meeting": chime_public_meeting_summary(active), "can_control": can_launch_chime_meeting(claims), "agenda": chime_agenda_public(agenda)})

def meeting_agenda_append_chime_vote_result(vote: Dict[str, Any], counts: Dict[str, int], closed_by_name: str) -> None:
    meeting_type = normalise_meeting_agenda_type(vote.get("source_meeting_type") or vote.get("meeting_type") or "")
    source_agenda_id = str(vote.get("source_agenda_id") or "")
    agenda_item_id = meeting_agenda_safe_id(vote.get("agenda_item_id") or "")
    if not meeting_type or not source_agenda_id or not agenda_item_id:
        return
    key = {"pk": {"S": meeting_agenda_item_pk(meeting_type, source_agenda_id)}, "sk": {"S": f"ITEM#{agenda_item_id}"}}
    try:
        resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key=key, ConsistentRead=True)
        item = item_to_python(resp.get("Item") or {}) if resp.get("Item") else {}
        if not item:
            return
        result_text = "; ".join([f"{opt}: {counts.get(str(opt), 0)}" for opt in (vote.get("options") or counts.keys())])
        line = f"Secret ballot closed {utc_now_precise()} by {closed_by_name}. Result: {result_text}. Total votes: {sum(counts.values())}."
        existing = str(item.get("minute_text") or "").strip()
        item["minute_text"] = (existing + "\n" if existing else "") + line
        result_payload = {"closed_at": utc_now_precise(), "closed_by_name": closed_by_name, "results": counts, "total_votes": sum(counts.values())}
        item["last_vote_result"] = result_payload
        item["updated_at"] = utc_now_precise()
        ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item(item))
        meeting_agenda_put_source_history(meeting_type, source_agenda_id, {
            "item_type": "chime_vote_result",
            "sk": f"VOTE#{result_payload['closed_at']}#{vote.get('vote_id') or uuid.uuid4().hex}",
            "vote": vote,
            "results": counts,
            "total_votes": sum(counts.values()),
            "closed_at": result_payload["closed_at"],
            "closed_by_name": closed_by_name,
            "agenda_item_id": agenda_item_id,
            "agenda_item_title": str(vote.get("agenda_item_title") or item.get("title") or ""),
        })
    except Exception as exc:
        print(f"Could not write Chime vote result back to meeting agenda: {exc}")


def chime_vote_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = chime_active_or_error()
    if not chime_meeting_is_formal(active):
        return response(200, {"meeting": chime_public_meeting_summary(active), "can_control": can_launch_chime_meeting(claims), "vote": None, "already_voted": False, "voting_enabled": False, "message": "Formal voting is only available for Committee, General, and AGM meeting modes."})
    meeting_id = str(active.get("meeting_id") or "")
    method = event.get("requestContext", {}).get("http", {}).get("method")
    pk = chime_vote_key(meeting_id)
    sub = str(claims.get("sub") or claims.get("cognito:username") or "")
    if method == "POST":
        body = parse_body(event)
        action = str(body.get("action") or "").strip().lower()
        if action == "start":
            require_chime_launcher(claims)
            agenda_item_id = str(body.get("agenda_item_id") or "").strip()
            agenda_item = None
            if agenda_item_id:
                agenda = get_chime_agenda(meeting_id)
                for candidate in agenda.get("items") or []:
                    if str(candidate.get("item_id") or "") == agenda_item_id:
                        agenda_item = candidate
                        break
                if not agenda_item:
                    raise ValueError("Agenda item was not found.")
                if not bool(agenda_item.get("voting_enabled")):
                    raise ValueError("Voting is not enabled for this agenda item.")
            title = str(body.get("title") or (agenda_item or {}).get("vote_title") or (agenda_item or {}).get("title") or "").strip()[:180]
            if not title:
                raise ValueError("Vote title/motion is required.")
            quorum = chime_build_quorum(active, list_chime_attendees(meeting_id), list_chime_manual_attendance(meeting_id))
            if not bool(quorum.get("met")):
                raise ValueError("Quorum is not currently met. Add online or in-person attendance before opening a formal ballot.")
            if not bool(body.get("quorum_confirmed")):
                raise ValueError("Confirm quorum before opening a formal ballot.")
            options = body.get("options") if isinstance(body.get("options"), list) else ["For", "Against", "Abstain"]
            options = [str(x).strip()[:80] for x in options if str(x).strip()][:6] or ["For", "Against", "Abstain"]
            vote = {
                "item_type": "chime_vote",
                "meeting_id": meeting_id,
                "vote_id": uuid.uuid4().hex,
                "status": "open",
                "secret_ballot": True,
                "meeting_type": normalise_chime_meeting_type(active.get("meeting_type")),
                "agenda_item_id": str((agenda_item or {}).get("item_id") or ""),
                "agenda_item_number": int((agenda_item or {}).get("number") or 0),
                "agenda_item_title": str((agenda_item or {}).get("title") or ""),
                "source_agenda_id": str((agenda_item or {}).get("source_agenda_id") or ""),
                "source_meeting_type": str((agenda_item or {}).get("source_meeting_type") or normalise_chime_meeting_type(active.get("meeting_type"))),
                "quorum_confirmed": True,
                "quorum_confirmed_by_name": chime_member_name(claims),
                "quorum_snapshot": {k: v for k, v in quorum.items() if k not in {"eligible_member_ids", "committee_member_ids"}},
                "title": title,
                "description": str(body.get("description") or (agenda_item or {}).get("motion_text") or (agenda_item or {}).get("detail") or "").strip()[:1000],
                "options": options,
                "created_at": utc_now_precise(),
                "created_by_name": chime_member_name(claims),
            }
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**vote, "pk": pk, "sk": "ACTIVE"}))
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**vote, "pk": pk, "sk": f"VOTE#{vote['vote_id']}"}))
            return response(200, {"message": "Secret ballot opened.", "vote": vote})
        if action == "cast":
            summary_for_vote = get_current_member_summary(claims)
            if not chime_member_voting_eligible(summary_for_vote):
                raise PermissionError("Only current financial or life members may vote in formal ballots.")
            if not chime_current_member_is_present(meeting_id, claims):
                raise PermissionError("You must be recorded as present online or in person before voting.")
            active_vote_resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": pk}, "sk": {"S": "ACTIVE"}}, ConsistentRead=True)
            vote = item_to_python(active_vote_resp.get("Item") or {}) if active_vote_resp.get("Item") else {}
            if not vote or str(vote.get("status") or "") != "open":
                raise ValueError("There is no open vote.")
            choice = str(body.get("choice") or "").strip()[:80]
            if choice not in list(vote.get("options") or []):
                raise ValueError("Invalid vote option.")
            summary = get_current_member_summary(claims)
            ballot = {
                "item_type": "chime_vote_ballot",
                "meeting_id": meeting_id,
                "vote_id": str(vote.get("vote_id") or ""),
                "member_sub_hash": hashlib.sha256(sub.encode("utf-8")).hexdigest(),
                "member_sub": sub,
                "member_email": str(summary.get("email") or claims.get("email") or ""),
                "member_name": chime_member_name(claims),
                "secret_ballot": True,
                "choice": choice,
                "cast_at": utc_now_precise(),
            }
            # Secret ballot: controllers and minutes receive totals only; identity is retained server-side to prevent multi-device duplicate voting and for audit integrity.
            ballot_key = f"BALLOT#{vote.get('vote_id')}#{ballot['member_sub_hash']}"
            existing_ballot = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": pk}, "sk": {"S": ballot_key}}, ConsistentRead=True)
            if existing_ballot.get("Item"):
                return response(200, {"message": "Your secret ballot has already been recorded.", "already_voted": True})
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**ballot, "pk": pk, "sk": ballot_key}), ConditionExpression="attribute_not_exists(pk)")
            return response(200, {"message": "Your secret ballot has been recorded.", "already_voted": True})
        if action == "close":
            require_chime_launcher(claims)
            active_vote_resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": pk}, "sk": {"S": "ACTIVE"}}, ConsistentRead=True)
            vote = item_to_python(active_vote_resp.get("Item") or {}) if active_vote_resp.get("Item") else {}
            if not vote:
                raise ValueError("There is no open vote to close.")
            vote_id = str(vote.get("vote_id") or "")
            resp = ddb.query(
                TableName=MEMBER_METADATA_TABLE,
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                ExpressionAttributeValues={":pk": {"S": pk}, ":prefix": {"S": f"BALLOT#{vote_id}#"}},
                Limit=500,
            )
            counts = {str(opt): 0 for opt in vote.get("options") or []}
            for raw in resp.get("Items") or []:
                b = item_to_python(raw)
                choice = str(b.get("choice") or "")
                counts[choice] = counts.get(choice, 0) + 1
            closed = {**vote, "status": "closed", "closed_at": utc_now_precise(), "closed_by_name": chime_member_name(claims), "results": counts, "total_votes": sum(counts.values())}
            ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": pk}, "sk": {"S": "ACTIVE"}})
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**closed, "pk": pk, "sk": f"VOTE#{vote_id}"}))
            ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({"pk": chime_history_key(meeting_id), "sk": f"VOTE#{closed['closed_at']}#{vote_id}", **closed, "item_type": "chime_vote_result"}))
            meeting_agenda_append_chime_vote_result(closed, counts, chime_member_name(claims))
            return response(200, {"message": "Secret ballot closed and stored in meeting history and agenda minutes.", "vote": closed})
    active_vote_resp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": pk}, "sk": {"S": "ACTIVE"}}, ConsistentRead=True)
    vote = item_to_python(active_vote_resp.get("Item") or {}) if active_vote_resp.get("Item") else None
    already_voted = False
    if vote and sub:
        vote_id = str(vote.get("vote_id") or "")
        member_hash = hashlib.sha256(sub.encode("utf-8")).hexdigest()
        bresp = ddb.get_item(TableName=MEMBER_METADATA_TABLE, Key={"pk": {"S": pk}, "sk": {"S": f"BALLOT#{vote_id}#{member_hash}"}}, ConsistentRead=True)
        already_voted = bool(bresp.get("Item"))
    return response(200, {"meeting": chime_public_meeting_summary(active), "can_control": can_launch_chime_meeting(claims), "vote": vote, "already_voted": already_voted, "voting_enabled": True, "member_is_financial": chime_member_voting_eligible(get_current_member_summary(claims)), "member_is_present": chime_current_member_is_present(meeting_id, claims), "attendance": chime_attendance_payload(active, claims), "agenda": chime_agenda_public(get_chime_agenda(meeting_id))})


def chime_history_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    active = chime_active_or_error()
    require_chime_launcher(claims)
    meeting_id = str(active.get("meeting_id") or "")
    chat = chime_chat_route({"requestContext": {"http": {"method": "GET"}}}, claims)
    attendees = list_chime_attendees(meeting_id)
    resp = ddb.query(
        TableName=MEMBER_METADATA_TABLE,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": chime_history_key(meeting_id)}},
        Limit=200,
    )
    history = [item_to_python(x) for x in resp.get("Items") or []]
    flagged_chat = []
    try:
        chat_body = json.loads(chat.get("body") or "{}") if isinstance(chat, dict) else {}
        flagged_chat = [m for m in chat_body.get("messages") or [] if bool(m.get("include_in_minutes"))]
    except Exception:
        flagged_chat = []
    return response(200, {"meeting": chime_public_meeting_summary(active), "attendance": attendees, "history": history, "chat_stored": True, "flagged_chat_for_minutes": flagged_chat})

def end_chime_meeting_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_chime_meetings()
    require_chime_launcher(claims)
    active = get_active_chime_meeting()
    if not active:
        return response(200, {"message": "No LROC meeting is currently active.", "meeting": {"active": False}, "can_launch": True, "can_end": True})
    chime_meeting_id = str(active.get("chime_meeting_id") or "")
    if chime_meeting_id:
        try:
            chime.delete_meeting(MeetingId=chime_meeting_id)
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code") or "")
            if code not in {"NotFoundException", "ResourceNotFoundException"}:
                raise
    ended = dict(active)
    ended["status"] = "ended"
    ended["ended_at"] = utc_now_precise()
    ended["ended_by_sub"] = str(claims.get("sub") or "")
    ended["ended_by_email"] = str(claims.get("email") or "")
    try:
        chime_store_attendance_snapshot(active, claims, "meeting_ended")
    except Exception as exc:
        print(f"Could not store final Chime attendance snapshot: {exc}")
    ddb.delete_item(TableName=MEMBER_METADATA_TABLE, Key=chime_active_key())
    ddb.put_item(TableName=MEMBER_METADATA_TABLE, Item=python_to_item({**ended, "pk": CHIME_MEETING_PK, "sk": f"MEETING#{ended.get('meeting_id') or ''}"}))
    return response(200, {"message": "LROC meeting ended.", "meeting": {"active": False}, "can_launch": True, "can_end": True})

# ---------------------------------------------------------------------------
# Role-based SES/S3 webmail
# ---------------------------------------------------------------------------
WEBMAIL_FOLDERS = {"inbox", "sent", "archive", "quarantine"}
WEBMAIL_SPAM_FAIL_STATUSES = {"fail", "gray", "grey"}
WEBMAIL_SAFE_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".rtf", ".odt"}
WEBMAIL_SAFE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
WEBMAIL_ARTICLE_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".rtf", ".odt"}
WEBMAIL_TRIPREPORT_EXTENSIONS = WEBMAIL_ARTICLE_EXTENSIONS | WEBMAIL_SAFE_IMAGE_EXTENSIONS
WEBMAIL_PRESENTATION_EXTENSIONS = {".pptx", ".pdf"}
WEBMAIL_MAGAZINECONTENT_EXTENSIONS = WEBMAIL_SAFE_DOCUMENT_EXTENSIONS | WEBMAIL_SAFE_IMAGE_EXTENSIONS
WEBMAIL_VENDORCONTENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".rtf", ".odt"} | WEBMAIL_SAFE_IMAGE_EXTENSIONS
WEBMAIL_MAGAZINE_EXTENSIONS = {".pdf", ".zip"}
WEBMAIL_MACRO_OFFICE_EXTENSIONS = {".docm", ".dotm", ".pptm", ".potm", ".ppam", ".xlsm", ".xltm", ".xlam"}
WEBMAIL_BLOCKED_ATTACHMENT_EXTENSIONS = {
    ".exe", ".dll", ".scr", ".com", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jse", ".wsf",
    ".msi", ".msp", ".jar", ".hta", ".reg", ".sh", ".app", ".dmg", ".iso",
} | WEBMAIL_MACRO_OFFICE_EXTENSIONS
WEBMAIL_EXT_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".rtf": "application/rtf",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".zip": "application/zip",
}
WEBMAIL_SCAN_CLEAN_STATUSES = {"clean", "ses_clean", "guardduty_clean", "scan_not_required", "internal_clean"}
WEBMAIL_SCAN_BLOCK_STATUSES = {"infected", "blocked_type", "quarantined", "scan_failed", "unsupported", "unsupported_type", "scan_unknown"}


def webmail_enabled() -> bool:
    return bool(WEBMAIL_ENABLED and WEBMAIL_MAIL_BUCKET and EMAIL_STATE_TABLE)


def webmail_unmatched_mailbox_address() -> str:
    configured = normalise_email_address(WEBMAIL_UNMATCHED_MAILBOX_ADDRESS or "")
    if configured:
        return configured
    return f"unmatched@{club_email_domain()}"


def webmail_unmatched_position_ids() -> set[str]:
    return {normalise_position_id(x) for x in WEBMAIL_UNMATCHED_POSITION_IDS_RAW.split(",") if str(x).strip()}


# LROC member-files backend build: 3.1.9 internal-webmail-scan-fix
def require_webmail() -> None:
    if not webmail_enabled():
        raise RuntimeError("Role webmail is not configured.")


def webmail_pk(mailbox: str) -> str:
    return f"WEBMAIL#{normalise_email_address(mailbox)}"


def webmail_message_sk(message_id: str) -> str:
    return f"MSG#{clean_webmail_message_id(message_id)}"


def clean_webmail_message_id(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.:@+-]+", "-", str(value or "").strip()).strip("-._")
    if not text:
        text = f"msg-{uuid.uuid4().hex}"
    return text[:180]


def safe_header(value: Any, max_len: int = 250) -> str:
    text = re.sub(r"[\r\n]+", " ", str(value or "").strip())
    return re.sub(r"\s+", " ", text)[:max_len]


def webmail_parse_address_list(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_values = [str(x or "") for x in value]
    else:
        raw_values = [str(value or "")]
    emails: List[str] = []
    seen: set[str] = set()
    for _name, addr in getaddresses(raw_values):
        email = normalise_email_address(addr or "")
        if valid_email_address(email) and email not in seen:
            emails.append(email)
            seen.add(email)
    return emails


def webmail_inbound_domain() -> str:
    configured = str(WEBMAIL_INBOUND_DOMAIN or "").strip().lower()
    return configured or club_email_domain()


def webmail_service_position_ids() -> set[str]:
    return {"articles", "clubarticles", "tripreports", "presentations", "magazinecontent", "vendorcontent", "magazines"}


def webmail_service_mailboxes() -> Dict[str, Dict[str, Any]]:
    domain = webmail_inbound_domain()
    services = [
        ("articles", "Articles"),
        ("clubarticles", "Club Articles"),
        ("tripreports", "Trip Reports"),
        ("presentations", "Presentations"),
        ("magazinecontent", "Magazine Content"),
        ("vendorcontent", "Vendor Content"),
        ("magazines", "Magazines"),
    ]
    out: Dict[str, Dict[str, Any]] = {}
    for local, label in services:
        email = normalise_email_address(f"{local}@{domain}")
        if valid_email_address(email):
            out[email] = {"position_id": local, "position_name": label, "email_address": email, "active": True, "mailbox": email}
    return out


def webmail_position_map() -> Dict[str, Dict[str, Any]]:
    positions = [p for p in list_club_positions(include_defaults=True) if bool(p.get("active", True))]
    out: Dict[str, Dict[str, Any]] = {}
    for position in positions:
        email = normalise_email_address(position.get("email_address") or "")
        if valid_email_address(email):
            out[email] = dict(position, mailbox=email)
    for email, service in webmail_service_mailboxes().items():
        out.setdefault(email, service)
    return out


def webmail_access_tokens_for_claims(claims: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    sub = str(claims.get("sub") or "").strip()
    if sub:
        try:
            meta = get_member_metadata(sub)
            tokens.add(normalise_position_id(meta.get("committee_position_id") or ""))
            tokens.add(normalise_position_id(meta.get("official_position_id") or ""))
            tokens.add(normalise_position_id(meta.get("committee_position_name") or ""))
            tokens.add(normalise_position_id(meta.get("official_position_name") or ""))
            for role in meta.get("assigned_role_ids") or []:
                tokens.add(normalise_position_id(role))
            for role in meta.get("assigned_role_names") or []:
                tokens.add(normalise_position_id(role))
            for role in meta.get("club_roles") or []:
                tokens.add(normalise_position_id(role))
            for role in re.split(r"[,;|\n]", str(meta.get("club_roles_raw") or "")):
                tokens.add(normalise_position_id(role))
        except Exception:
            pass
    groups = get_groups(claims)
    for group in groups:
        tokens.add(normalise_position_id(group))
    return {x for x in tokens if x}


def webmail_accessible_mailboxes(claims: Dict[str, Any]) -> List[Dict[str, Any]]:
    # A logged-in role holder may use their own assigned role mailbox plus
    # shared service accounts such as Articles, Club Articles, Trip Reports and
    # Magazines. Do not expose other role holders' mailboxes just because the
    # user is also an admin; that would allow accidental role spoofing from Webmail.
    position_by_email = webmail_position_map()
    tokens = webmail_access_tokens_for_claims(claims)
    service_ids = webmail_service_position_ids()
    can_use_webmail = bool(tokens) or is_admin(claims)
    mailboxes: List[Dict[str, Any]] = []
    for email, position in position_by_email.items():
        pid = normalise_position_id(position.get("position_id") or position.get("position_name") or "")
        pname_token = normalise_position_id(position.get("position_name") or "")
        owned = pid in tokens or pname_token in tokens
        service_account = pid in service_ids or normalise_email_address(email) in webmail_service_mailboxes()
        allowed = owned or (service_account and can_use_webmail)
        if not allowed:
            continue
        role_name = str(position.get("position_name") or email).strip()
        mailboxes.append({
            "mailbox": email,
            "address": email,
            "position_id": pid,
            "role_name": role_name,
            "label": role_name,
            "signature": webmail_role_signature(role_name),
            "unmatched": False,
            "service_account": service_account,
            "service": service_account,
            "owned": owned,
            "preferred": owned and not service_account,
            "send_allowed": owned or service_account,
        })
    unmatched_allowed = bool(tokens.intersection(webmail_unmatched_position_ids())) or "webmaster" in tokens or is_admin(claims)
    if unmatched_allowed:
        addr = webmail_unmatched_mailbox_address()
        mailboxes.append({
            "mailbox": addr,
            "address": addr,
            "position_id": "unmatched-inbound",
            "role_name": "Unmatched inbound mail",
            "label": "Unmatched inbound mail",
            "signature": webmail_role_signature("Webmaster" if "webmaster" in tokens else "President"),
            "unmatched": True,
            "service_account": True,
            "service": True,
            "owned": False,
            "preferred": False,
            "send_allowed": False,
        })
    mailboxes.sort(key=lambda item: (
        0 if item.get("preferred") else 1,
        0 if item.get("owned") else 1,
        1 if item.get("service_account") else 0,
        1 if item.get("unmatched") else 0,
        str(item.get("label") or "").lower(),
    ))
    return mailboxes


def webmail_get_mailbox_for_claims(claims: Dict[str, Any], mailbox: str, *, for_send: bool = False) -> Dict[str, Any]:
    mailbox = normalise_email_address(mailbox or "")
    for item in webmail_accessible_mailboxes(claims):
        if normalise_email_address(item.get("mailbox") or "") == mailbox:
            if for_send and not bool(item.get("send_allowed")):
                raise PermissionError("This mailbox is read-only and cannot be used as a sending identity.")
            return item
    raise PermissionError("You do not have access to that mailbox.")


def webmail_role_signature(role_name: str) -> str:
    role = safe_header(role_name or "LROC", 120)
    return f"Regards,\n{role}\nLand Rover Owners Club of Australia Inc"


def webmail_member_contact_email(claims: Dict[str, Any]) -> str:
    # Important: use the member contact email stored in metadata, not the Cognito/login email.
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        return ""
    try:
        meta = get_member_metadata(sub)
        email = normalise_email_address(meta.get("email") or "")
        return email if valid_email_address(email) else ""
    except Exception:
        return ""


def webmail_attachment_safe_name(name: Any, fallback: str = "attachment") -> str:
    text = str(name or fallback).strip().replace("\\", "_").replace("/", "_")
    text = re.sub(r"[^A-Za-z0-9_.() -]+", "_", text)
    return (text or fallback)[:160]


def webmail_attachment_key(message_id: str, index: int, filename: str) -> str:
    return f"{WEBMAIL_ATTACHMENT_PREFIX}{clean_webmail_message_id(message_id)}/{index:02d}-{webmail_attachment_safe_name(filename)}"


def webmail_submission_key(kind: str, message_id: str, index: int, filename: str) -> str:
    safe_kind = re.sub(r"[^a-z0-9-]+", "-", str(kind or "submission").strip().lower()).strip("-") or "submission"
    return f"{WEBMAIL_SUBMISSION_PREFIX}{safe_kind}/{clean_webmail_message_id(message_id)}/{index:02d}-{webmail_attachment_safe_name(filename)}"


def webmail_attachment_ext(filename: Any) -> str:
    return os.path.splitext(str(filename or "").strip().lower())[1]


def webmail_attachment_content_type(filename: Any, content_type: Any = "") -> str:
    ctype = str(content_type or "").strip().lower()
    if ctype and ctype not in {"application/octet-stream", "binary/octet-stream"}:
        return ctype
    ext = webmail_attachment_ext(filename)
    return WEBMAIL_EXT_CONTENT_TYPES.get(ext) or mimetypes.guess_type(str(filename or ""))[0] or "application/octet-stream"


def webmail_attachment_kind_for_filename(filename: Any, content_type: Any = "") -> str:
    ext = webmail_attachment_ext(filename)
    ctype = webmail_attachment_content_type(filename, content_type)
    if ext == ".pdf" or ctype in {"application/pdf", "application/x-pdf"}:
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext == ".pptx":
        return "pptx"
    if ext in {".txt", ".md", ".rtf", ".odt"}:
        return ext.lstrip(".")
    if ext in WEBMAIL_SAFE_IMAGE_EXTENSIONS:
        return "image"
    if ext == ".zip":
        return "zip"
    return ext.lstrip(".") or "file"


def webmail_attachment_type_policy(filename: Any, content_type: Any = "", *, target: str = "") -> Dict[str, Any]:
    filename = webmail_attachment_safe_name(filename or "attachment")
    ext = webmail_attachment_ext(filename)
    if ext in WEBMAIL_BLOCKED_ATTACHMENT_EXTENSIONS:
        return {"allowed": False, "status": "blocked_type", "reason": "macro_or_executable_attachment", "extension": ext, "kind": webmail_attachment_kind_for_filename(filename, content_type)}
    target = str(target or "").strip().lower()
    allowed = WEBMAIL_SAFE_DOCUMENT_EXTENSIONS | WEBMAIL_SAFE_IMAGE_EXTENSIONS
    if target == "articles":
        allowed = WEBMAIL_ARTICLE_EXTENSIONS
    elif target == "tripreports":
        allowed = WEBMAIL_TRIPREPORT_EXTENSIONS
    elif target == "presentations":
        allowed = WEBMAIL_PRESENTATION_EXTENSIONS
    elif target == "magazinecontent":
        allowed = WEBMAIL_MAGAZINECONTENT_EXTENSIONS
    elif target == "vendorcontent":
        allowed = WEBMAIL_VENDORCONTENT_EXTENSIONS
    elif target == "magazines":
        allowed = WEBMAIL_MAGAZINE_EXTENSIONS
    if ext and ext not in allowed:
        return {"allowed": False, "status": "unsupported_type", "reason": f"unsupported_{target or 'webmail'}_attachment_type", "extension": ext, "kind": webmail_attachment_kind_for_filename(filename, content_type)}
    if not ext:
        return {"allowed": False, "status": "unsupported_type", "reason": "missing_extension", "extension": "", "kind": "file"}
    return {"allowed": True, "status": "type_allowed", "reason": "ok", "extension": ext, "kind": webmail_attachment_kind_for_filename(filename, content_type)}


def webmail_guardduty_scan_tag_for_key(key: str) -> str:
    if not key:
        return ""
    try:
        resp = s3.get_object_tagging(Bucket=WEBMAIL_MAIL_BUCKET, Key=key)
    except Exception:
        return ""
    for tag in resp.get("TagSet") or []:
        if str(tag.get("Key") or "") == WEBMAIL_MALWARE_SCAN_TAG_KEY:
            return str(tag.get("Value") or "").strip().upper()
    return ""


def webmail_attachment_scan_status(att: Dict[str, Any], spam: Dict[str, Any] | None = None, *, refresh: bool = False) -> Dict[str, Any]:
    att = att if isinstance(att, dict) else {}
    if bool(att.get("skipped")):
        return {"status": "skipped", "provider": "webmail", "download_allowed": False, "import_allowed": False, "reason": str(att.get("reason") or "skipped")}
    filename = att.get("filename") or "attachment"
    policy = webmail_attachment_type_policy(filename, att.get("content_type"))
    if not policy.get("allowed"):
        return {"status": str(policy.get("status") or "blocked_type"), "provider": "type_policy", "download_allowed": False, "import_allowed": False, "reason": str(policy.get("reason") or "blocked_type"), **policy}
    if bool(att.get("internal_trusted")) or str(att.get("scan_provider") or "").strip().lower() == "internal_webmail":
        return {"status": "internal_clean", "provider": "internal_webmail", "download_allowed": True, "import_allowed": True, "reason": "internal_webmail_delivery"}
    spam = spam or {}
    verdicts = spam.get("verdicts") if isinstance(spam.get("verdicts"), dict) else {}
    virus = str(verdicts.get("virus") or att.get("ses_virus_verdict") or "").strip().lower()
    if virus in WEBMAIL_SPAM_FAIL_STATUSES or str(spam.get("status") or "").strip().lower() == "quarantine":
        return {"status": "quarantined", "provider": "ses", "download_allowed": False, "import_allowed": False, "reason": "ses_spam_or_virus_verdict"}
    key = str(att.get("key") or "")
    tag = webmail_guardduty_scan_tag_for_key(key) if (refresh or WEBMAIL_REQUIRE_ATTACHMENT_SCAN) else str(att.get("guardduty_scan_status") or "").strip().upper()
    if tag:
        if tag in WEBMAIL_MALWARE_SCAN_CLEAN_VALUES:
            return {"status": "guardduty_clean", "provider": "guardduty_s3", "download_allowed": True, "import_allowed": True, "reason": "clean", "guardduty_scan_status": tag}
        if tag in WEBMAIL_MALWARE_SCAN_BLOCK_VALUES or "THREAT" in tag or "FAIL" in tag:
            return {"status": "infected" if "THREAT" in tag else "scan_failed", "provider": "guardduty_s3", "download_allowed": False, "import_allowed": False, "reason": tag.lower(), "guardduty_scan_status": tag}
        if WEBMAIL_REQUIRE_ATTACHMENT_SCAN:
            return {"status": "pending_scan", "provider": "guardduty_s3", "download_allowed": False, "import_allowed": False, "reason": tag.lower(), "guardduty_scan_status": tag}
    if WEBMAIL_REQUIRE_ATTACHMENT_SCAN:
        return {"status": "pending_scan", "provider": "guardduty_s3", "download_allowed": False, "import_allowed": False, "reason": "guardduty_tag_not_available_yet"}
    if WEBMAIL_TRUST_SES_VIRUS_SCAN and virus in {"pass", "gray", "grey", ""}:
        return {"status": "ses_clean", "provider": "ses", "download_allowed": True, "import_allowed": True, "reason": "ses_virus_verdict_pass_or_unavailable"}
    return {"status": "scan_not_required", "provider": "type_policy", "download_allowed": True, "import_allowed": True, "reason": "scan_not_required"}


def webmail_update_attachment_statuses(attachments: List[Dict[str, Any]], spam: Dict[str, Any] | None = None, *, refresh: bool = False) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in attachments or []:
        if not isinstance(raw, dict):
            continue
        att = dict(raw)
        scan = webmail_attachment_scan_status(att, spam, refresh=refresh)
        att["scan_status"] = str(scan.get("status") or "")
        att["scan_provider"] = str(scan.get("provider") or "")
        att["scan_reason"] = str(scan.get("reason") or "")
        att["download_allowed"] = bool(scan.get("download_allowed"))
        att["import_allowed"] = bool(scan.get("import_allowed"))
        if scan.get("guardduty_scan_status"):
            att["guardduty_scan_status"] = str(scan.get("guardduty_scan_status") or "")
        att["kind"] = webmail_attachment_kind_for_filename(att.get("filename"), att.get("content_type"))
        att["extension"] = webmail_attachment_ext(att.get("filename"))
        out.append(att)
    return out


def webmail_message_spam_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": str(item.get("spam_status") or "clean"), "verdicts": item.get("spam_verdicts") if isinstance(item.get("spam_verdicts"), dict) else {}}


def webmail_compose_upload_key(sub: str, filename: str) -> str:
    owner = re.sub(r"[^A-Za-z0-9_.=-]+", "-", str(sub or "member"))[:80] or "member"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{WEBMAIL_ATTACHMENT_PREFIX}compose/{owner}/{stamp}-{secrets.token_hex(8)}-{webmail_attachment_safe_name(filename)}"


def webmail_is_compose_upload_key(key: str, sub: str) -> bool:
    owner = re.sub(r"[^A-Za-z0-9_.=-]+", "-", str(sub or "member"))[:80] or "member"
    return str(key or "").startswith(f"{WEBMAIL_ATTACHMENT_PREFIX}compose/{owner}/")


def webmail_sent_key(message_id: str) -> str:
    return f"{WEBMAIL_SENT_PREFIX}{clean_webmail_message_id(message_id)}.eml"


def webmail_body_from_message(msg) -> tuple[str, str]:
    text_body = ""
    html_body = ""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part:
            content = part.get_content()
            if part.get_content_type() == "text/html":
                html_body = str(content or "")
                text_body = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.I)
                text_body = re.sub(r"<[^>]+>", " ", text_body)
                text_body = html.unescape(re.sub(r"\s+", " ", text_body)).strip()
            else:
                text_body = str(content or "")
        if not text_body:
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    text_body = str(part.get_content() or "")
                    break
    except Exception:
        text_body = ""
    return text_body[:120000], html_body[:200000]


def webmail_extract_attachments(msg, message_id: str) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []
    total = 0
    index = 0
    for part in msg.iter_attachments():
        filename = webmail_attachment_safe_name(part.get_filename() or f"attachment-{index + 1}")
        ctype = str(part.get_content_type() or "application/octet-stream")
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            payload = None
        if payload is None:
            content = part.get_content()
            payload = content.encode("utf-8") if isinstance(content, str) else bytes(content or b"")
        if not payload:
            continue
        size = len(payload)
        if size > WEBMAIL_MAX_ATTACHMENT_BYTES or total + size > WEBMAIL_MAX_TOTAL_ATTACHMENT_BYTES:
            attachments.append({"filename": filename, "content_type": ctype, "size": size, "skipped": True, "reason": "size_limit"})
            continue
        key = webmail_attachment_key(message_id, index, filename)
        s3.put_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=key, Body=payload, ContentType=ctype, ServerSideEncryption="AES256")
        attachments.append({"index": index, "filename": filename, "content_type": ctype, "size": size, "key": key})
        total += size
        index += 1
    return attachments


def webmail_spam_status_from_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    def status(name: str) -> str:
        value = receipt.get(name) or {}
        return str(value.get("status") or "").strip().lower()
    verdicts = {
        "spam": status("spamVerdict"),
        "virus": status("virusVerdict"),
        "spf": status("spfVerdict"),
        "dkim": status("dkimVerdict"),
        "dmarc": status("dmarcVerdict"),
    }
    quarantine = verdicts.get("virus") in WEBMAIL_SPAM_FAIL_STATUSES or verdicts.get("spam") in WEBMAIL_SPAM_FAIL_STATUSES
    return {"verdicts": verdicts, "quarantine": quarantine, "status": "quarantine" if quarantine else "clean"}


def webmail_index_message(item: Dict[str, Any]) -> Dict[str, Any]:
    require_email_state_table()
    mailbox = normalise_email_address(item.get("mailbox") or "")
    if not mailbox:
        raise ValueError("mailbox is required.")
    message_id = clean_webmail_message_id(item.get("message_id") or "")
    item["pk"] = webmail_pk(mailbox)
    item["sk"] = webmail_message_sk(message_id)
    item["item_type"] = "webmail_message"
    item["mailbox"] = mailbox
    item["message_id"] = message_id
    item["updated_at"] = utc_now_precise()
    ddb.put_item(TableName=EMAIL_STATE_TABLE, Item=python_to_item(item))
    mirror = {
        "pk": f"WEBMAIL#MSG#{message_id}",
        "sk": f"MAILBOX#{mailbox}",
        "mailbox": mailbox,
        "message_id": message_id,
        "folder": item.get("folder") or "inbox",
        "created_at": item.get("received_at") or item.get("sent_at") or item.get("created_at") or utc_now_precise(),
    }
    ddb.put_item(TableName=EMAIL_STATE_TABLE, Item=python_to_item(mirror))
    return item


def webmail_attachment_scan_summary(attachments: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len([a for a in attachments or [] if isinstance(a, dict) and not bool(a.get("skipped"))])
    statuses: Dict[str, int] = {}
    blocked = 0
    pending = 0
    clean = 0
    for att in attachments or []:
        if not isinstance(att, dict) or bool(att.get("skipped")):
            continue
        status = str(att.get("scan_status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        if status in WEBMAIL_SCAN_CLEAN_STATUSES:
            clean += 1
        elif status in WEBMAIL_SCAN_BLOCK_STATUSES:
            blocked += 1
        else:
            pending += 1
    return {"total": total, "clean": clean, "blocked": blocked, "pending": pending, "statuses": statuses}


def webmail_message_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    body = str(item.get("body_text") or "")
    return {
        "message_id": str(item.get("message_id") or ""),
        "mailbox": normalise_email_address(item.get("mailbox") or ""),
        "folder": str(item.get("folder") or "inbox"),
        "from": str(item.get("from") or ""),
        "to": item.get("to") if isinstance(item.get("to"), list) else [],
        "cc": item.get("cc") if isinstance(item.get("cc"), list) else [],
        "subject": str(item.get("subject") or "(no subject)"),
        "received_at": str(item.get("received_at") or item.get("sent_at") or item.get("created_at") or ""),
        "sent_at": str(item.get("sent_at") or ""),
        "preview": body[:220],
        "has_attachments": bool(item.get("attachments")),
        "attachment_count": len(item.get("attachments") if isinstance(item.get("attachments"), list) else []),
        "read": bool(item.get("read")),
        "spam_status": str(item.get("spam_status") or "clean"),
        "attachment_scan_summary": webmail_attachment_scan_summary(item.get("attachments") if isinstance(item.get("attachments"), list) else []),
        "article_import": item.get("article_import") if isinstance(item.get("article_import"), dict) else {},
        "tripreport_import": item.get("tripreport_import") if isinstance(item.get("tripreport_import"), dict) else {},
        "presentation_import": item.get("presentation_import") if isinstance(item.get("presentation_import"), dict) else {},
        "magazinecontent_import": item.get("magazinecontent_import") if isinstance(item.get("magazinecontent_import"), dict) else {},
        "vendorcontent_import": item.get("vendorcontent_import") if isinstance(item.get("vendorcontent_import"), dict) else {},
        "magazine_import": item.get("magazine_import") if isinstance(item.get("magazine_import"), dict) else {},
        "unmatched": bool(item.get("unmatched")),
        "original_recipients": item.get("original_recipients") if isinstance(item.get("original_recipients"), list) else [],
    }


def webmail_get_message(mailbox: str, message_id: str) -> Dict[str, Any]:
    mailbox = normalise_email_address(mailbox or "")
    message_id = clean_webmail_message_id(message_id)
    resp = ddb.get_item(TableName=EMAIL_STATE_TABLE, Key={"pk": {"S": webmail_pk(mailbox)}, "sk": {"S": webmail_message_sk(message_id)}}, ConsistentRead=True)
    item = resp.get("Item")
    if not item:
        raise ValueError("Message not found.")
    return item_to_python(item)



def webmail_local_part(address: str) -> str:
    email = normalise_email_address(address or "")
    return email.split("@", 1)[0].strip().lower() if "@" in email else ""


def webmail_article_visibility_for_address(address: str) -> str:
    local = webmail_local_part(address)
    if local in ARTICLES_MEMBER_INBOUND_LOCAL_PARTS or local in {"clubarticle", "clubarticles"}:
        return "members"
    if local in ARTICLES_INBOUND_LOCAL_PARTS or local in {"article", "articles"}:
        return "public"
    return ""


def webmail_is_articles_address(address: str) -> bool:
    return bool(webmail_article_visibility_for_address(address))


def webmail_is_tripreports_address(address: str) -> bool:
    local = webmail_local_part(address)
    return local in TRIPREPORTS_INBOUND_LOCAL_PARTS or local in {"tripreport", "tripreports"}


def webmail_is_presentations_address(address: str) -> bool:
    local = webmail_local_part(address)
    return local in PRESENTATIONS_INBOUND_LOCAL_PARTS or local in {"presentation", "presentations"}


def webmail_is_magazinecontent_address(address: str) -> bool:
    local = webmail_local_part(address)
    return local in MAGAZINECONTENT_INBOUND_LOCAL_PARTS or local in {"magazinecontent", "magazine-content", "magazinearticles", "magazinearticle"}


def webmail_is_vendorcontent_address(address: str) -> bool:
    local = webmail_local_part(address)
    return local in VENDORCONTENT_INBOUND_LOCAL_PARTS or local in {"vendorcontent", "vendor-content", "vendorcontents"}


def webmail_is_magazines_address(address: str) -> bool:
    local = webmail_local_part(address)
    return local in MAGAZINES_INBOUND_LOCAL_PARTS or local in {"magazine", "magazines"}


def webmail_domain_from_recipients(recipients: List[str]) -> str:
    for recipient in recipients:
        email = normalise_email_address(recipient)
        if "@" in email:
            return email.split("@", 1)[1]
    return ""


def webmail_editor_mailbox_address(position_by_email: Dict[str, Dict[str, Any]], recipients: List[str]) -> str:
    for email, position in position_by_email.items():
        token = normalise_position_id(position.get("position_id") or position.get("position_name") or "")
        if token in {"editor", "magazine-editor", "magazineeditor", "newsletter-editor", "newslettereditor"}:
            return normalise_email_address(email)
    domain = webmail_domain_from_recipients(recipients)
    return f"editor@{domain}" if domain else ""


def find_member_by_article_sender(sender_email: str) -> Dict[str, Any] | None:
    email = normalise_email_address(sender_email or "")
    if not valid_email_address(email):
        return None
    for member in list_member_summaries(""):
        for key in ["contact_email", "email", "email_raw", "member_email", "preferred_email", "primary_email"]:
            if normalise_email_address(member.get(key) or "") == email:
                return member
    return None


def clean_article_precis(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", str(text or "")).strip()
    signoff_markers = {
        "73", "73s", "73's", "regards", "kind regards", "best regards",
        "cheers", "thanks", "thank you", "yours sincerely", "sincerely",
    }
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        marker = stripped.lower().strip(" .,!-–—")
        if stripped.startswith(">"):
            break
        if re.match(r"^On .+ wrote:$", stripped, re.I):
            break
        if marker in signoff_markers:
            break
        lines.append(line)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned[:1500]


def article_manifest_contains_source(source_message_id: str, source_attachment_key: str = "", source_attachment_index: Any = None) -> bool:
    try:
        manifest = load_articles_manifest()
    except Exception:
        return False
    for item in manifest.get("articles") or []:
        if not isinstance(item, dict):
            continue
        if source_attachment_key and str(item.get("source_attachment_key") or "") == source_attachment_key:
            return True
        if source_message_id and str(item.get("source_message_id") or "") == source_message_id:
            if source_attachment_index is None or str(item.get("source_attachment_index") or "") == str(source_attachment_index):
                return True
    return False


def import_article_from_email_attachment(title: str, precis: str, filename: str, payload: bytes, submitter: Dict[str, Any], message_id: str, visibility: str = "public", content_type: str = "", source_attachment_key: str = "", source_attachment_index: Any = None) -> Dict[str, Any]:
    safe_title = safe_header(title or filename or "Email article", 180) or "Email article"
    filename = webmail_attachment_safe_name(filename or "article")
    visibility = normalise_article_visibility(visibility)
    ext = webmail_attachment_ext(filename) or ".pdf"
    if ext in WEBMAIL_BLOCKED_ATTACHMENT_EXTENSIONS:
        raise ValueError("Attachment type is blocked for safety.")
    if ext not in WEBMAIL_ARTICLE_EXTENSIONS:
        raise ValueError("Attachment type is not supported for article publishing.")
    if article_manifest_contains_source(message_id, source_attachment_key, source_attachment_index):
        raise ValueError("already_imported")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    article_id = article_slug(f"{safe_title}-{message_id}-{filename}")
    key = f"{article_prefix_for_visibility(visibility)}{article_slug(safe_title)}-{timestamp}-{secrets.token_hex(3)}{ext}"
    bucket = article_storage_bucket_for_visibility(visibility)
    ctype = webmail_attachment_content_type(filename, content_type)
    put_args = {"Bucket": bucket, "Key": key, "Body": payload, "ContentType": ctype}
    if visibility == "public":
        put_args["CacheControl"] = "public, max-age=86400"
    else:
        put_args["ServerSideEncryption"] = "AES256"
    s3.put_object(**put_args)
    manifest = load_articles_manifest()
    items = [item for item in manifest.get("articles") or [] if isinstance(item, dict)]
    entry = {
        "id": article_id,
        "title": safe_title,
        "summary": clean_article_precis(precis),
        "precis": clean_article_precis(precis),
        "filename": key.rsplit("/", 1)[-1],
        "original_filename": filename,
        "key": key,
        "url": f"/{key}" if visibility == "public" else "",
        "visibility": visibility,
        "members_only": visibility == "members",
        "uploaded_at": utc_now(),
        "uploaded_by": str(submitter.get("sub") or submitter.get("email") or "email"),
        "uploaded_by_email": normalise_email_address(submitter.get("email") or ""),
        "uploaded_by_name": str(submitter.get("name") or submitter.get("display_callsign") or submitter.get("callsign") or submitter.get("email") or "LROC Member"),
        "source": "email",
        "source_message_id": message_id,
        "source_attachment_key": source_attachment_key,
        "source_attachment_index": str(source_attachment_index if source_attachment_index is not None else ""),
        "content_type": ctype,
        "document_type": webmail_attachment_kind_for_filename(filename, ctype),
        "file_extension": ext,
    }
    items = [item for item in items if str(item.get("id") or "") != article_id]
    items.insert(0, entry)
    manifest["articles"] = items
    save_articles_manifest(manifest)
    try:
        send_article_notification_email(entry)
    except Exception:
        pass
    return entry


def webmail_try_import_articles_from_email(parsed, sender_email: str, message_id: str, subject: str, body_text: str, visibility: str = "public") -> Dict[str, Any]:
    submitter = find_member_by_article_sender(sender_email) or {"email": normalise_email_address(sender_email), "name": webmail_contact_label_from_email(sender_email)}
    imported = []
    skipped = []
    for idx, part in enumerate(parsed.walk() if parsed else []):
        if part.is_multipart():
            continue
        filename = webmail_attachment_safe_name(part.get_filename() or "")
        ctype = str(part.get_content_type() or "").lower()
        disposition = str(part.get_content_disposition() or "").lower()
        if disposition != "attachment" and not filename:
            continue
        policy = webmail_attachment_type_policy(filename, ctype, target="articles")
        if not policy.get("allowed"):
            skipped.append({"filename": filename or f"attachment-{idx+1}", "reason": policy.get("reason") or "unsupported_type"})
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            skipped.append({"filename": filename or f"attachment-{idx+1}", "reason": "empty"})
            continue
        title = safe_header(subject or filename.rsplit(".", 1)[0] or "Email article", 180)
        try:
            entry = import_article_from_email_attachment(
                title,
                body_text or f"Submitted by email from {submitter.get('name') or submitter.get('email') or 'member'}.",
                filename or f"article-{len(imported)+1}{policy.get('extension') or '.pdf'}",
                payload,
                submitter,
                message_id,
                visibility=visibility,
                content_type=ctype,
                source_attachment_index=idx,
            )
            imported.append({"id": entry.get("id"), "title": entry.get("title"), "key": entry.get("key"), "visibility": visibility, "filename": entry.get("filename"), "document_type": entry.get("document_type")})
        except Exception as exc:
            reason = str(exc)[:300]
            skipped.append({"filename": filename or f"attachment-{idx+1}", "reason": reason})
    return {"imported": len(imported), "items": imported, "skipped": skipped, "submitter": {"sub": submitter.get("sub"), "email": submitter.get("email"), "name": submitter.get("name")}, "reason": "ok" if imported else "no_supported_article_attachments"}


def save_magazine_entry(title: str, filename: str, key: str, uploader_email: str, source: str, message_id: str = "") -> Dict[str, Any]:
    safe_title = safe_header(title or filename or "Club magazine", 180) or "Club magazine"
    mag_id = article_slug(f"{safe_title}-{key.rsplit('/', 1)[-1]}")
    manifest = load_magazines_manifest()
    items = [item for item in manifest.get("magazines") or [] if isinstance(item, dict)]
    entry = {
        "id": mag_id,
        "title": safe_title,
        "filename": key.rsplit("/", 1)[-1],
        "key": key,
        "url": f"/{key}",
        "published_at": utc_now(),
        "uploaded_at": utc_now(),
        "uploaded_by_email": normalise_email_address(uploader_email),
        "source": source,
        "source_message_id": message_id,
    }
    items = [item for item in items if str(item.get("id") or "") != mag_id]
    items.insert(0, entry)
    manifest["magazines"] = items
    save_magazines_manifest(manifest)
    return entry


def import_magazine_from_payload(title: str, filename: str, payload: bytes, sender_email: str, message_id: str, source: str = "email") -> Dict[str, Any]:
    if not SITE_BUCKET:
        raise RuntimeError("SITE_BUCKET is not configured.")
    safe_title = safe_header(title or filename or "Club magazine", 180) or "Club magazine"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    key = f"{MAGAZINES_PREFIX}{article_slug(safe_title)}-{timestamp}-{secrets.token_hex(3)}.pdf"
    s3.put_object(Bucket=SITE_BUCKET, Key=key, Body=payload, ContentType="application/pdf", CacheControl="public, max-age=86400")
    return save_magazine_entry(safe_title, filename or key.rsplit("/", 1)[-1], key, sender_email, source, message_id)


def import_magazine_from_email_attachment(title: str, filename: str, payload: bytes, sender_email: str, message_id: str) -> Dict[str, Any]:
    return import_magazine_from_payload(title, filename, payload, sender_email, message_id, source="email")


def magazine_pdf_payloads_from_attachment(filename: str, ctype: str, payload: bytes) -> List[Tuple[str, bytes]]:
    filename = webmail_attachment_safe_name(filename or "")
    ctype = str(ctype or "").lower()
    if not payload:
        return []
    if ctype in {"application/pdf", "application/x-pdf"} or filename.lower().endswith(".pdf"):
        return [(filename or "magazine.pdf", payload)]
    if ctype in {"application/zip", "application/x-zip-compressed", "multipart/x-zip"} or filename.lower().endswith(".zip"):
        out: List[Tuple[str, bytes]] = []
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                infos = [info for info in zf.infolist() if not info.is_dir() and info.filename.lower().endswith(".pdf")]
                for info in infos[:20]:
                    if info.file_size > 25 * 1024 * 1024:
                        continue
                    data = zf.read(info)
                    if data:
                        out.append((webmail_attachment_safe_name(os.path.basename(info.filename) or "magazine.pdf"), data))
        except Exception:
            return []
        return out
    return []


def webmail_try_import_magazines_from_email(parsed, sender_email: str, message_id: str, subject: str) -> Dict[str, Any]:
    imported = []
    for part in parsed.walk() if parsed else []:
        if part.is_multipart():
            continue
        filename = webmail_attachment_safe_name(part.get_filename() or "")
        ctype = str(part.get_content_type() or "").lower()
        disposition = str(part.get_content_disposition() or "").lower()
        if disposition != "attachment" and not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        for pdf_name, pdf_payload in magazine_pdf_payloads_from_attachment(filename, ctype, payload):
            title = safe_header(subject or pdf_name.rsplit(".", 1)[0] or "Club magazine", 180)
            entry = import_magazine_from_email_attachment(title, pdf_name or f"magazine-{len(imported)+1}.pdf", pdf_payload, sender_email, message_id)
            imported.append({"id": entry.get("id"), "title": entry.get("title"), "key": entry.get("key"), "filename": pdf_name})
    return {"imported": len(imported), "items": imported, "reason": "ok" if imported else "no_pdf_attachments"}



def webmail_submission_targets_for_message(item: Dict[str, Any]) -> List[str]:
    addresses: List[str] = []
    for field in ("mailbox", "to", "cc", "bcc", "original_recipients"):
        value = item.get(field)
        if isinstance(value, list):
            addresses.extend([normalise_email_address(x) for x in value if normalise_email_address(x)])
        elif isinstance(value, str):
            addresses.append(normalise_email_address(value))
    targets: List[str] = []
    if any(webmail_is_articles_address(a) for a in addresses):
        targets.append("articles")
    if any(webmail_is_tripreports_address(a) for a in addresses):
        targets.append("tripreports")
    if any(webmail_is_presentations_address(a) for a in addresses):
        targets.append("presentations")
    if any(webmail_is_magazinecontent_address(a) for a in addresses):
        targets.append("magazinecontent")
    if any(webmail_is_vendorcontent_address(a) for a in addresses):
        targets.append("vendorcontent")
    if any(webmail_is_magazines_address(a) for a in addresses):
        targets.append("magazines")
    return targets


def webmail_read_stored_attachment(att: Dict[str, Any]) -> bytes:
    key = str(att.get("key") or "")
    if not key:
        return b""
    obj = s3.get_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=key)
    return obj.get("Body").read()


def webmail_find_existing_submission(kind: str, message_id: str, attachment_key: str = "") -> Dict[str, Any] | None:
    try:
        resp = ddb.query(
            TableName=EMAIL_STATE_TABLE,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :sk)",
            ExpressionAttributeValues={":pk": {"S": f"WEBMAIL#SUBMISSIONS#{kind}"}, ":sk": {"S": f"SUBMISSION#{clean_webmail_message_id(message_id)}#"}},
        )
    except Exception:
        return None
    for raw in resp.get("Items") or []:
        item = item_to_python(raw)
        if attachment_key and str(item.get("source_attachment_key") or "") == attachment_key:
            return item
    return None


def webmail_store_submission_record(kind: str, item: Dict[str, Any], att: Dict[str, Any], dest_key: str, status: str = "stored") -> Dict[str, Any]:
    require_email_state_table()
    message_id = clean_webmail_message_id(item.get("message_id") or "")
    idx = str(att.get("index") if att.get("index") is not None else att.get("source_attachment_index") or "0")
    sub_id = article_slug(f"{kind}-{message_id}-{idx}-{att.get('filename') or ''}")
    record = {
        "pk": f"WEBMAIL#SUBMISSIONS#{kind}",
        "sk": f"SUBMISSION#{message_id}#{idx}",
        "item_type": "webmail_submission",
        "submission_id": sub_id,
        "kind": kind,
        "status": status,
        "message_id": message_id,
        "mailbox": normalise_email_address(item.get("mailbox") or ""),
        "subject": str(item.get("subject") or ""),
        "from": str(item.get("from") or ""),
        "received_at": str(item.get("received_at") or item.get("created_at") or ""),
        "source_attachment_key": str(att.get("key") or ""),
        "source_attachment_index": idx,
        "filename": str(att.get("filename") or ""),
        "content_type": str(att.get("content_type") or ""),
        "document_type": webmail_attachment_kind_for_filename(att.get("filename"), att.get("content_type")),
        "extension": webmail_attachment_ext(att.get("filename")),
        "size": int(att.get("size") or 0),
        "s3_bucket": WEBMAIL_MAIL_BUCKET,
        "s3_key": dest_key,
        "scan_status": str(att.get("scan_status") or ""),
        "scan_provider": str(att.get("scan_provider") or ""),
        "created_at": utc_now_precise(),
        "updated_at": utc_now_precise(),
    }
    ddb.put_item(TableName=EMAIL_STATE_TABLE, Item=python_to_item(record))
    return record


def webmail_store_submission_copy(kind: str, item: Dict[str, Any], att: Dict[str, Any], payload: bytes) -> Dict[str, Any]:
    message_id = clean_webmail_message_id(item.get("message_id") or "")
    idx = int(att.get("index") or 0)
    filename = webmail_attachment_safe_name(att.get("filename") or f"{kind}-{idx+1}")
    existing = webmail_find_existing_submission(kind, message_id, str(att.get("key") or ""))
    if existing:
        return {"stored": False, "duplicate": True, "item": existing, "key": existing.get("s3_key")}
    dest_key = webmail_submission_key(kind, message_id, idx, filename)
    s3.put_object(
        Bucket=WEBMAIL_MAIL_BUCKET,
        Key=dest_key,
        Body=payload,
        ContentType=webmail_attachment_content_type(filename, att.get("content_type")),
        ServerSideEncryption="AES256",
        Metadata={"source-message-id": message_id[:180], "source-attachment-key": str(att.get("key") or "")[:900], "submission-kind": kind},
    )
    record = webmail_store_submission_record(kind, item, att, dest_key, status="stored")
    return {"stored": True, "duplicate": False, "item": record, "key": dest_key}


def webmail_submitter_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    from_addresses = webmail_parse_address_list(item.get("from") or "")
    sender_email = from_addresses[0] if from_addresses else ""
    member = find_member_by_article_sender(sender_email) or {}
    return {
        "sub": str(member.get("sub") or member.get("id") or ""),
        "email": normalise_email_address(member.get("email") or member.get("contact_email") or sender_email),
        "name": str(member.get("name") or member.get("full_name") or webmail_contact_label_from_email(sender_email) or sender_email or "Email submitter"),
    }


def webmail_import_articles_from_stored_message(item: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
    attachments = item.get("attachments") if isinstance(item.get("attachments"), list) else []
    visibility = "members" if any(webmail_article_visibility_for_address(a) == "members" for a in (item.get("to") or []) + (item.get("cc") or []) + (item.get("original_recipients") or [])) else "public"
    submitter = webmail_submitter_from_item(item)
    imported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for att in attachments:
        if not isinstance(att, dict) or bool(att.get("skipped")):
            continue
        filename = webmail_attachment_safe_name(att.get("filename") or "article")
        policy = webmail_attachment_type_policy(filename, att.get("content_type"), target="articles")
        if not policy.get("allowed"):
            skipped.append({"filename": filename, "reason": policy.get("reason") or "unsupported_type"})
            continue
        if not bool(att.get("import_allowed")):
            skipped.append({"filename": filename, "reason": att.get("scan_status") or "pending_scan"})
            continue
        if article_manifest_contains_source(str(item.get("message_id") or ""), str(att.get("key") or ""), att.get("index")):
            skipped.append({"filename": filename, "reason": "already_imported"})
            continue
        if dry_run:
            imported.append({"title": item.get("subject") or filename, "filename": filename, "dry_run": True})
            continue
        try:
            payload = webmail_read_stored_attachment(att)
            entry = import_article_from_email_attachment(
                str(item.get("subject") or filename.rsplit(".", 1)[0] or "Email article"),
                str(item.get("body_text") or ""),
                filename,
                payload,
                submitter,
                str(item.get("message_id") or ""),
                visibility=visibility,
                content_type=str(att.get("content_type") or ""),
                source_attachment_key=str(att.get("key") or ""),
                source_attachment_index=att.get("index"),
            )
            imported.append({"id": entry.get("id"), "title": entry.get("title"), "key": entry.get("key"), "filename": entry.get("filename"), "document_type": entry.get("document_type"), "visibility": visibility})
        except Exception as exc:
            skipped.append({"filename": filename, "reason": str(exc)[:300]})
    return {"imported": len(imported), "items": imported, "skipped": skipped, "visibility": visibility, "reason": "ok" if imported else "no_importable_article_attachments"}


def webmail_store_submission_attachments(item: Dict[str, Any], kind: str, *, dry_run: bool = False) -> Dict[str, Any]:
    attachments = item.get("attachments") if isinstance(item.get("attachments"), list) else []
    stored: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for att in attachments:
        if not isinstance(att, dict) or bool(att.get("skipped")):
            continue
        filename = webmail_attachment_safe_name(att.get("filename") or f"{kind}-attachment")
        policy = webmail_attachment_type_policy(filename, att.get("content_type"), target=kind)
        if not policy.get("allowed"):
            skipped.append({"filename": filename, "reason": policy.get("reason") or "unsupported_type"})
            continue
        if not bool(att.get("import_allowed")):
            skipped.append({"filename": filename, "reason": att.get("scan_status") or "pending_scan"})
            continue
        if dry_run:
            stored.append({"filename": filename, "dry_run": True})
            continue
        try:
            payload = webmail_read_stored_attachment(att)
            result = webmail_store_submission_copy(kind, item, att, payload)
            stored.append({"filename": filename, "key": result.get("key"), "duplicate": bool(result.get("duplicate"))})
        except Exception as exc:
            skipped.append({"filename": filename, "reason": str(exc)[:300]})
    return {"stored": len([x for x in stored if not x.get("duplicate")]), "items": stored, "skipped": skipped, "reason": "ok" if stored else "no_importable_submission_attachments"}


def webmail_process_submission_message(item: Dict[str, Any], *, dry_run: bool = False, refresh_scan: bool = True, persist: bool = True) -> Dict[str, Any]:
    direction = str(item.get("direction") or "").strip().lower()
    if direction != "inbound" and not bool(item.get("internal_delivery")):
        return {"processed": False, "reason": "not_inbound_or_internal_submission"}
    if str(item.get("folder") or "inbox") == "quarantine" or str(item.get("spam_status") or "") == "quarantine":
        return {"processed": False, "reason": "message_quarantined"}
    targets = webmail_submission_targets_for_message(item)
    if not targets:
        return {"processed": False, "reason": "no_submission_target"}
    attachments = item.get("attachments") if isinstance(item.get("attachments"), list) else []
    updated_attachments = webmail_update_attachment_statuses(attachments, webmail_message_spam_payload(item), refresh=refresh_scan)
    working = dict(item)
    working["attachments"] = updated_attachments
    results: Dict[str, Any] = {"processed": True, "targets": targets, "attachment_scan_summary": webmail_attachment_scan_summary(updated_attachments)}
    if "articles" in targets:
        results["article_import"] = webmail_import_articles_from_stored_message(working, dry_run=dry_run)
    if "tripreports" in targets:
        results["tripreport_import"] = webmail_store_submission_attachments(working, "tripreports", dry_run=dry_run)
    if "presentations" in targets:
        results["presentation_import"] = webmail_store_submission_attachments(working, "presentations", dry_run=dry_run)
    if "magazinecontent" in targets:
        results["magazinecontent_import"] = webmail_store_submission_attachments(working, "magazinecontent", dry_run=dry_run)
    if "vendorcontent" in targets:
        results["vendorcontent_import"] = webmail_store_submission_attachments(working, "vendorcontent", dry_run=dry_run)
    if persist and not dry_run:
        for field in ("article_import", "tripreport_import", "presentation_import", "magazinecontent_import", "vendorcontent_import"):
            if field in results:
                working[field] = results[field]
        working["attachments"] = updated_attachments
        working["submission_backfilled_at"] = utc_now_precise()
        webmail_index_message(working)
    return results



def webmail_refresh_message_attachment_scan_state(item: Dict[str, Any], *, refresh_scan: bool = True, persist: bool = True) -> Dict[str, Any]:
    """Refresh stored attachment scan metadata without requiring the message to be a submission target.

    This is used by the reader and admin reprocess path so old messages that were
    indexed before the current scan policy do not stay stuck at pending_scan when
    GuardDuty scanning is not required and the SES verdict is acceptable.
    """
    if not isinstance(item, dict):
        return item
    attachments = item.get("attachments") if isinstance(item.get("attachments"), list) else []
    if not attachments:
        return item
    updated = webmail_update_attachment_statuses(attachments, webmail_message_spam_payload(item), refresh=refresh_scan)
    working = dict(item)
    working["attachments"] = updated
    working["attachment_scan_summary"] = webmail_attachment_scan_summary(updated)
    working["attachment_scan_refreshed_at"] = utc_now_precise()
    if persist and (updated != attachments or item.get("attachment_scan_summary") != working.get("attachment_scan_summary")):
        webmail_index_message(working)
    return working


def handle_ses_inbound_event(event: Dict[str, Any]) -> Dict[str, Any]:
    require_webmail()
    results: List[Dict[str, Any]] = []
    position_by_email = webmail_position_map()
    unmatched = webmail_unmatched_mailbox_address()
    for record in event.get("Records") or []:
        ses = record.get("ses") or record.get("SES") or {}
        mail = ses.get("mail") or {}
        receipt = ses.get("receipt") or {}
        message_id = clean_webmail_message_id(mail.get("messageId") or mail.get("message_id") or uuid.uuid4().hex)
        raw_key = f"{WEBMAIL_INBOUND_PREFIX}{message_id}"
        try:
            raw = s3.get_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=raw_key)["Body"].read()
        except Exception as exc:
            results.append({"message_id": message_id, "indexed": 0, "error": f"raw mail not found at {raw_key}: {exc}"})
            continue
        try:
            parsed = BytesParser(policy=policy.default).parsebytes(raw)
        except Exception:
            parsed = None
        recipients = [normalise_email_address(x) for x in (receipt.get("recipients") or mail.get("destination") or []) if normalise_email_address(x)]
        matched_mailboxes = [r for r in recipients if r in position_by_email]
        article_visibilities = [webmail_article_visibility_for_address(r) for r in recipients]
        article_visibility = "members" if "members" in article_visibilities else ("public" if "public" in article_visibilities else "")
        article_recipient = bool(article_visibility)
        tripreports_recipient = any(webmail_is_tripreports_address(r) for r in recipients)
        presentations_recipient = any(webmail_is_presentations_address(r) for r in recipients)
        magazinecontent_recipient = any(webmail_is_magazinecontent_address(r) for r in recipients)
        vendorcontent_recipient = any(webmail_is_vendorcontent_address(r) for r in recipients)
        magazines_recipient = any(webmail_is_magazines_address(r) for r in recipients)
        target_mailboxes = matched_mailboxes or [unmatched]
        if article_recipient:
            article_box = next((r for r in recipients if webmail_article_visibility_for_address(r)), "")
            if article_box and article_box not in target_mailboxes:
                target_mailboxes.append(article_box)
        if tripreports_recipient:
            tripreports_box = next((r for r in recipients if webmail_is_tripreports_address(r)), "")
            if tripreports_box and tripreports_box not in target_mailboxes:
                target_mailboxes.append(tripreports_box)
            editor_box = webmail_editor_mailbox_address(position_by_email, recipients)
            if editor_box and editor_box not in target_mailboxes:
                target_mailboxes.append(editor_box)
        if presentations_recipient:
            presentations_box = next((r for r in recipients if webmail_is_presentations_address(r)), "")
            if presentations_box and presentations_box not in target_mailboxes:
                target_mailboxes.append(presentations_box)
        if magazinecontent_recipient:
            magazinecontent_box = next((r for r in recipients if webmail_is_magazinecontent_address(r)), "")
            if magazinecontent_box and magazinecontent_box not in target_mailboxes:
                target_mailboxes.append(magazinecontent_box)
        if vendorcontent_recipient:
            vendorcontent_box = next((r for r in recipients if webmail_is_vendorcontent_address(r)), "")
            if vendorcontent_box and vendorcontent_box not in target_mailboxes:
                target_mailboxes.append(vendorcontent_box)
        if magazines_recipient:
            magazines_box = next((r for r in recipients if webmail_is_magazines_address(r)), "")
            if magazines_box and magazines_box not in target_mailboxes:
                target_mailboxes.append(magazines_box)
        spam = webmail_spam_status_from_receipt(receipt)
        folder = "quarantine" if spam["quarantine"] else "inbox"
        body_text, body_html = webmail_body_from_message(parsed) if parsed else ("", "")
        subject = safe_header(parsed.get("Subject") if parsed else mail.get("commonHeaders", {}).get("subject"), 250)
        from_header = safe_header(parsed.get("From") if parsed else "", 250)
        from_addresses = webmail_parse_address_list(parsed.get("From") if parsed else mail.get("source"))
        from_email = from_addresses[0] if from_addresses else normalise_email_address(mail.get("source") or "")
        from_display = from_header.split("<", 1)[0].strip().strip('"') if from_header else webmail_contact_label_from_email(from_email)
        to_list = webmail_parse_address_list(parsed.get("To") if parsed else recipients)
        cc_list = webmail_parse_address_list(parsed.get("Cc") if parsed else "")
        header_article_visibilities = [webmail_article_visibility_for_address(r) for r in to_list + cc_list]
        if any(header_article_visibilities):
            article_visibility = "members" if "members" in header_article_visibilities else (article_visibility or "public")
            article_recipient = True
        if any(webmail_is_tripreports_address(r) for r in to_list + cc_list):
            tripreports_recipient = True
            tripreports_box = next((r for r in to_list + cc_list if webmail_is_tripreports_address(r)), "")
            if tripreports_box and tripreports_box not in target_mailboxes:
                target_mailboxes.append(tripreports_box)
            editor_box = webmail_editor_mailbox_address(position_by_email, recipients + to_list + cc_list)
            if editor_box and editor_box not in target_mailboxes:
                target_mailboxes.append(editor_box)
        if any(webmail_is_presentations_address(r) for r in to_list + cc_list):
            presentations_recipient = True
            presentations_box = next((r for r in to_list + cc_list if webmail_is_presentations_address(r)), "")
            if presentations_box and presentations_box not in target_mailboxes:
                target_mailboxes.append(presentations_box)
        if any(webmail_is_magazinecontent_address(r) for r in to_list + cc_list):
            magazinecontent_recipient = True
            magazinecontent_box = next((r for r in to_list + cc_list if webmail_is_magazinecontent_address(r)), "")
            if magazinecontent_box and magazinecontent_box not in target_mailboxes:
                target_mailboxes.append(magazinecontent_box)
        if any(webmail_is_vendorcontent_address(r) for r in to_list + cc_list):
            vendorcontent_recipient = True
            vendorcontent_box = next((r for r in to_list + cc_list if webmail_is_vendorcontent_address(r)), "")
            if vendorcontent_box and vendorcontent_box not in target_mailboxes:
                target_mailboxes.append(vendorcontent_box)
        if any(webmail_is_magazines_address(r) for r in to_list + cc_list):
            magazines_recipient = True
        received_at = utc_now_precise()
        try:
            if parsed and parsed.get("Date"):
                dt = parsedate_to_datetime(str(parsed.get("Date")))
                if dt:
                    received_at = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        attachments = webmail_extract_attachments(parsed, message_id) if parsed else []
        attachments = webmail_update_attachment_statuses(attachments, spam, refresh=False)
        if from_email:
            webmail_remember_external_contacts([from_email], {}, ",".join(target_mailboxes), source="inbound", display_name=from_display, message_id=message_id)
        article_import: Dict[str, Any] = {}
        magazine_import: Dict[str, Any] = {}
        tripreport_import: Dict[str, Any] = {}
        presentation_import: Dict[str, Any] = {}
        magazinecontent_import: Dict[str, Any] = {}
        vendorcontent_import: Dict[str, Any] = {}
        if parsed and magazines_recipient and not spam.get("quarantine") and not WEBMAIL_REQUIRE_ATTACHMENT_SCAN:
            try:
                magazine_import = webmail_try_import_magazines_from_email(parsed, from_email, message_id, subject)
            except Exception as exc:
                # Inbound indexing must not fail just because a downstream magazine import failed.
                magazine_import = {"imported": 0, "reason": "magazine_import_failed", "error": str(exc)[:300]}
        if not spam.get("quarantine") and (article_recipient or tripreports_recipient or presentations_recipient or magazinecontent_recipient or vendorcontent_recipient):
            submission_seed = {
                "mailbox": target_mailboxes[0] if target_mailboxes else "",
                "message_id": message_id,
                "folder": folder,
                "direction": "inbound",
                "from": from_header or safe_header(mail.get("source") or ""),
                "to": to_list or recipients,
                "cc": cc_list,
                "subject": subject or "(no subject)",
                "received_at": received_at,
                "created_at": utc_now_precise(),
                "raw_s3_key": raw_key,
                "body_text": body_text,
                "attachments": attachments,
                "spam_status": spam["status"],
                "spam_verdicts": spam["verdicts"],
                "original_recipients": recipients,
            }
            try:
                submission_result = webmail_process_submission_message(submission_seed, dry_run=False, refresh_scan=False, persist=False)
                article_import = submission_result.get("article_import") if isinstance(submission_result.get("article_import"), dict) else ({"imported": 0, "reason": submission_result.get("reason")} if article_recipient else {})
                tripreport_import = submission_result.get("tripreport_import") if isinstance(submission_result.get("tripreport_import"), dict) else ({"received": True, "reason": submission_result.get("reason")} if tripreports_recipient else {})
                presentation_import = submission_result.get("presentation_import") if isinstance(submission_result.get("presentation_import"), dict) else ({"received": True, "reason": submission_result.get("reason")} if presentations_recipient else {})
                magazinecontent_import = submission_result.get("magazinecontent_import") if isinstance(submission_result.get("magazinecontent_import"), dict) else ({"received": True, "reason": submission_result.get("reason")} if magazinecontent_recipient else {})
                vendorcontent_import = submission_result.get("vendorcontent_import") if isinstance(submission_result.get("vendorcontent_import"), dict) else ({"received": True, "reason": submission_result.get("reason")} if vendorcontent_recipient else {})
            except Exception as exc:
                # Never bounce/drop mail because the article/trip/presentation handoff failed.
                err = str(exc)[:300]
                if article_recipient:
                    article_import = {"imported": 0, "reason": "submission_processing_failed", "error": err}
                if tripreports_recipient:
                    tripreport_import = {"stored": 0, "reason": "submission_processing_failed", "error": err}
                if presentations_recipient:
                    presentation_import = {"stored": 0, "reason": "submission_processing_failed", "error": err}
                if magazinecontent_recipient:
                    magazinecontent_import = {"stored": 0, "reason": "submission_processing_failed", "error": err}
                if vendorcontent_recipient:
                    vendorcontent_import = {"stored": 0, "reason": "submission_processing_failed", "error": err}
        elif tripreports_recipient:
            tripreport_import = {"received": True, "editor_mailbox": webmail_editor_mailbox_address(position_by_email, recipients + to_list + cc_list), "note": "Trip reports are indexed to the Editor mailbox for magazine workflow; they are not published to the site."}
        indexed = 0
        for mailbox in sorted(set(target_mailboxes)):
            position = position_by_email.get(mailbox) or {}
            item = {
                "mailbox": mailbox,
                "message_id": message_id,
                "folder": folder,
                "direction": "inbound",
                "from": from_header or safe_header(mail.get("source") or ""),
                "to": to_list or recipients,
                "cc": cc_list,
                "subject": subject or "(no subject)",
                "received_at": received_at,
                "created_at": utc_now_precise(),
                "raw_s3_key": raw_key,
                "body_text": body_text,
                "body_html": body_html,
                "attachments": attachments,
                "spam_status": spam["status"],
                "spam_verdicts": spam["verdicts"],
                "article_import": article_import,
                "magazine_import": magazine_import,
                "tripreport_import": tripreport_import,
                "presentation_import": presentation_import,
                "magazinecontent_import": magazinecontent_import,
                "vendorcontent_import": vendorcontent_import,
                "quarantine_until": (datetime.now(timezone.utc) + timedelta(days=WEBMAIL_SPAM_RETENTION_DAYS)).date().isoformat() if spam["quarantine"] else "",
                "unmatched": mailbox == unmatched,
                "original_recipients": recipients,
                "role_name": str(position.get("position_name") or ("Unmatched inbound mail" if mailbox == unmatched else mailbox)),
                "read": False,
            }
            webmail_index_message(item)
            indexed += 1
        results.append({"message_id": message_id, "indexed": indexed, "folder": folder, "recipients": recipients, "mailboxes": target_mailboxes})
    return response(200, {"message": "Inbound SES mail processed.", "results": results})


def webmail_backfill_submissions_event(event: Dict[str, Any]) -> Dict[str, Any]:
    # Direct Lambda invocation helper for trusted operators / one-off catch-up jobs.
    # API callers should use POST /admin/webmail/backfill-submissions instead.
    require_webmail()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
    fake_event = {"body": json.dumps(payload)}
    # This is intentionally not exposed through API Gateway without admin auth.
    return json.loads(admin_webmail_backfill_submissions_route(fake_event, {"cognito:groups": ["admins"]}).get("body") or "{}")


def admin_webmail_backfill_submissions_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    require_webmail()
    body = parse_body(event)
    mailbox = normalise_email_address(body.get("mailbox") or "")
    dry_run = bool(body.get("dry_run"))
    refresh_scan = bool(body.get("refresh_scan", True))
    try:
        limit = max(1, min(500, int(body.get("limit") or 100)))
    except Exception:
        limit = 100
    folders = body.get("folders") if isinstance(body.get("folders"), list) else ["inbox"]
    folders = {str(f or "").strip().lower() for f in folders if str(f or "").strip().lower() in WEBMAIL_FOLDERS} or {"inbox"}
    requested_ids_raw = body.get("message_ids") if isinstance(body.get("message_ids"), list) else []
    if body.get("message_id"):
        requested_ids_raw.append(body.get("message_id"))
    requested_ids = [clean_webmail_message_id(x) for x in requested_ids_raw if clean_webmail_message_id(x)]

    items: List[Dict[str, Any]] = []
    examined = 0
    pages = 0
    has_more = False

    def candidate(item: Dict[str, Any]) -> bool:
        if str(item.get("folder") or "inbox") not in folders:
            return False
        direction = str(item.get("direction") or "").strip().lower()
        if direction != "inbound" and not bool(item.get("internal_delivery")):
            return False
        if not webmail_submission_targets_for_message(item):
            return False
        return True

    if requested_ids:
        # Reprocess selected messages exactly, regardless of where they fall in the inbox.
        if not mailbox:
            raise ValueError("mailbox is required when message_id/message_ids are supplied.")
        for msg_id in requested_ids[:limit]:
            try:
                item = webmail_get_message(mailbox, msg_id)
                item = webmail_refresh_message_attachment_scan_state(item, refresh_scan=refresh_scan, persist=True)
                examined += 1
                if candidate(item):
                    items.append(item)
            except Exception:
                continue
    elif mailbox:
        # DynamoDB Query returns a single page unless LastEvaluatedKey is followed.
        # Keep paginating until we have enough candidate messages or the mailbox is exhausted.
        last_key = None
        while len(items) < limit and pages < 25:
            kwargs = {
                "TableName": EMAIL_STATE_TABLE,
                "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
                "ExpressionAttributeValues": {":pk": {"S": webmail_pk(mailbox)}, ":prefix": {"S": "MSG#"}},
                "Limit": 100,
                "ScanIndexForward": False,
            }
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = ddb.query(**kwargs)
            pages += 1
            for raw in resp.get("Items") or []:
                examined += 1
                item = item_to_python(raw)
                if candidate(item):
                    items.append(item)
                    if len(items) >= limit:
                        break
            last_key = resp.get("LastEvaluatedKey")
            has_more = bool(last_key)
            if not last_key:
                break
    else:
        last_key = None
        while len(items) < limit and pages < 50:
            kwargs = {
                "TableName": EMAIL_STATE_TABLE,
                "FilterExpression": "item_type = :type",
                "ExpressionAttributeValues": {":type": {"S": "webmail_message"}},
                "Limit": 100,
            }
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = ddb.scan(**kwargs)
            pages += 1
            for raw in resp.get("Items") or []:
                examined += 1
                item = item_to_python(raw)
                if candidate(item):
                    items.append(item)
                    if len(items) >= limit:
                        break
            last_key = resp.get("LastEvaluatedKey")
            has_more = bool(last_key)
            if not last_key:
                break

    considered = 0
    processed = 0
    imported = 0
    stored = 0
    skipped = 0
    results: List[Dict[str, Any]] = []
    for item in items:
        considered += 1
        result = webmail_process_submission_message(item, dry_run=dry_run, refresh_scan=refresh_scan, persist=True)
        if result.get("processed"):
            processed += 1
        art = result.get("article_import") if isinstance(result.get("article_import"), dict) else {}
        trp = result.get("tripreport_import") if isinstance(result.get("tripreport_import"), dict) else {}
        prs = result.get("presentation_import") if isinstance(result.get("presentation_import"), dict) else {}
        magc = result.get("magazinecontent_import") if isinstance(result.get("magazinecontent_import"), dict) else {}
        vend = result.get("vendorcontent_import") if isinstance(result.get("vendorcontent_import"), dict) else {}
        imported += int(art.get("imported") or 0)
        stored += int(trp.get("stored") or 0) + int(prs.get("stored") or 0) + int(magc.get("stored") or 0) + int(vend.get("stored") or 0)
        skipped += len(art.get("skipped") if isinstance(art.get("skipped"), list) else [])
        skipped += len(trp.get("skipped") if isinstance(trp.get("skipped"), list) else [])
        skipped += len(prs.get("skipped") if isinstance(prs.get("skipped"), list) else [])
        skipped += len(magc.get("skipped") if isinstance(magc.get("skipped"), list) else [])
        skipped += len(vend.get("skipped") if isinstance(vend.get("skipped"), list) else [])
        results.append({
            "message_id": item.get("message_id"),
            "mailbox": item.get("mailbox"),
            "subject": item.get("subject"),
            "targets": result.get("targets") or [],
            "article_import": art,
            "tripreport_import": trp,
            "presentation_import": prs,
            "magazinecontent_import": magc,
            "vendorcontent_import": vend,
            "attachment_scan_summary": result.get("attachment_scan_summary") or {},
            "reason": result.get("reason") or "ok",
        })
    return response(200, {
        "message": "Webmail submission backfill complete." if not dry_run else "Webmail submission backfill dry-run complete.",
        "dry_run": dry_run,
        "mailbox": mailbox,
        "folders": sorted(folders),
        "limit": limit,
        "examined": examined,
        "pages": pages,
        "has_more": has_more,
        "considered": considered,
        "processed": processed,
        "imported_articles": imported,
        "stored_submissions": stored,
        "skipped_attachments": skipped,
        "items": results[:100],
    })

def webmail_mailboxes_route(_event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    boxes = webmail_accessible_mailboxes(claims)
    default_box = next((b for b in boxes if b.get("preferred") or b.get("owned")), boxes[0] if boxes else {})
    return response(200, {
        "items": boxes,
        "default_mailbox": default_box.get("mailbox") or "",
        "enabled": webmail_enabled(),
        "configured": webmail_enabled(),
        "message": "Role webmail is configured." if webmail_enabled() else "Role mailbox access is available, but inbound SES webmail is not enabled in Terraform yet.",
    })


def webmail_list_messages_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    params = get_query_params(event)
    mailbox = normalise_email_address(params.get("mailbox") or "")
    folder = str(params.get("folder") or "inbox").strip().lower()
    if folder not in WEBMAIL_FOLDERS:
        folder = "inbox"
    webmail_get_mailbox_for_claims(claims, mailbox)
    resp = ddb.query(
        TableName=EMAIL_STATE_TABLE,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": {"S": webmail_pk(mailbox)}, ":prefix": {"S": "MSG#"}},
    )
    items = [item_to_python(item) for item in resp.get("Items") or []]
    items = [item for item in items if str(item.get("folder") or "inbox") == folder]
    items.sort(key=lambda item: str(item.get("received_at") or item.get("sent_at") or item.get("created_at") or ""), reverse=True)
    limit = max(1, min(100, int(params.get("limit") or 50)))
    return response(200, {"items": [webmail_message_summary(item) for item in items[:limit]], "count": len(items), "folder": folder})


def webmail_read_message_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    params = get_query_params(event)
    mailbox = normalise_email_address(params.get("mailbox") or "")
    message_id = ((event.get("pathParameters") or {}).get("message_id") or params.get("message_id") or "")
    webmail_get_mailbox_for_claims(claims, mailbox)
    item = webmail_get_message(mailbox, message_id)
    item = webmail_refresh_message_attachment_scan_state(item, refresh_scan=True, persist=False)
    item["read"] = True
    webmail_index_message(item)
    summary = webmail_message_summary(item)
    summary.update({
        "body_text": str(item.get("body_text") or ""),
        "body_html": str(item.get("body_html") or ""),
        "attachments": item.get("attachments") if isinstance(item.get("attachments"), list) else [],
        "raw_s3_key": str(item.get("raw_s3_key") or ""),
    })
    return response(200, {"item": summary})


def webmail_archive_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    mailbox = normalise_email_address(body.get("mailbox") or "")
    message_id = str(body.get("message_id") or "")
    folder = str(body.get("folder") or "archive").strip().lower()
    if folder not in WEBMAIL_FOLDERS:
        folder = "archive"
    webmail_get_mailbox_for_claims(claims, mailbox)
    item = webmail_get_message(mailbox, message_id)
    item["folder"] = folder
    item["archived_at"] = utc_now_precise() if folder == "archive" else str(item.get("archived_at") or "")
    webmail_index_message(item)
    return response(200, {"message": f"Message moved to {folder}.", "item": webmail_message_summary(item)})


def admin_webmail_delete_message_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    require_admin(claims)
    require_webmail()
    body = parse_body(event)
    mailbox = normalise_email_address(body.get("mailbox") or "")
    message_id = clean_webmail_message_id(body.get("message_id") or "")
    all_mailboxes = bool(body.get("all_mailboxes"))
    delete_objects = bool(body.get("delete_objects"))
    if not message_id:
        raise ValueError("message_id is required.")
    mailboxes: List[str] = []
    if all_mailboxes:
        try:
            resp = ddb.query(
                TableName=EMAIL_STATE_TABLE,
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                ExpressionAttributeValues={":pk": {"S": f"WEBMAIL#MSG#{message_id}"}, ":prefix": {"S": "MAILBOX#"}},
                Limit=100,
            )
            for raw in resp.get("Items") or []:
                item = item_to_python(raw)
                box = normalise_email_address(item.get("mailbox") or str(item.get("sk") or "").replace("MAILBOX#", "", 1))
                if box and box not in mailboxes:
                    mailboxes.append(box)
        except Exception:
            pass
    if mailbox and mailbox not in mailboxes:
        mailboxes.append(mailbox)
    if not mailboxes:
        raise ValueError("mailbox is required, or set all_mailboxes=true for a message with mirror records.")

    deleted: List[str] = []
    object_keys: set[str] = set()
    for box in mailboxes:
        try:
            item = webmail_get_message(box, message_id)
        except Exception:
            continue
        if delete_objects:
            raw_key = str(item.get("raw_s3_key") or "")
            if raw_key.startswith(WEBMAIL_INBOUND_PREFIX):
                object_keys.add(raw_key)
            for att in item.get("attachments") if isinstance(item.get("attachments"), list) else []:
                key = str(att.get("key") or "")
                if key.startswith(WEBMAIL_ATTACHMENT_PREFIX) or key.startswith(WEBMAIL_SUBMISSION_PREFIX):
                    object_keys.add(key)
        ddb.delete_item(TableName=EMAIL_STATE_TABLE, Key={"pk": {"S": webmail_pk(box)}, "sk": {"S": webmail_message_sk(message_id)}})
        ddb.delete_item(TableName=EMAIL_STATE_TABLE, Key={"pk": {"S": f"WEBMAIL#MSG#{message_id}"}, "sk": {"S": f"MAILBOX#{box}"}})
        deleted.append(box)

    deleted_objects = 0
    if delete_objects:
        for key in sorted(object_keys):
            try:
                s3.delete_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=key)
                deleted_objects += 1
            except Exception:
                pass
    return response(200, {"message": "Message deleted.", "message_id": message_id, "deleted_mailboxes": deleted, "deleted_objects": deleted_objects})


def webmail_create_attachment_upload_url_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise ValueError("Signed-in member is required.")
    filename = webmail_attachment_safe_name(body.get("filename") or "attachment.bin")
    content_type = str(body.get("content_type") or "application/octet-stream").strip() or "application/octet-stream"
    try:
        size = int(body.get("size") or 0)
    except Exception:
        size = 0
    if size <= 0:
        raise ValueError("Attachment size is required.")
    if size > WEBMAIL_MAX_ATTACHMENT_BYTES:
        raise ValueError(f"Attachment {filename} is too large.")
    key = webmail_compose_upload_key(sub, filename)
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": WEBMAIL_MAIL_BUCKET,
            "Key": key,
            "ContentType": content_type,
            "ServerSideEncryption": "AES256",
            "Metadata": {
                "owner-sub": sub[:120],
                "original-filename": filename[:180],
                "purpose": "webmail-compose-attachment",
            },
        },
        ExpiresIn=900,
    )
    return response(200, {"upload_url": upload_url, "key": key, "filename": filename, "content_type": content_type, "size": size})


def webmail_prepare_compose_attachments(raw_attachments: List[Dict[str, Any]], claims: Dict[str, Any]) -> List[Dict[str, Any]]:
    sub = str(claims.get("sub") or "").strip()
    prepared: List[Dict[str, Any]] = []
    total = 0
    for idx, attachment in enumerate(raw_attachments or []):
        if not isinstance(attachment, dict):
            raise ValueError("One of the attachments is not valid.")
        filename = webmail_attachment_safe_name(attachment.get("filename") or f"attachment-{idx+1}")
        ctype = str(attachment.get("content_type") or "application/octet-stream")
        upload_key = str(attachment.get("upload_key") or attachment.get("key") or "").strip()
        if upload_key:
            if not webmail_is_compose_upload_key(upload_key, sub):
                raise ValueError("One of the uploaded attachments is not valid for this member.")
            try:
                obj = s3.get_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=upload_key)
                payload = obj.get("Body").read()
                meta = obj.get("Metadata") or {}
                filename = webmail_attachment_safe_name(attachment.get("filename") or meta.get("original-filename") or upload_key.rsplit("/", 1)[-1])
                ctype = str(attachment.get("content_type") or obj.get("ContentType") or "application/octet-stream")
            except Exception as exc:
                raise ValueError("One of the uploaded attachments could not be read.") from exc
        else:
            raw_b64 = str(attachment.get("data") or "")
            try:
                payload = base64.b64decode(raw_b64, validate=True)
            except Exception as exc:
                raise ValueError("One of the attachments is not valid.") from exc
        size = len(payload)
        if size <= 0:
            raise ValueError(f"Attachment {filename} is empty.")
        if size > WEBMAIL_MAX_ATTACHMENT_BYTES:
            raise ValueError(f"Attachment {filename} is too large.")
        total += size
        if total > WEBMAIL_MAX_TOTAL_ATTACHMENT_BYTES:
            raise ValueError("Total attachment size is too large.")
        prepared.append({
            "filename": filename,
            "content_type": ctype,
            "size": size,
            "data": base64.b64encode(payload).decode("ascii"),
            "upload_key": upload_key,
        })
    return prepared


def webmail_attachment_url_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    mailbox = normalise_email_address(body.get("mailbox") or "")
    message_id = str(body.get("message_id") or "")
    key = str(body.get("key") or "")
    webmail_get_mailbox_for_claims(claims, mailbox)
    item = webmail_get_message(mailbox, message_id)
    allowed = {str(att.get("key") or "") for att in (item.get("attachments") if isinstance(item.get("attachments"), list) else [])}
    if key not in allowed:
        raise PermissionError("Attachment is not available for that mailbox message.")
    attachments = item.get("attachments") if isinstance(item.get("attachments"), list) else []
    updated = webmail_update_attachment_statuses(attachments, webmail_message_spam_payload(item), refresh=True)
    selected = next((att for att in updated if str(att.get("key") or "") == key), {})
    if not bool(selected.get("download_allowed")):
        item["attachments"] = updated
        webmail_index_message(item)
        raise PermissionError(f"Attachment is not available until malware scan is clean: {selected.get('scan_status') or 'pending_scan'}.")
    if updated != attachments:
        item["attachments"] = updated
        webmail_index_message(item)
    filename = str(selected.get("filename") or "attachment")
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": WEBMAIL_MAIL_BUCKET, "Key": key, "ResponseContentDisposition": f'attachment; filename="{webmail_attachment_safe_name(filename)}"'},
        ExpiresIn=DOWNLOAD_EXPIRY,
    )
    return response(200, {"url": url, "scan_status": selected.get("scan_status"), "scan_provider": selected.get("scan_provider")})


def webmail_contacts_pk() -> str:
    return "WEBMAIL#EXTERNAL_CONTACTS"


def webmail_contact_sk(email: str) -> str:
    return f"EMAIL#{normalise_email_address(email)}"


def webmail_contact_label_from_email(email: str) -> str:
    local = normalise_email_address(email).split("@", 1)[0]
    local = re.sub(r"[._+-]+", " ", local).strip()
    return re.sub(r"\s+", " ", local).title()[:120] if local else normalise_email_address(email)


def webmail_member_contact_email_from_summary(member: Dict[str, Any]) -> str:
    return normalise_email_address(member.get("contact_email") or member.get("email") or "")


def webmail_contact_match_text(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def webmail_contact_query_matches(query: str, haystack: str) -> bool:
    q = re.sub(r"\s+", " ", str(query or "").strip().lower())
    if not q:
        return True
    h = str(haystack or "").lower()
    return all(token in h for token in q.split() if token)




WEBMAIL_CURRENT_PENDING_STATUSES = {"", "active", "current", "financial", "due", "life", "pending", "provisional", "new", "applicant"}
WEBMAIL_OPTOUT_FIELDS = (
    "email_opt_out", "emailOptOut", "club_email_opt_out", "clubEmailOptOut",
    "bulk_email_opt_out", "bulkEmailOptOut", "webmail_opt_out", "webmailOptOut",
    "no_email", "noEmail", "do_not_email", "doNotEmail", "unsubscribed", "unsubscribe",
    "opt_out", "optOut", "mail_opt_out", "mailOptOut",
)


def webmail_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "t", "yes", "y", "on", "opted_out", "opt-out", "unsubscribe", "unsubscribed"}


def webmail_member_email_candidates(member: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    keys = [
        "contact_email", "contactEmail", "email", "Email", "email_raw", "emailRaw",
        "email_address", "emailAddress", "member_email", "memberEmail",
        "primary_email", "primaryEmail", "preferred_email", "preferredEmail", "mail", "Mail",
    ]
    for key in keys:
        value = member.get(key)
        values = value if isinstance(value, list) else [value]
        for item in values:
            email = normalise_email_address(item or "")
            if valid_email_address(email) and email not in candidates:
                candidates.append(email)
    return candidates


def webmail_member_has_email_opt_out(member: Dict[str, Any]) -> bool:
    return any(webmail_truthy(member.get(key)) for key in WEBMAIL_OPTOUT_FIELDS)


def webmail_member_is_current_or_pending(member: Dict[str, Any]) -> bool:
    if str(member.get("account_status") or "active").strip().lower() == "deleted":
        return False
    status = str(
        member.get("membership_status") or member.get("membershipStatus") or member.get("member_status") or member.get("memberStatus") or member.get("status") or ""
    ).strip().lower()
    return status in WEBMAIL_CURRENT_PENDING_STATUSES


def webmail_member_recipient_name(member: Dict[str, Any]) -> str:
    return str(
        member.get("name") or member.get("display_name") or member.get("displayName") or member.get("full_name") or member.get("fullName")
        or member.get("display_callsign") or member.get("callsign") or member.get("email") or "Member"
    ).strip()


def webmail_member_recipient_records() -> List[Dict[str, Any]]:
    by_email: Dict[str, Dict[str, Any]] = {}
    for member in list_member_summaries(""):
        if str(member.get("account_status") or "active").strip().lower() == "deleted":
            continue
        opted_out = webmail_member_has_email_opt_out(member)
        current_pending = webmail_member_is_current_or_pending(member)
        for email in webmail_member_email_candidates(member):
            if email in by_email:
                existing = by_email[email]
                existing["current_pending"] = bool(existing.get("current_pending") or current_pending)
                existing["opted_out"] = bool(existing.get("opted_out") or opted_out)
                continue
            by_email[email] = {
                "email": email,
                "name": webmail_member_recipient_name(member),
                "current_pending": current_pending,
                "opted_out": opted_out,
                "type": "member",
            }
    return list(by_email.values())


def webmail_opted_out_member_email_set() -> set[str]:
    return {item["email"] for item in webmail_member_recipient_records() if item.get("opted_out")}


def webmail_external_contact_records() -> List[Dict[str, Any]]:
    contacts: List[Dict[str, Any]] = []
    try:
        resp = ddb.query(
            TableName=EMAIL_STATE_TABLE,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={":pk": {"S": webmail_contacts_pk()}, ":prefix": {"S": "EMAIL#"}},
        )
        for raw in resp.get("Items") or []:
            item = item_to_python(raw)
            email = normalise_email_address(item.get("email") or "")
            if valid_email_address(email):
                contacts.append({"email": email, "name": str(item.get("display_name") or webmail_contact_label_from_email(email)), "type": "external"})
    except Exception:
        pass
    return contacts


def webmail_compose_group_recipients(groups: List[str]) -> Dict[str, Any]:
    requested = {str(group or "").strip().lower() for group in groups if str(group or "").strip()}
    if not requested:
        return {"recipients": [], "skipped": [], "groups": []}
    members = webmail_member_recipient_records()
    candidates: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    if "current_pending" in requested or "current-pending" in requested or "current_pending_members" in requested:
        for member in members:
            if member.get("current_pending"):
                if member.get("opted_out"):
                    skipped.append({"email": member["email"], "name": member.get("name", ""), "reason": "opted_out"})
                else:
                    candidates.append({"email": member["email"], "name": member.get("name", ""), "type": "current_pending_member"})
    if "others" in requested or "all_others" in requested or "other_contacts" in requested:
        known_roles = webmail_role_email_set()
        for member in members:
            if not member.get("current_pending"):
                if member.get("opted_out"):
                    skipped.append({"email": member["email"], "name": member.get("name", ""), "reason": "opted_out"})
                else:
                    candidates.append({"email": member["email"], "name": member.get("name", ""), "type": "other_member"})
        for contact in webmail_external_contact_records():
            if contact["email"] not in known_roles:
                candidates.append(contact)
    filtered = filter_sendable_recipients(candidates)
    skipped.extend(filtered.get("skipped") or [])
    return {"recipients": filtered.get("sendable") or [], "skipped": skipped, "groups": sorted(requested)}


def webmail_filter_compose_address_lists(to: List[str], cc: List[str], bcc: List[str]) -> Dict[str, Any]:
    opted_out = webmail_opted_out_member_email_set()
    skipped: List[Dict[str, Any]] = []

    def clean(values: List[str], bucket: str) -> List[str]:
        cleaned: List[str] = []
        for email in values:
            email_n = normalise_email_address(email)
            if not valid_email_address(email_n):
                continue
            if email_n in opted_out:
                skipped.append({"email": email_n, "reason": "opted_out", "bucket": bucket})
                continue
            suppression = get_email_suppression(email_n)
            if suppression and str(suppression.get("status") or "suppressed").lower() != "cleared":
                skipped.append({"email": email_n, "reason": str(suppression.get("reason") or "suppressed"), "bucket": bucket})
                continue
            if email_n not in cleaned:
                cleaned.append(email_n)
        return cleaned

    return {"to": clean(to, "to"), "cc": clean(cc, "cc"), "bcc": clean(bcc, "bcc"), "skipped": skipped}

def webmail_known_member_email_set() -> set[str]:
    emails: set[str] = set()
    for member in list_member_summaries(""):
        for key in ["contact_email", "email", "email_raw", "member_email", "preferred_email", "primary_email"]:
            email = normalise_email_address(member.get(key) or "")
            if valid_email_address(email):
                emails.add(email)
    return emails


def webmail_role_email_set() -> set[str]:
    return {normalise_email_address(item.get("mailbox") or email) for email, item in webmail_position_map().items() if valid_email_address(item.get("mailbox") or email)}


def webmail_remember_external_contacts(recipients: List[str], claims: Dict[str, Any] | None = None, mailbox: str = "", *, source: str = "webmail", display_name: str = "", message_id: str = "") -> None:
    if not recipients:
        return
    known_members = webmail_known_member_email_set()
    known_roles = webmail_role_email_set()
    now = utc_now_precise()
    claims = claims or {}
    actor_sub = str(claims.get("sub") or "")
    actor_name = str(claims.get("name") or claims.get("email") or actor_sub or "")
    for email in sorted({normalise_email_address(x) for x in recipients if valid_email_address(x)}):
        if email in known_members or email in known_roles:
            continue
        key = {"pk": {"S": webmail_contacts_pk()}, "sk": {"S": webmail_contact_sk(email)}}
        existing: Dict[str, Any] = {}
        try:
            resp = ddb.get_item(TableName=EMAIL_STATE_TABLE, Key=key)
            if resp.get("Item"):
                existing = item_to_python(resp["Item"])
        except Exception:
            existing = {}
        label = str(display_name or existing.get("display_name") or webmail_contact_label_from_email(email)).strip()
        item = {
            "pk": webmail_contacts_pk(),
            "sk": webmail_contact_sk(email),
            "item_type": "webmail_external_contact",
            "email": email,
            "display_name": label,
            "source": source or "webmail",
            "first_used_at": str(existing.get("first_used_at") or now),
            "last_used_at": now,
            "use_count": int(existing.get("use_count") or 0) + 1,
            "last_used_by_sub": actor_sub,
            "last_used_by_name": actor_name,
            "last_used_from_mailbox": normalise_email_address(mailbox),
            "last_message_id": clean_webmail_message_id(message_id) if message_id else str(existing.get("last_message_id") or ""),
        }
        try:
            ddb.put_item(TableName=EMAIL_STATE_TABLE, Item=python_to_item(item))
        except Exception:
            pass


def webmail_contact_suggestions_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    params = get_query_params(event)
    query = re.sub(r"\s+", " ", str(params.get("q") or params.get("query") or "").strip()).lower()
    if len(query) < 3:
        return response(200, {"items": []})
    webmail_accessible_mailboxes(claims)  # access check / role refresh side effect
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(email: str, label: str, source_type: str, detail: str = "") -> None:
        email_n = normalise_email_address(email)
        if not valid_email_address(email_n) or email_n in seen:
            return
        haystack = webmail_contact_match_text(email_n, label, detail)
        if not webmail_contact_query_matches(query, haystack):
            return
        seen.add(email_n)
        items.append({"email": email_n, "label": label or email_n, "type": source_type, "detail": detail})

    for member in list_member_summaries(query):
        email = webmail_member_contact_email_from_summary(member)
        if not valid_email_address(email):
            continue
        label_bits = [str(member.get("name") or "").strip(), str(member_summary_display_number(member) or "").strip()]
        label = " · ".join([x for x in label_bits if x]) or email
        detail = "Member"
        add(email, label, "member", detail)

    for _email, position in webmail_position_map().items():
        mailbox = normalise_email_address(position.get("mailbox") or _email)
        label = str(position.get("position_name") or position.get("position_id") or mailbox).strip()
        add(mailbox, label, "role", "Role / service account")

    try:
        resp = ddb.query(
            TableName=EMAIL_STATE_TABLE,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={":pk": {"S": webmail_contacts_pk()}, ":prefix": {"S": "EMAIL#"}},
        )
        contacts = [item_to_python(item) for item in resp.get("Items") or []]
        contacts.sort(key=lambda item: (str(item.get("last_used_at") or ""), int(item.get("use_count") or 0)), reverse=True)
        for contact in contacts:
            email = normalise_email_address(contact.get("email") or "")
            label = str(contact.get("display_name") or webmail_contact_label_from_email(email))
            detail = f"External · used {int(contact.get('use_count') or 0)} time{'s' if int(contact.get('use_count') or 0) != 1 else ''}"
            add(email, label, "external", detail)
    except Exception:
        pass

    rank = {"member": 0, "role": 1, "external": 2}
    items.sort(key=lambda item: (rank.get(item.get("type"), 9), item.get("label", "").lower(), item.get("email", "")))
    return response(200, {"items": items[:12], "query": query, "count": len(items)})


def webmail_split_signature_block(body_text: str) -> tuple[str, str]:
    """Split compose text into message body and the editor's signature.

    Role Webmail keeps club branding out of the first visible HTML block.
    The normal compose signature is detected near the end of the message and
    rendered as a compact branded footer instead.
    """
    text = str(body_text or "").strip()
    if not text:
        return "", ""
    lines = text.splitlines()
    if len(lines) < 2:
        return text, ""
    window_start = max(0, len(lines) - 14)
    marker_index = -1
    for idx in range(len(lines) - 1, window_start - 1, -1):
        line = lines[idx].strip().lower().replace("’", "'")
        if line in {"regards", "regards,", "kind regards", "kind regards,", "73s", "73s,", "73's", "73's,"}:
            marker_index = idx
            break
    if marker_index >= 0 and len(lines) - marker_index <= 12:
        body = "\n".join(lines[:marker_index]).strip()
        signature = "\n".join(lines[marker_index:]).strip()
        return body, signature
    for idx in range(len(lines) - 1, window_start - 1, -1):
        if "land rover owners club" in lines[idx].strip().lower():
            start = max(window_start, idx - 2)
            body = "\n".join(lines[:start]).strip()
            signature = "\n".join(lines[start:]).strip()
            return body, signature
    return text, ""


def webmail_html_paragraphs(text: str) -> str:
    return "".join(
        f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>"
        for part in re.split(r"\n\s*\n", str(text or ""))
        if part.strip()
    )


def webmail_branded_html(body_text: str, role_name: str) -> str:
    logo = WEBMAIL_CLUB_LOGO_URL or (f"{SITE_BASE_URL}/assets/lroc-logo.png" if SITE_BASE_URL else "")
    message_text, signature_text = webmail_split_signature_block(body_text)
    paras = webmail_html_paragraphs(message_text)
    fallback_signature = f"Regards,\n{role_name or 'LROC'}\nLand Rover Owners Club of Australia Inc"
    signature_html = html.escape(signature_text or fallback_signature).replace("\n", "<br>")
    logo_html = f'<img src="{html.escape(logo)}" alt="LROC" style="height:42px;width:auto;margin-right:12px;flex:0 0 auto">' if logo else '<strong style="font-size:18px;color:#7f1d1d;margin-right:12px;flex:0 0 auto">LROC</strong>'
    return (
        '<div style="font-family:Arial,sans-serif;line-height:1.55;color:#111827">'
        f'{paras}'
        '<div style="border-top:1px solid #d1d5db;margin-top:18px;padding-top:12px;display:flex;align-items:flex-start;color:#374151">'
        f'{logo_html}'
        '<div style="font-size:13px;line-height:1.45">'
        f'{signature_html}'
        '</div></div>'
        '</div>'
    )


def webmail_build_raw_email(from_address: str, from_name: str, to: List[str], cc: List[str], subject: str, body_text: str, attachments: List[Dict[str, Any]], role_name: str) -> bytes:
    root = MIMEMultipart("mixed")
    root["From"] = formataddr((from_name or role_name or "LROC", from_address))
    root["To"] = ", ".join(to)
    if cc:
        root["Cc"] = ", ".join(cc)
    root["Reply-To"] = from_address
    root["Subject"] = safe_header(subject or "(no subject)", 250)
    root["Message-ID"] = make_msgid(domain=from_address.split("@")[-1] if "@" in from_address else None)
    root["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(str(body_text or ""), "plain", "utf-8"))
    alt.attach(MIMEText(webmail_branded_html(body_text, role_name), "html", "utf-8"))
    root.attach(alt)
    for attachment in attachments:
        filename = webmail_attachment_safe_name(attachment.get("filename") or "attachment")
        ctype = str(attachment.get("content_type") or "application/octet-stream")
        raw_b64 = str(attachment.get("data") or "")
        try:
            payload = base64.b64decode(raw_b64, validate=True)
        except Exception:
            raise ValueError(f"Attachment {filename} is not valid base64.")
        if len(payload) > WEBMAIL_MAX_ATTACHMENT_BYTES:
            raise ValueError(f"Attachment {filename} is too large.")
        maintype, subtype = (ctype.split("/", 1) + ["octet-stream"])[:2] if "/" in ctype else ("application", "octet-stream")
        part = MIMEBase(maintype, subtype)
        part.set_payload(payload)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        part.add_header("Content-Type", ctype, name=filename)
        root.attach(part)
    return root.as_bytes()


def webmail_send_member_copy_email(member_email: str, mailbox: str, role_name: str, subject: str, body_text: str, to: List[str], cc: List[str], bcc: List[str], attachment_count: int) -> Dict[str, Any]:
    """Send the role holder a separate no-reply copy of an outbound webmail message.

    This deliberately does not BCC the role holder into the live message thread.
    Their personal/member contact email receives a no-reply notification copy, so
    replying from that private mailbox does not accidentally continue club
    correspondence outside the role mailbox.
    """
    member_email = normalise_email_address(member_email or "")
    if not member_email or not valid_email_address(member_email) or not ses_email_available():
        return {"sent": False, "skipped": True, "reason": "no member email or SES unavailable"}
    copy_subject = safe_header(f"Copy of sent LROC {role_name or 'role'} email: {subject}", 250)
    rows = [
        ("Role mailbox", mailbox),
        ("Role", role_name or "LROC"),
        ("To", ", ".join(to) or "—"),
        ("CC", ", ".join(cc) or "—"),
        ("BCC", ", ".join(bcc) or "—"),
        ("Attachments", str(attachment_count)),
    ]
    warning = (
        "This is a no-reply copy for your records. Please do not reply from this personal mailbox. "
        "Use the LROC Webmail page to continue this correspondence from the role mailbox."
    )
    text = (
        f"{warning}\n\n"
        f"Role mailbox: {mailbox}\n"
        f"Role: {role_name or 'LROC'}\n"
        f"To: {', '.join(to) or '—'}\n"
        f"CC: {', '.join(cc) or '—'}\n"
        f"BCC: {', '.join(bcc) or '—'}\n"
        f"Attachments: {attachment_count}\n\n"
        f"Original message:\n{body_text}"
    )
    html_body = simple_html_email(
        "LROC Webmail sent-copy notice",
        [warning, "Original message content is shown below for your records.", body_text],
        rows=rows,
    )
    return safe_send_email_via_ses(
        [member_email],
        copy_subject,
        text,
        html_body,
        from_email=SES_FROM_EMAIL,
        reply_to=SES_FROM_EMAIL,
    )


def webmail_internal_recipient_mailboxes(addresses: List[str]) -> List[str]:
    roles = webmail_role_email_set()
    seen: set[str] = set()
    out: List[str] = []
    for email in addresses:
        email_n = normalise_email_address(email)
        if email_n in roles and email_n not in seen:
            seen.add(email_n)
            out.append(email_n)
    return out


def webmail_internal_article_recipients(addresses: List[str]) -> List[str]:
    return [normalise_email_address(addr) for addr in addresses if webmail_is_articles_address(addr)]


def webmail_compose_attachment_payload(attachment: Dict[str, Any]) -> bytes:
    try:
        return base64.b64decode(str(attachment.get("data") or ""), validate=True)
    except Exception as exc:
        filename = webmail_attachment_safe_name(attachment.get("filename") or "attachment")
        raise ValueError(f"Attachment {filename} is not valid.") from exc


def webmail_import_compose_articles(internal_recipients: List[str], attachments: List[Dict[str, Any]], claims: Dict[str, Any], subject: str, body_text: str, message_id: str) -> Dict[str, Any]:
    article_recipients = [addr for addr in internal_recipients if webmail_is_articles_address(addr)]
    if not article_recipients:
        return {"imported": 0, "items": [], "reason": "not_article_recipient"}
    visibility = "members" if any(webmail_article_visibility_for_address(addr) == "members" for addr in article_recipients) else "public"
    submitter = {
        "sub": str(claims.get("sub") or ""),
        "email": webmail_member_contact_email(claims),
        "name": str(claims.get("name") or claims.get("email") or "LROC Member"),
    }
    try:
        if submitter["sub"]:
            meta = get_member_metadata(submitter["sub"])
            submitter["name"] = str(meta.get("name") or meta.get("full_name") or submitter["name"] or "LROC Member")
    except Exception:
        pass
    imported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for idx, attachment in enumerate(attachments):
        filename = webmail_attachment_safe_name(attachment.get("filename") or f"article-{idx+1}.pdf")
        ctype = str(attachment.get("content_type") or "").lower()
        policy = webmail_attachment_type_policy(filename, ctype, target="articles")
        if not policy.get("allowed"):
            skipped.append({"filename": filename, "reason": policy.get("reason") or "unsupported_type"})
            continue
        try:
            payload = webmail_compose_attachment_payload(attachment)
        except Exception:
            skipped.append({"filename": filename, "reason": "invalid_attachment"})
            continue
        if not payload:
            skipped.append({"filename": filename, "reason": "empty"})
            continue
        try:
            entry = import_article_from_email_attachment(subject or filename.rsplit(".", 1)[0], body_text or f"Submitted from LROC Webmail by {submitter.get('name') or 'member'}.", filename, payload, submitter, f"{message_id}-{idx}", visibility=visibility, content_type=ctype, source_attachment_index=idx)
            imported.append({"id": entry.get("id"), "title": entry.get("title"), "key": entry.get("key"), "visibility": visibility, "document_type": entry.get("document_type")})
        except Exception as exc:
            skipped.append({"filename": filename, "reason": str(exc)[:300]})
    return {"imported": len(imported), "items": imported, "skipped": skipped, "visibility": visibility, "reason": "ok" if imported else "no_supported_article_attachments"}


def webmail_internal_magazine_recipients(addresses: List[str]) -> List[str]:
    return [normalise_email_address(addr) for addr in addresses if webmail_is_magazines_address(addr)]


def webmail_import_compose_magazines(internal_recipients: List[str], attachments: List[Dict[str, Any]], claims: Dict[str, Any], subject: str, message_id: str) -> Dict[str, Any]:
    magazine_recipients = [addr for addr in internal_recipients if webmail_is_magazines_address(addr)]
    if not magazine_recipients:
        return {"imported": 0, "items": [], "reason": "not_magazine_recipient"}
    sender_email = webmail_member_contact_email(claims) or str(claims.get("email") or "")
    imported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for idx, attachment in enumerate(attachments):
        filename = webmail_attachment_safe_name(attachment.get("filename") or f"magazine-{idx+1}.pdf")
        ctype = str(attachment.get("content_type") or "application/octet-stream").lower()
        try:
            payload = webmail_compose_attachment_payload(attachment)
        except Exception:
            skipped.append({"filename": filename, "reason": "invalid_attachment"})
            continue
        for pdf_name, pdf_payload in magazine_pdf_payloads_from_attachment(filename, ctype, payload):
            try:
                title = safe_header(subject or pdf_name.rsplit(".", 1)[0] or "Club magazine", 180)
                if len(attachments) > 1 and subject:
                    title = safe_header(f"{subject} - {pdf_name.rsplit('.', 1)[0]}", 180)
                entry = import_magazine_from_payload(title, pdf_name or f"magazine-{len(imported)+1}.pdf", pdf_payload, sender_email, f"{message_id}-{idx}-{len(imported)}", source="webmail")
                imported.append({"id": entry.get("id"), "title": entry.get("title"), "key": entry.get("key"), "filename": pdf_name})
            except Exception as exc:
                skipped.append({"filename": pdf_name or filename, "reason": str(exc)[:300]})
        if not any((item.get("filename") or "") == filename for item in imported) and not (filename.lower().endswith(".zip") or ctype in {"application/zip", "application/x-zip-compressed", "multipart/x-zip"} or filename.lower().endswith(".pdf") or ctype in {"application/pdf", "application/x-pdf"}):
            skipped.append({"filename": filename, "reason": "not_pdf_or_zip"})
    return {"imported": len(imported), "items": imported, "skipped": skipped, "reason": "ok" if imported else "no_imported_pdfs"}


def webmail_mark_internal_attachments_clean(attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mark in-app Webmail deliveries as trusted internal uploads.

    Messages delivered entirely inside the LROC Webmail system do not pass
    through SES receiving, so they never get SES virus verdict headers. They
    have already passed the compose attachment type/size checks and are stored
    by this Lambda, so keep them importable instead of leaving them stuck at
    pending_scan waiting for an inbound SES scan that will never happen.
    """
    out: List[Dict[str, Any]] = []
    for raw in attachments or []:
        if not isinstance(raw, dict):
            continue
        att = dict(raw)
        if not bool(att.get("skipped")):
            att["internal_trusted"] = True
            att["scan_status"] = "internal_clean"
            att["scan_provider"] = "internal_webmail"
            att["scan_reason"] = "internal_webmail_delivery"
            att["download_allowed"] = True
            att["import_allowed"] = True
            att["kind"] = webmail_attachment_kind_for_filename(att.get("filename"), att.get("content_type"))
            att["extension"] = webmail_attachment_ext(att.get("filename"))
        out.append(att)
    return out


def webmail_deliver_internal_message(mailbox: str, source_mailbox: str, role_name: str, subject: str, body_text: str, to: List[str], cc: List[str], bcc: List[str], attachments: List[Dict[str, Any]], sent_message_id: str, raw_key: str) -> Dict[str, Any]:
    inbox_id = clean_webmail_message_id(f"internal-{sent_message_id}-{mailbox}")
    now = utc_now_precise()
    item = {
        "mailbox": mailbox,
        "message_id": inbox_id,
        "folder": "inbox",
        "direction": "internal",
        "internal_delivery": True,
        "from": source_mailbox,
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "received_at": now,
        "created_at": now,
        "raw_s3_key": raw_key,
        "body_text": body_text,
        "body_html": webmail_branded_html(body_text, role_name),
        "attachments": webmail_mark_internal_attachments_clean(attachments),
        "spam_status": "internal",
        "spam_verdicts": {"virus": "internal", "spam": "internal"},
        "role_name": role_name,
        "read": False,
        "source_sent_message_id": sent_message_id,
    }
    webmail_index_message(item)
    return item


def webmail_send_route(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    mailbox = normalise_email_address(body.get("mailbox") or "")
    box = webmail_get_mailbox_for_claims(claims, mailbox, for_send=True)

    raw_to = webmail_parse_address_list(body.get("to") or "")
    raw_cc = webmail_parse_address_list(body.get("cc") or "")
    raw_bcc = webmail_parse_address_list(body.get("bcc") or "")

    internal_recipients = webmail_internal_recipient_mailboxes(raw_to + raw_cc + raw_bcc)
    internal_set = set(internal_recipients)
    article_recipients = webmail_internal_article_recipients(internal_recipients)
    magazine_recipients = webmail_internal_magazine_recipients(internal_recipients)
    article_only_internal = bool(article_recipients) and set(internal_recipients).issubset(set(article_recipients))
    magazine_only_internal = bool(magazine_recipients) and set(internal_recipients).issubset(set(magazine_recipients))

    # Internal LROC role/service mailbox delivery must not be treated like a
    # normal external/member send. In particular, do not apply member opt-out or
    # suppression filters to service addresses such as articles@lroc..., and do
    # not require SES outbound when every recipient is internal.
    external_raw_to = [email for email in raw_to if email not in internal_set]
    external_raw_cc = [email for email in raw_cc if email not in internal_set]
    external_raw_bcc = [email for email in raw_bcc if email not in internal_set]
    address_filter = webmail_filter_compose_address_lists(external_raw_to, external_raw_cc, external_raw_bcc)

    to: List[str] = []
    cc: List[str] = []
    bcc: List[str] = []
    for email in raw_to:
        email_n = normalise_email_address(email)
        if email_n in internal_set and email_n not in to:
            to.append(email_n)
    for email in raw_cc:
        email_n = normalise_email_address(email)
        if email_n in internal_set and email_n not in cc:
            cc.append(email_n)
    for email in raw_bcc:
        email_n = normalise_email_address(email)
        if email_n in internal_set and email_n not in bcc:
            bcc.append(email_n)

    for email in address_filter["to"]:
        if email not in to:
            to.append(email)
    for email in address_filter["cc"]:
        if email not in cc:
            cc.append(email)
    for email in address_filter["bcc"]:
        if email not in bcc:
            bcc.append(email)

    group_data = webmail_compose_group_recipients(body.get("recipient_groups") if isinstance(body.get("recipient_groups"), list) else [])
    group_emails = [normalise_email_address(item.get("email") or "") for item in group_data.get("recipients") or []]
    for email in group_emails:
        if valid_email_address(email) and email not in to and email not in cc and email not in bcc:
            bcc.append(email)

    skipped_recipients = (address_filter.get("skipped") or []) + (group_data.get("skipped") or [])
    if not to and not cc and not bcc:
        raise ValueError("At least one sendable recipient is required. Opted-out or suppressed recipients were skipped.")

    raw_attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []
    attachments = webmail_prepare_compose_attachments(raw_attachments, claims)

    subject = safe_header(body.get("subject") or "", 250)
    if not subject and article_recipients and attachments:
        subject = webmail_attachment_safe_name(attachments[0].get("filename") or "Submitted article").rsplit(".", 1)[0][:120] or "Submitted article"
    if not subject and magazine_recipients and attachments:
        subject = webmail_attachment_safe_name(attachments[0].get("filename") or "Club magazine").rsplit(".", 1)[0][:120] or "Club magazine"
    if not subject:
        raise ValueError("Subject is required.")
    body_text = str(body.get("body") or "").strip()
    if not body_text and article_recipients:
        sender_name = str(claims.get("name") or claims.get("email") or "LROC member")
        body_text = f"Submitted from LROC Webmail by {sender_name}."
    if not body_text and magazine_recipients:
        sender_name = str(claims.get("name") or claims.get("email") or "LROC member")
        body_text = f"Magazine uploaded from LROC Webmail by {sender_name}."
    if not body_text:
        raise ValueError("Message body is required.")

    role_name = str(box.get("role_name") or box.get("label") or "LROC").strip()
    external_destinations = sorted(set([email for email in to + cc + bcc if email not in internal_set]))
    message_id = clean_webmail_message_id(uuid.uuid4().hex)

    stored_attachments: List[Dict[str, Any]] = []
    for idx, attachment in enumerate(attachments):
        filename = webmail_attachment_safe_name(attachment.get("filename") or f"attachment-{idx+1}")
        payload = webmail_compose_attachment_payload(attachment)
        key = webmail_attachment_key(message_id, idx, filename)
        ctype = str(attachment.get("content_type") or "application/octet-stream")
        s3.put_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=key, Body=payload, ContentType=ctype, ServerSideEncryption="AES256")
        stored_attachments.append({
            "index": idx,
            "filename": filename,
            "content_type": ctype,
            "size": len(payload),
            "key": key,
            "internal_trusted": True,
            "scan_status": "internal_clean",
            "scan_provider": "internal_webmail",
            "scan_reason": "internal_webmail_upload",
            "download_allowed": True,
            "import_allowed": True,
            "kind": webmail_attachment_kind_for_filename(filename, ctype),
            "extension": webmail_attachment_ext(filename),
        })
        upload_key = str(attachment.get("upload_key") or "")
        if upload_key and webmail_is_compose_upload_key(upload_key, str(claims.get("sub") or "")):
            try:
                s3.delete_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=upload_key)
            except Exception:
                pass

    result: Dict[str, Any] = {}
    raw_key = ""
    raw = b""
    if external_destinations:
        visible_to = to or ([mailbox] if bcc and not cc else to)
        raw = webmail_build_raw_email(mailbox, role_name, visible_to, cc, subject, body_text, attachments, role_name)
        if not ses_email_available():
            raise RuntimeError("SES sending is not configured.")
        kwargs = {
            "FromEmailAddress": mailbox,
            "Destination": {"ToAddresses": external_destinations},
            "Content": {"Raw": {"Data": raw}},
        }
        if SES_CONFIGURATION_SET:
            kwargs["ConfigurationSetName"] = SES_CONFIGURATION_SET
        result = sesv2.send_email(**kwargs)
        message_id = clean_webmail_message_id(result.get("MessageId") or message_id)
        raw_key = webmail_sent_key(message_id)
        s3.put_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=raw_key, Body=raw, ContentType="message/rfc822", ServerSideEncryption="AES256")
    else:
        # Internal-only delivery is an in-site upload/delivery workflow, not an
        # SMTP email loop. This avoids SES/API limits for article-style uploads
        # while still keeping a sent record and inbox entry for the service
        # mailbox.
        raw_key = webmail_sent_key(message_id)
        internal_note = json.dumps({
            "message_id": message_id,
            "from": mailbox,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "body_text": body_text,
            "attachment_count": len(stored_attachments),
            "delivery": "internal",
        }, ensure_ascii=False).encode("utf-8")
        s3.put_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=raw_key, Body=internal_note, ContentType="application/json", ServerSideEncryption="AES256")

    internal_delivery_items: List[Dict[str, Any]] = []
    for internal_mailbox in internal_recipients:
        try:
            delivered = webmail_deliver_internal_message(internal_mailbox, mailbox, role_name, subject, body_text, to, cc, bcc, stored_attachments, message_id, raw_key)
            internal_delivery_items.append(webmail_message_summary(delivered))
        except Exception:
            pass

    article_import = webmail_import_compose_articles(internal_recipients, attachments, claims, subject, body_text, message_id)
    magazine_import = webmail_import_compose_magazines(internal_recipients, attachments, claims, subject, message_id)
    member_copy_email = webmail_member_contact_email(claims)
    member_copy_result = webmail_send_member_copy_email(member_copy_email, mailbox, role_name, subject, body_text, to, cc, bcc, len(attachments)) if member_copy_email and ses_email_available() and external_destinations else {"sent": False, "skipped": True, "reason": "internal delivery" if not external_destinations else "no member email or SES unavailable"}

    item = {
        "mailbox": mailbox,
        "message_id": message_id,
        "folder": "sent",
        "direction": "outbound" if external_destinations else "internal",
        "from": mailbox,
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "recipient_groups": group_data.get("groups") or [],
        "skipped_recipients": skipped_recipients,
        "member_copy_email": member_copy_email,
        "member_copy_result": member_copy_result,
        "subject": subject,
        "sent_at": utc_now_precise(),
        "created_at": utc_now_precise(),
        "raw_s3_key": raw_key,
        "body_text": body_text,
        "body_html": webmail_branded_html(body_text, role_name),
        "attachments": stored_attachments,
        "spam_status": "outbound" if external_destinations else "internal",
        "spam_verdicts": {"virus": "internal", "spam": "internal"} if not external_destinations else {},
        "role_name": role_name,
        "read": True,
        "ses_message_id": result.get("MessageId") or "",
        "internal_recipients": internal_recipients,
        "external_recipients": external_destinations,
        "internal_delivery_items": internal_delivery_items,
        "article_import": article_import,
        "magazine_import": magazine_import,
    }
    webmail_index_message(item)
    webmail_remember_external_contacts(external_destinations, claims, mailbox)
    return response(200, {
        "message": f"Email sent from {mailbox}." if external_destinations else f"Message delivered internally from {mailbox}.",
        "item": webmail_message_summary(item),
        "member_copy_email": member_copy_email,
        "member_copy": member_copy_result,
        "group_recipient_count": len(group_emails),
        "skipped_recipient_count": len(skipped_recipients),
        "skipped_recipients": skipped_recipients[:25],
        "internal_recipient_count": len(internal_recipients),
        "external_recipient_count": len(external_destinations),
        "article_import": article_import,
        "magazine_import": magazine_import,
    })

def webmail_spam_purge_scan(triggered_by: str = "scheduler") -> Dict[str, Any]:
    require_webmail()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WEBMAIL_SPAM_RETENTION_DAYS)).date().isoformat()
    deleted = 0
    scanned = 0
    resp = ddb.scan(
        TableName=EMAIL_STATE_TABLE,
        FilterExpression="item_type = :type AND folder = :folder",
        ExpressionAttributeValues={":type": {"S": "webmail_message"}, ":folder": {"S": "quarantine"}},
    )
    for raw in resp.get("Items") or []:
        item = item_to_python(raw)
        scanned += 1
        quarantine_until = str(item.get("quarantine_until") or "")
        received_date = str(item.get("received_at") or item.get("created_at") or "")[:10]
        due = (quarantine_until and quarantine_until <= datetime.now(timezone.utc).date().isoformat()) or (received_date and received_date <= cutoff)
        if not due:
            continue
        for key in [str(item.get("raw_s3_key") or "")] + [str(att.get("key") or "") for att in (item.get("attachments") if isinstance(item.get("attachments"), list) else [])]:
            if key:
                try:
                    s3.delete_object(Bucket=WEBMAIL_MAIL_BUCKET, Key=key)
                except Exception:
                    pass
        ddb.delete_item(TableName=EMAIL_STATE_TABLE, Key={"pk": {"S": str(item.get("pk"))}, "sk": {"S": str(item.get("sk"))}})
        ddb.delete_item(TableName=EMAIL_STATE_TABLE, Key={"pk": {"S": f"WEBMAIL#MSG#{item.get('message_id')}"}, "sk": {"S": f"MAILBOX#{item.get('mailbox')}"}})
        deleted += 1
    return {"message": "Webmail quarantine purge complete.", "triggered_by": triggered_by, "scanned": scanned, "deleted": deleted, "retention_days": WEBMAIL_SPAM_RETENTION_DAYS}


def human_file_size(size: Any) -> str:
    try:
        n = float(size or 0)
    except Exception:
        n = 0
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    while n >= 1024 and idx < len(units) - 1:
        n /= 1024
        idx += 1
    return f"{n:.1f} {units[idx]}" if idx else f"{int(n)} {units[idx]}"


def member_file_safe_name(name: Any, fallback: str = "file") -> str:
    text = os.path.basename(str(name or fallback).strip())
    text = re.sub(r"[^A-Za-z0-9_.() -]+", "_", text)
    return (text or fallback)[:180]


def member_file_description_key(key: str) -> str:
    return f"{key}.metadata.json"


def list_regular_member_files() -> List[Dict[str, Any]]:
    prefix = PREFIX.strip().strip("/") + "/"
    items: List[Dict[str, Any]] = []
    token = None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = str(obj.get("Key") or "")
            if not key or key.endswith("/") or key.endswith(".metadata.json") or key.startswith(MEETING_MINUTES_PREFIX):
                continue
            filename = os.path.basename(key)
            description = ""
            try:
                meta_key = member_file_description_key(key)
                meta_obj = s3.get_object(Bucket=BUCKET, Key=meta_key)
                meta = json.loads(meta_obj["Body"].read().decode("utf-8"))
                description = str(meta.get("description") or "")
            except Exception:
                description = ""
            last_modified = obj.get("LastModified")
            items.append({
                "key": key,
                "filename": filename,
                "last_modified": last_modified.isoformat() if hasattr(last_modified, "isoformat") else str(last_modified or ""),
                "size": int(obj.get("Size") or 0),
                "size_human": human_file_size(obj.get("Size") or 0),
                "description": description,
                "document_type": "member_file",
                "category": "Shared member files",
            })
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return items


def list_meeting_minutes_file_items() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for mt, label in MEETING_AGENDA_LABELS.items():
        for minutes in meeting_agenda_list_minutes(mt, 100):
            key = str(minutes.get("pdf_key") or "")
            if not key:
                continue
            size = 0
            last_modified = str(minutes.get("finalised_at") or "")
            try:
                head = s3.head_object(Bucket=BUCKET, Key=key)
                size = int(head.get("ContentLength") or 0)
                lm = head.get("LastModified")
                if hasattr(lm, "isoformat"):
                    last_modified = lm.isoformat()
            except Exception:
                pass
            filename = str(minutes.get("pdf_filename") or os.path.basename(key) or f"{mt}-minutes.pdf")
            items.append({
                "key": f"MEETING_MINUTES::{mt}::{minutes.get('minutes_id')}",
                "filename": filename,
                "last_modified": last_modified,
                "size": size,
                "size_human": human_file_size(size) if size else "",
                "description": f"{label} minutes - {minutes.get('scheduled_at') or minutes.get('finalised_at') or ''}",
                "document_type": "meeting_minutes",
                "meeting_type": mt,
                "meeting_type_label": label,
                "minutes_id": str(minutes.get("minutes_id") or ""),
                "category": f"{label} Minutes",
                "s3_prefix": str(minutes.get("s3_prefix") or "/".join(key.split("/")[:-1]) + "/"),
            })
    items.sort(key=lambda x: str(x.get("last_modified") or ""), reverse=True)
    return items


def list_files() -> Dict[str, Any]:
    items = list_meeting_minutes_file_items() + list_regular_member_files()
    categories = [
        {"id": "committee", "label": "Committee Meeting Minutes", "document_type": "meeting_minutes", "meeting_type": "committee"},
        {"id": "general", "label": "General Meeting Minutes", "document_type": "meeting_minutes", "meeting_type": "general"},
        {"id": "agm", "label": "Annual General Meeting Minutes", "document_type": "meeting_minutes", "meeting_type": "agm"},
        {"id": "shared", "label": "Shared member files", "document_type": "member_file"},
    ]
    return response(200, {"items": items, "categories": categories})


def create_upload_url(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    filename = member_file_safe_name(body.get("filename") or "file")
    content_type = str(body.get("content_type") or "application/octet-stream").strip()[:120] or "application/octet-stream"
    description = str(body.get("description") or "").strip()[:500]
    owner = re.sub(r"[^A-Za-z0-9_.=-]+", "-", str(claims.get("sub") or claims.get("email") or "member"))[:80] or "member"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    key = f"{PREFIX.strip().strip('/')}/{owner}/{stamp}-{secrets.token_hex(6)}-{filename}"
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type, "ServerSideEncryption": "AES256"},
        ExpiresIn=UPLOAD_EXPIRY,
    )
    if description:
        meta = {"description": description, "uploaded_by": str(claims.get("email") or claims.get("sub") or ""), "created_at": utc_now_precise()}
        s3.put_object(Bucket=BUCKET, Key=member_file_description_key(key), Body=json.dumps(meta).encode("utf-8"), ContentType="application/json", ServerSideEncryption="AES256")
    return response(200, {"upload_url": upload_url, "key": key, "required_headers": {"Content-Type": content_type, "x-amz-server-side-encryption": "AES256"}})


def resolve_meeting_minutes_download_key(virtual_key: str) -> tuple[str, str]:
    parts = str(virtual_key or "").split("::")
    if len(parts) != 3 or parts[0] != "MEETING_MINUTES":
        raise ValueError("Invalid meeting minutes reference.")
    mt = normalise_meeting_agenda_type(parts[1])
    minutes_id = meeting_agenda_safe_id(parts[2])
    for item in meeting_agenda_list_minutes(mt, 100):
        if str(item.get("minutes_id") or "") == minutes_id:
            key = str(item.get("pdf_key") or "")
            if not key.startswith(MEETING_MINUTES_PREFIX):
                raise PermissionError("Invalid minutes file key.")
            return key, str(item.get("pdf_filename") or os.path.basename(key) or f"{mt}-minutes.pdf")
    raise ValueError("Minutes record not found.")


def create_download_url(event: Dict[str, Any]) -> Dict[str, Any]:
    body = parse_body(event)
    key = str(body.get("key") or "").strip()
    filename = os.path.basename(key)
    if key.startswith("MEETING_MINUTES::"):
        key, filename = resolve_meeting_minutes_download_key(key)
    else:
        prefix = PREFIX.strip().strip("/") + "/"
        if not key.startswith(prefix) or key.endswith(".metadata.json") or key.startswith(MEETING_MINUTES_PREFIX):
            raise PermissionError("Invalid member file key.")
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key, "ResponseContentDisposition": f'attachment; filename="{filename}"'},
        ExpiresIn=DOWNLOAD_EXPIRY,
    )
    return response(200, {"url": url})


def delete_file(event: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    if not is_admin(claims):
        raise PermissionError("Only administrators can delete shared member files.")
    raw_path = str((event.get("rawPath") or "").split("/member/files/", 1)[-1])
    key = unquote(raw_path)
    prefix = PREFIX.strip().strip("/") + "/"
    if not key.startswith(prefix) or key.startswith(MEETING_MINUTES_PREFIX):
        raise PermissionError("Invalid member file key.")
    s3.delete_object(Bucket=BUCKET, Key=key)
    try:
        s3.delete_object(Bucket=BUCKET, Key=member_file_description_key(key))
    except Exception:
        pass
    return response(200, {"message": "File deleted."})


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        if event.get("Records") and any(str((record.get("EventSource") or record.get("eventSource") or "")).lower() == "aws:sns" for record in event.get("Records") or []):
            return handle_sns_event(event)
        if event.get("Records") and any(str((record.get("eventSource") or record.get("EventSource") or "")).lower() == "aws:ses" for record in event.get("Records") or []):
            return handle_ses_inbound_event(event)
        if event.get("action") == "event_reminders":
            return response(200, run_event_reminder_scan(triggered_by="scheduler"))
        if event.get("action") == "vehicle_registration_reminders":
            return response(200, run_vehicle_registration_reminder_scan(triggered_by="scheduler"))
        if event.get("action") == "webmail_spam_purge":
            return response(200, webmail_spam_purge_scan(triggered_by="scheduler"))
        if event.get("action") == "webmail_backfill_submissions":
            return response(200, webmail_backfill_submissions_event(event))
        route_key = event.get("routeKey", "")
        if route_key == "GET /articles":
            return list_public_articles()
        if route_key == "GET /magazines":
            return list_public_magazines()
        if route_key == "POST /member/magazines/upload-url":
            return create_magazine_upload_url(event, claims)
        if route_key == "POST /member/magazines/publish":
            return publish_magazine_upload(event, claims)
        if route_key == "GET /events":
            return public_events_route(event)
        if route_key == "POST /guest/chime/request":
            return guest_chime_request_route(event)
        if route_key == "GET /guest/chime/status" or route_key == "POST /guest/chime/status":
            return guest_chime_status_route(event)
        if route_key == "POST /guest/chime/join":
            return guest_chime_join_route(event)
        claims = ensure_member(event)
        if route_key == "GET /member/files":
            return list_files()
        if route_key == "POST /member/files/upload-url":
            return create_upload_url(event, claims)
        if route_key == "POST /member/files/download-url":
            return create_download_url(event)
        if route_key == "DELETE /member/files/{proxy+}" or route_key.startswith("DELETE /member/files/"):
            return delete_file(event, claims)
        if route_key == "POST /admin/content/publish":
            return publish_site_content(event, claims)
        if route_key == "GET /admin/expo/content" or route_key == "POST /admin/expo/content":
            return admin_expo_content_route(event, claims)
        if route_key == "GET /member/profile-metadata":
            return get_profile_metadata(event, claims)
        if route_key == "GET /member/vehicle-options":
            return member_vehicle_options_route(event, claims)
        if route_key == "GET /member/vehicles":
            return list_member_vehicles_route(event, claims)
        if route_key == "GET /member/events":
            return list_member_events_route(event, claims)
        if route_key == "POST /member/events/register":
            return register_member_event_route(event, claims)
        if route_key == "POST /member/events/cancel":
            return cancel_member_event_route(event, claims)
        if route_key == "GET /member/events/attendees" or route_key == "POST /member/events/attendees":
            return member_event_attendees_route(event, claims)
        if route_key == "POST /member/vehicles":
            return save_member_vehicle_route(event, claims)
        if route_key == "GET /member/historic-registration":
            return historic_registration_state_route(event, claims)
        if route_key == "POST /member/historic-registration/upload-url":
            return create_historic_registration_upload_url(event, claims)
        if route_key == "POST /member/historic-registration/submit":
            return historic_registration_submit_route(event, claims)
        if route_key == "POST /member/historic-registration/process":
            return historic_registration_process_route(event, claims)
        if route_key == "POST /member/historic-registration/vehicle-form/upload-url":
            return historic_registration_vehicle_form_upload_url_route(event, claims)
        if route_key == "POST /member/historic-registration/vehicle-record":
            return historic_registration_vehicle_record_route(event, claims)
        if route_key == "POST /member/vehicles/historic-rego":
            return member_vehicle_historic_rego_route(event, claims)
        if route_key == "POST /member/vehicles/registration-response":
            return member_vehicle_registration_response_route(event, claims)
        if route_key == "POST /member/vehicles/delete":
            return delete_member_vehicle_route(event, claims)
        if route_key == "GET /member/vehicle-maintenance" or route_key == "POST /member/vehicle-maintenance":
            return vehicle_maintenance_route(event, claims)
        if route_key == "POST /member/vehicle-maintenance/delete":
            return vehicle_maintenance_delete_route(event, claims)
        if route_key == "POST /member/vehicle-help/suggest":
            return member_vehicle_help_suggest_route(event, claims)
        if route_key == "GET /member/session-check":
            return member_session_check_route(event, claims)
        if route_key == "GET /member/meeting-agenda/current":
            return meeting_agenda_current_route(event, claims)
        if route_key == "POST /member/meeting-agenda/meeting":
            return meeting_agenda_save_meeting_route(event, claims)
        if route_key == "POST /member/meeting-agenda/items":
            return meeting_agenda_save_item_route(event, claims)
        if route_key == "POST /member/meeting-agenda/items/delete":
            return meeting_agenda_delete_item_route(event, claims)
        if route_key == "POST /member/meeting-agenda/suggestions":
            return meeting_agenda_create_suggestion_route(event, claims)
        if route_key == "GET /member/meeting-agenda/suggestions":
            return meeting_agenda_suggestions_route(event, claims)
        if route_key == "POST /member/meeting-agenda/suggestions/add":
            return meeting_agenda_add_suggestion_route(event, claims)
        if route_key == "POST /member/meeting-agenda/suggestions/dismiss":
            return meeting_agenda_dismiss_suggestion_route(event, claims)
        if route_key == "POST /member/meeting-agenda/finalise":
            return meeting_agenda_finalise_route(event, claims)
        if route_key == "POST /member/meeting-agenda/preview-pdf":
            return meeting_agenda_preview_pdf_route(event, claims)
        if route_key == "GET /member/meeting-agenda/minutes":
            return meeting_agenda_minutes_route(event, claims)
        if route_key == "POST /member/meeting-agenda/minutes/download-url":
            return meeting_agenda_minutes_download_route(event, claims)
        if route_key == "GET /member/chime/status":
            return chime_status_route(event, claims)
        if route_key == "POST /member/chime/launch":
            return launch_chime_meeting_route(event, claims)
        if route_key == "POST /member/chime/mode":
            return chime_mode_route(event, claims)
        if route_key == "POST /member/chime/join":
            return join_chime_meeting_route(event, claims)
        if route_key == "POST /member/chime/end":
            return end_chime_meeting_route(event, claims)
        if route_key == "GET /member/chime/attendance" or route_key == "POST /member/chime/attendance":
            return chime_attendance_route(event, claims)
        if route_key == "GET /member/chime/guests" or route_key == "POST /member/chime/guests":
            return chime_guest_lobby_route(event, claims)
        if route_key == "GET /member/chime/chat" or route_key == "POST /member/chime/chat":
            return chime_chat_route(event, claims)
        if route_key == "GET /member/chime/control" or route_key == "POST /member/chime/control":
            return chime_control_route(event, claims)
        if route_key == "GET /member/chime/agenda" or route_key == "POST /member/chime/agenda":
            return chime_agenda_route(event, claims)
        if route_key == "GET /member/chime/vote" or route_key == "POST /member/chime/vote":
            return chime_vote_route(event, claims)
        if route_key == "GET /member/chime/history":
            return chime_history_route(event, claims)
        if route_key == "GET /member/chat/rooms":
            return list_chat_rooms_route(event, claims)
        if route_key == "POST /member/push/subscribe":
            return subscribe_push_route(event, claims)
        if route_key == "POST /member/push/unsubscribe":
            return unsubscribe_push_route(event, claims)
        if route_key == "POST /member/chat/rooms":
            return create_chat_room_route(event, claims)
        if route_key == "GET /member/chat/rooms/{room_id}/messages":
            return get_chat_room_messages_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/messages":
            return post_chat_message_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/attachments/upload-url":
            return create_chat_attachment_upload_url_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/attachments/complete":
            return complete_chat_attachment_upload_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/attachments/download-url":
            return create_chat_attachment_download_url_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/join":
            return join_chat_room_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/leave":
            return leave_chat_room_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/notifications/mute":
            return mute_chat_notifications_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/notifications/unmute":
            return unmute_chat_notifications_route(event, claims)
        if route_key == "POST /member/chat/rooms/{room_id}/close":
            return close_chat_room_route(event, claims)
        if route_key == "GET /member/webmail/mailboxes":
            return webmail_mailboxes_route(event, claims)
        if route_key == "GET /member/webmail/contacts":
            return webmail_contact_suggestions_route(event, claims)
        if route_key == "GET /member/webmail/messages":
            return webmail_list_messages_route(event, claims)
        if route_key == "GET /member/webmail/messages/{message_id}" or route_key.startswith("GET /member/webmail/messages/"):
            return webmail_read_message_route(event, claims)
        if route_key == "POST /member/webmail/send":
            return webmail_send_route(event, claims)
        if route_key == "POST /member/webmail/archive":
            return webmail_archive_route(event, claims)
        if route_key == "POST /member/webmail/attachment-url":
            return webmail_attachment_url_route(event, claims)
        if route_key == "POST /member/webmail/attachments/upload-url":
            return webmail_create_attachment_upload_url_route(event, claims)
        if route_key == "POST /member/profile-preferences":
            return update_profile_preferences(event, claims)
        if route_key == "GET /admin/member-metadata":
            return list_admin_member_metadata(event, claims)
        if route_key == "GET /admin/members/count":
            return count_member_metadata_records(event, claims)
        if route_key == "POST /admin/member-metadata":
            return update_admin_member_metadata(event, claims)
        if route_key == "POST /admin/members/create":
            return create_admin_member(event, claims)
        if route_key == "POST /admin/members/resend-invite":
            return resend_admin_member_invite(event, claims)
        if route_key == "POST /admin/members/import-preview":
            return member_import_preview(event, claims)
        if route_key == "POST /admin/members/import-commit":
            return member_import_commit(event, claims)
        if route_key == "GET /admin/members/import-history":
            return list_member_import_history(event, claims)
        if route_key == "POST /admin/members/import-rollback":
            return rollback_uninvited_imported_members(event, claims)
        if route_key == "POST /admin/members/disable":
            return disable_admin_member(event, claims)
        if route_key == "POST /admin/members/restore":
            return restore_admin_member(event, claims)
        if route_key == "POST /admin/email/test":
            return send_admin_test_email(event, claims)
        if route_key == "POST /admin/email/audience":
            return admin_email_audience_route(event, claims)
        if route_key == "GET /admin/email/positions":
            return admin_email_positions_route(event, claims)
        if route_key == "GET /admin/positions":
            return list_positions_route(event, claims)
        if route_key == "POST /admin/positions":
            return save_position_route(event, claims)
        if route_key == "POST /admin/positions/delete":
            return delete_position_route(event, claims)
        if route_key == "GET /admin/landrover-parts":
            return admin_landrover_parts_route(event, claims)
        if route_key == "POST /admin/landrover-parts":
            return save_admin_landrover_part_route(event, claims)
        if route_key == "POST /admin/landrover-parts/delete":
            return delete_admin_landrover_part_route(event, claims)
        if route_key == "GET /admin/vehicle-options":
            return admin_vehicle_options_route(event, claims)
        if route_key == "POST /admin/vehicle-options":
            return save_admin_vehicle_options_route(event, claims)
        if route_key == "GET /admin/event-options":
            return admin_event_data_route(event, claims)
        if route_key == "POST /admin/event-options":
            return save_admin_event_data_route(event, claims)
        if route_key == "GET /admin/events":
            return admin_events_route(event, claims)
        if route_key == "POST /admin/events":
            return save_admin_event_route(event, claims)
        if route_key == "POST /admin/events/short-descriptions":
            return save_admin_event_short_descriptions_route(event, claims)
        if route_key == "POST /admin/events/delete":
            return delete_admin_event_route(event, claims)
        if route_key == "POST /admin/events/image-upload-url":
            return create_event_image_upload_url(event, claims)
        if route_key == "POST /admin/events/seed-meetings":
            return seed_lroc_meetings_route(event, claims)
        if route_key == "POST /admin/maps/geocode":
            return admin_geocode_route(event, claims)
        if route_key == "POST /admin/member-roles":
            return update_admin_member_roles(event, claims)
        if route_key == "POST /admin/email/send-test":
            return admin_email_send_test_route(event, claims)
        if route_key == "POST /admin/email/send-bulk":
            return admin_email_send_bulk_route(event, claims)
        if route_key == "POST /admin/email/suppress":
            return admin_email_suppress_route(event, claims)
        if route_key == "POST /admin/email/clear-suppression":
            return admin_email_clear_suppression_route(event, claims)
        if route_key == "POST /admin/events/reminders/run":
            return run_event_reminders_route(event, claims)
        if route_key == "POST /admin/vehicles/registration-reminders/run":
            return run_vehicle_registration_reminders_route(event, claims)
        if route_key == "POST /admin/webmail/backfill-submissions":
            return admin_webmail_backfill_submissions_route(event, claims)
        if route_key == "POST /admin/webmail/messages/delete":
            return admin_webmail_delete_message_route(event, claims)
        if route_key == "GET /member/articles":
            return list_member_articles(event, claims)
        if route_key == "POST /member/articles/upload-url":
            return create_article_upload_url(event, claims)
        if route_key == "POST /member/articles/publish":
            return publish_article(event, claims)
        if route_key == "POST /member/articles/download":
            return article_download_url_route(event, claims)
        if route_key == "POST /admin/articles/delete":
            return delete_article(event, claims)
        if route_key == "POST /admin/events/info-upload-url":
            return create_event_info_upload_url(event, claims)
        if route_key == "POST /admin/events/info-delete":
            return delete_event_info(event, claims)
        return response(404, {"message": f"Unsupported route: {route_key}"})
    except PermissionError as exc:
        return response(403, {"message": str(exc)})
    except ValueError as exc:
        return response(400, {"message": str(exc)})
    except Exception as exc:
        return response(500, {"message": str(exc)})

# v3.1.9 deploy marker: PDF preview renderer fix for source document camera-ready pages.
