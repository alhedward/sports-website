import base64
import hashlib
import email
from email import policy
import io
import json
import os
import re
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from html import escape as html_escape
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

DDB_TABLE = os.environ.get("MAGAZINE_TABLE", "")
EMAIL_STATE_TABLE = os.environ.get("EMAIL_STATE_TABLE", "")
MEMBER_METADATA_TABLE = os.environ.get("MEMBER_METADATA_TABLE", "")
ASSETS_BUCKET = os.environ.get("MAGAZINE_ASSETS_BUCKET", "")
ASSETS_PREFIX = os.environ.get("MAGAZINE_ASSETS_PREFIX", "magazine/").strip("/") + "/"
UPLOAD_EXPIRY_SECONDS = int(os.environ.get("MAGAZINE_UPLOAD_EXPIRY_SECONDS", "3600"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAGAZINE_MAX_UPLOAD_BYTES", str(1024 * 1024 * 1024)))
ALLOWED_MIME_PREFIXES = tuple(x.strip() for x in os.environ.get("MAGAZINE_ALLOWED_MIME_PREFIXES", "image/,application/pdf,application/zip,application/json,text/,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/rtf,message/rfc822").split(",") if x.strip())
ALLOWED_GROUPS = {x.strip() for x in os.environ.get("MAGAZINE_ALLOWED_GROUPS", "admins,webmaster,committee").split(",") if x.strip()}
MAGAZINE_ADVERT_ASSET_TYPES = {"advertisement", "advert", "advert_pdf", "vendor_pdf", "back_cover_ad", "sponsor_ad"}
MAGAZINE_IMAGE_ASSET_TYPES = {"image", "article_image", "trip_report_image", "cover_image", "logo", "advert_source_image"}
MAGAZINE_FINISHED_PDF_TYPES = {"finished_pdf", "source_pdf", "external_pdf", "supplement_pdf"}

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")
table = ddb.Table(DDB_TABLE) if DDB_TABLE else None
member_metadata_table = ddb.Table(MEMBER_METADATA_TABLE) if MEMBER_METADATA_TABLE else None
email_state_table = ddb.Table(EMAIL_STATE_TABLE) if EMAIL_STATE_TABLE else None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def response(status: int, body: Any = None) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "authorization,content-type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body if body is not None else {}, default=json_default),
    }


def parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except Exception:
        raise ValueError("Request body must be valid JSON.")
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def claims(event: Dict[str, Any]) -> Dict[str, Any]:
    return event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {}) or {}


def claim_groups(claims_: Dict[str, Any]) -> set:
    raw = claims_.get("cognito:groups") or claims_.get("groups") or ""
    if isinstance(raw, str):
        return {x.strip() for x in raw.replace("[", "").replace("]", "").replace('"', "").split(",") if x.strip()}
    if isinstance(raw, list):
        return {str(x).strip() for x in raw if str(x).strip()}
    return set()


def user_id(claims_: Dict[str, Any]) -> str:
    return str(claims_.get("email") or claims_.get("username") or claims_.get("sub") or "unknown")[:256]


def metadata_key(sub: str) -> Dict[str, str]:
    return {"pk": f"MEMBER#{sub}", "sk": "PROFILE"}


def text_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            tokens.update(text_tokens(*value))
            continue
        text = str(value or "").strip().lower()
        if not text:
            continue
        for part in text.replace("_", " ").replace("-", " ").split():
            if part:
                tokens.add(part)
        for part in text.replace(";", ",").replace("|", ",").split(","):
            part = part.strip()
            if part:
                tokens.add(part)
    return tokens


def user_metadata_for_claims(c: Dict[str, Any]) -> Dict[str, Any]:
    if member_metadata_table is None:
        return {}
    sub = str(c.get("sub") or "").strip()
    if not sub:
        return {}
    try:
        return member_metadata_table.get_item(Key=metadata_key(sub), ConsistentRead=True).get("Item") or {}
    except Exception as exc:
        print(f"Magazine API could not load member metadata for auth: {exc}")
        return {}


def is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y", "on"}


def is_editor_claim_or_metadata(c: Dict[str, Any], meta: Dict[str, Any] | None = None) -> bool:
    groups = claim_groups(c)
    if groups.intersection(ALLOWED_GROUPS):
        return True
    meta = meta or {}
    for source in (c, meta):
        for key in ("can_manage_magazine", "can_edit_magazine", "can_review_magazine_submissions", "can_publish_magazine"):
            if is_truthy(source.get(key)):
                return True
    tokens = text_tokens(
        groups,
        meta.get("system_roles"),
        meta.get("assigned_role_ids"),
        meta.get("assigned_role_names"),
        meta.get("committee_position_id"),
        meta.get("official_position_id"),
        meta.get("official_position_name"),
        meta.get("club_roles"),
        meta.get("club_roles_raw"),
    )
    allowed_tokens = {x.strip().lower() for x in ALLOWED_GROUPS if x.strip()} | {
        "admin", "admins", "siteadmin", "site", "committee", "webmaster",
        "president", "vice", "secretary", "treasurer", "editor", "magazine",
    }
    if tokens.intersection(allowed_tokens):
        return True
    # Two-word role labels are tokenised above, so explicitly catch common phrases.
    joined = " ".join(sorted(tokens))
    return any(phrase in joined for phrase in ("site admin", "magazine editor", "magazine admin"))


def require_editor(event: Dict[str, Any]) -> Dict[str, Any]:
    c = claims(event)
    meta = user_metadata_for_claims(c)
    if is_editor_claim_or_metadata(c, meta):
        return c
    raise PermissionError("Magazine production is restricted to authorised editors.")


def ensure_table() -> None:
    if table is None:
        raise RuntimeError("MAGAZINE_TABLE is not configured.")


def issue_pk(issue_id: str) -> str:
    return f"ISSUE#{issue_id}"


def asset_pk(asset_id: str) -> str:
    return f"ASSET#{asset_id}"


def content_pk(content_id: str) -> str:
    return f"CONTENT#{content_id}"


def inbound_pk(item_id: str) -> str:
    return f"INBOUND#{item_id}"


def submission_pk(kind: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(kind or "magazinecontent")).strip("-") or "magazinecontent"
    return f"WEBMAIL#SUBMISSIONS#{safe}"


def safe_filename(value: Any, fallback: str = "submission") -> str:
    text = str(value or fallback).replace("\\", "_").replace("/", "_").strip()
    out = "".join(ch if ch.isalnum() or ch in "_.() -" else "_" for ch in text)
    return (out or fallback)[:160]


def simple_slug(value: Any, fallback: str = "item") -> str:
    text = str(value or fallback).strip().lower()
    out = []
    last_dash = False
    for ch in text:
        if ch.isalnum():
            out.append(ch); last_dash = False
        elif not last_dash:
            out.append("-"); last_dash = True
    return "".join(out).strip("-")[:90] or fallback


def extension_for_filename(filename: Any) -> str:
    name = str(filename or "").lower()
    return name.rsplit(".", 1)[1] if "." in name else ""


def infer_asset_type_from_submission(kind: str, filename: str, content_type: str) -> str:
    ext = extension_for_filename(filename)
    if kind == "vendorcontent":
        return "vendor_pdf" if ext == "pdf" else "advertisement"
    if kind == "tripreports" and str(content_type or "").startswith("image/"):
        return "trip_report_image"
    if ext == "pdf":
        return "source_pdf"
    if str(content_type or "").startswith("image/"):
        return "article_image"
    return "production_file"


def infer_material_type(asset_type: str, filename: str = "", content_type: str = "", explicit: Any = "") -> str:
    explicit_text = clean_text(explicit, 80)
    if explicit_text:
        return explicit_text
    asset_type = clean_text(asset_type, 80).lower()
    ext = extension_for_filename(filename)
    mime = str(content_type or "").lower()
    if asset_type in MAGAZINE_ADVERT_ASSET_TYPES:
        return "advert"
    if asset_type in MAGAZINE_IMAGE_ASSET_TYPES or mime.startswith("image/"):
        return "image"
    if asset_type in MAGAZINE_FINISHED_PDF_TYPES or ext == "pdf" or mime == "application/pdf":
        return "finished_pdf" if asset_type == "finished_pdf" else "source_pdf"
    if asset_type == "source_document" or ext in {"doc", "docx", "odt", "rtf", "txt", "md", "markdown"}:
        return "article_source"
    return "asset"


def infer_content_type_from_submission(kind: str, filename: str, explicit: Any = "") -> str:
    explicit_text = clean_text(explicit, 80)
    if explicit_text:
        return explicit_text
    ext = extension_for_filename(filename)
    if kind == "tripreports":
        return "trip_report"
    if kind == "vendorcontent":
        return "advertisement" if ext in {"pdf", "jpg", "jpeg", "png", "webp"} else "external_pdf"
    if kind == "presentations":
        return "external_pdf"
    return "article"
def image_mime_for_filename(filename: Any) -> str:
    ext = extension_for_filename(filename)
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
    }.get(ext, "application/octet-stream")


def source_format_for_filename(filename: Any, content_type: Any = "") -> str:
    ext = extension_for_filename(filename)
    if ext:
        return ext
    mime = str(content_type or "").lower()
    if "wordprocessingml.document" in mime:
        return "docx"
    if "pdf" in mime:
        return "pdf"
    if mime == "message/rfc822" or ext == "eml":
        return "eml"
    if mime.startswith("text/"):
        return "txt"
    return "unknown"


def decode_bytes_to_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")




def email_message_to_plain_text(data: bytes) -> str:
    try:
        msg = email.message_from_bytes(data, policy=policy.default)
    except Exception:
        return decode_bytes_to_text(data)
    parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = str(part.get_content_type() or "").lower()
            disp = str(part.get_content_disposition() or "").lower()
            if disp == "attachment":
                continue
            if ctype == "text/plain":
                try:
                    parts.append(str(part.get_content()))
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    parts.append(decode_bytes_to_text(payload))
        if not parts:
            for part in msg.walk():
                if str(part.get_content_type() or "").lower() == "text/html":
                    try:
                        html = str(part.get_content())
                    except Exception:
                        html = decode_bytes_to_text(part.get_payload(decode=True) or b"")
                    text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.I)
                    text = re.sub(r"</\s*p\s*>", "\n\n", text, flags=re.I)
                    text = re.sub(r"<[^>]+>", " ", text)
                    parts.append(text)
                    break
    else:
        try:
            parts.append(str(msg.get_content()))
        except Exception:
            parts.append(decode_bytes_to_text(msg.get_payload(decode=True) or b""))
    subject = str(msg.get("subject") or "").strip()
    sender = str(msg.get("from") or "").strip()
    header = "\n".join(x for x in [f"Subject: {subject}" if subject else "", f"From: {sender}" if sender else ""] if x)
    body = clean_extracted_text("\n\n".join(parts))
    return clean_extracted_text("\n\n".join(x for x in [header, body] if x))

def clean_extracted_text(text: Any, limit: int = 60000) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    # Imported DOCX/email sources often contain spacer paragraphs. Collapse those
    # aggressively here so the article editor does not inherit dead blank rows.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]



ARTICLE_ALLOWED_FONT_SIZES = {"9pt", "10pt", "11pt", "12pt", "14pt", "16pt", "18pt", "24pt"}
ARTICLE_ALLOWED_TEXT_ALIGN = {"left", "right", "center", "justify"}


def clean_article_style_attribute(match: re.Match) -> str:
    """Keep only magazine-safe TinyMCE inline styles.

    The controlled article editor intentionally allows selected text to carry a
    small set of approved font sizes. Earlier sanitising removed all style/span
    markup, so a user could change body text from 11pt to 9pt, save, and the
    article would reload at the base 11pt. This preserves only the explicit
    values the magazine editor exposes while still discarding arbitrary pasted
    Word/web styling.
    """
    quote = match.group(1) or '"'
    raw = match.group(2) or ""
    kept: List[str] = []
    for part in raw.split(";"):
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        key = name.strip().lower()
        val = value.strip().lower().replace(" ", "")
        if key == "font-size" and val in ARTICLE_ALLOWED_FONT_SIZES:
            kept.append(f"font-size: {val}")
        elif key == "text-align" and val in ARTICLE_ALLOWED_TEXT_ALIGN:
            kept.append(f"text-align: {val}")
    if not kept:
        return ""
    return f" style={quote}{'; '.join(kept)}{quote}"


def clean_article_html(value: Any, max_len: int = 120000) -> str:
    """Conservative storage sanitiser for controlled article-editor HTML.

    TinyMCE already limits the toolbar in the browser, but the backend still strips
    script/style blocks, inline event handlers, javascript: URLs and Word style
    leftovers before saving article HTML. Selected text font sizes from the
    controlled toolbar are preserved if they match the approved magazine sizes.
    The renderer/export stage can apply stricter template sanitising later.
    """
    text = str(value or "")[:max_len]
    if not text:
        return ""
    text = re.sub(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", "", text, flags=re.I | re.S)
    text = re.sub(r'\s+on[a-zA-Z]+\s*=\s*("[^\"]*"|\'[^\']*\'|[^\s>]+)', "", text)
    text = re.sub(r'(href|src)\s*=\s*(["\'])\s*javascript:[^"\']*\2', r"\1=\2#\2", text, flags=re.I)
    text = re.sub(r'\s+style\s*=\s*(["\'])(.*?)\1', clean_article_style_attribute, text, flags=re.I | re.S)
    text = re.sub(r"</?font[^>]*>", "", text, flags=re.I)
    text = re.sub(r"<span(?![^>]*style=)[^>]*>", "<span>", text, flags=re.I)
    return text.strip()

def rtf_to_plain_text(data: bytes) -> str:
    text = decode_bytes_to_text(data)
    # Lightweight RTF cleanup. This is not a full RTF parser, but is good enough
    # to produce editable draft text from simple article submissions.
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\par[d]?", "\n", text)
    text = re.sub(r"\\tab", "\t", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    return clean_extracted_text(text)


def docx_xml_paragraph_text(paragraph: ET.Element) -> str:
    parts: List[str] = []
    for node in paragraph.iter():
        name = str(node.tag).rsplit("}", 1)[-1]
        if name == "t" and node.text:
            parts.append(node.text)
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    value = "".join(parts).replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    # A single DOCX paragraph should not create stacked blank editor rows. Page
    # breaks are handled separately, so repeated soft breaks are just normalised.
    value = re.sub(r"\n{2,}", "\n", value)
    return value.strip()


def docx_relationship_targets(zf: zipfile.ZipFile) -> Dict[str, str]:
    rels: Dict[str, str] = {}
    try:
        root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
    except Exception:
        return rels
    for rel in root.iter():
        if str(rel.tag).rsplit("}", 1)[-1] != "Relationship":
            continue
        rid = str(rel.attrib.get("Id") or "").strip()
        target = str(rel.attrib.get("Target") or "").strip()
        if not rid or not target:
            continue
        if target.startswith("../"):
            target = target[3:]
        if not target.startswith("word/"):
            target = f"word/{target.lstrip('/')}"
        rels[rid] = target
    return rels


def docx_paragraph_image_targets(paragraph: ET.Element, rels: Dict[str, str]) -> List[str]:
    targets: List[str] = []
    for node in paragraph.iter():
        if str(node.tag).rsplit("}", 1)[-1] != "blip":
            continue
        rid = ""
        for attr, value in node.attrib.items():
            if attr.endswith("}embed") or attr.endswith("}link") or attr in {"embed", "link"}:
                rid = str(value or "").strip()
                break
        target = rels.get(rid, "")
        if target and target not in targets:
            targets.append(target)
    return targets


def docx_paragraph_has_page_break(paragraph: ET.Element) -> bool:
    for node in paragraph.iter():
        name = str(node.tag).rsplit("}", 1)[-1]
        if name == "lastRenderedPageBreak":
            return True
        if name == "br":
            for attr, value in node.attrib.items():
                if attr.endswith("}type") and str(value or "").lower() == "page":
                    return True
    return False


def docx_detect_column_count(root: ET.Element) -> int:
    """Return a best-effort DOCX section column count for editor preview hints."""
    count = 1
    try:
        for node in root.iter():
            if str(node.tag).rsplit("}", 1)[-1] != "cols":
                continue
            for attr, value in node.attrib.items():
                if attr.endswith("}num") or attr == "num":
                    try:
                        count = max(count, min(4, int(value or 1)))
                    except Exception:
                        pass
    except Exception:
        return 1
    return max(1, count)


def article_blocks_to_html(blocks: List[Dict[str, Any]], image_assets: List[Dict[str, Any]]) -> str:
    """Create editable TinyMCE HTML from extracted source blocks and images.

    The editor HTML is not the final print renderer. It is a faithful enough
    editable master: text stays in source order, embedded DOCX images are inserted
    where the DOCX referenced them, and image nodes keep data-mag-asset-id so the
    frontend can refresh short-lived preview URLs when the article is reopened.
    """
    asset_by_filename = {str(asset.get("fileName") or ""): asset for asset in image_assets if asset.get("assetId")}
    used: set[str] = set()
    parts: List[str] = []

    def img_html(filename: str) -> str:
        asset = asset_by_filename.get(filename) or {}
        asset_id = clean_text(asset.get("assetId"), 120)
        if not asset_id:
            return ""
        shown = asset_with_view_url(asset)
        src = html_escape(str(shown.get("viewUrl") or ""), quote=True)
        alt = html_escape(filename or clean_text(asset.get("title"), 240) or "Article image", quote=True)
        used.add(asset_id)
        return f'<figure class="mag-article-image" data-mag-asset-id="{html_escape(asset_id, quote=True)}"><img src="{src}" alt="{alt}" data-mag-asset-id="{html_escape(asset_id, quote=True)}"><figcaption>{html_escape(filename or "Article image")}</figcaption></figure>'

    for block in blocks or []:
        btype = str((block or {}).get("type") or "text")
        if btype == "image":
            filename = clean_text((block or {}).get("filename"), 240)
            html = img_html(filename)
            if html:
                parts.append(html)
            continue
        if btype == "page_break":
            parts.append('<hr data-source-page-break="1">')
            continue
        text = clean_extracted_text((block or {}).get("text"), 8000)
        if not text:
            continue
        text = re.sub(r"\n{2,}", "\n", text.strip())
        if not text:
            continue
        escaped = html_escape(text).replace("\n", "<br>")
        parts.append(f"<p>{escaped}</p>")

    # If the DOCX contained images that were not attached to a paragraph, append
    # them once at the end rather than silently losing them.
    for asset in image_assets or []:
        asset_id = clean_text(asset.get("assetId"), 120)
        filename = clean_text(asset.get("fileName"), 240)
        if asset_id and asset_id not in used:
            html = img_html(filename)
            if html:
                parts.append(html)
    return "".join(parts)


def article_text_to_html(text: Any) -> str:
    body = clean_extracted_text(text, 60000)
    if not body:
        return ""
    parts = []
    for para in re.split(r"\n{2,}", body):
        value = para.strip()
        if not value:
            continue
        parts.append(f"<p>{html_escape(value).replace(chr(10), '<br>')}</p>")
    return "".join(parts)


def source_pages_from_blocks(blocks: List[Dict[str, Any]], target_chars: int = 1750) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    current_text: List[str] = []
    current_images: List[str] = []
    current_image_items: List[Dict[str, Any]] = []
    current_cost = 0
    current_text_chars = 0

    def flush(reason: str = "auto") -> None:
        nonlocal current_text, current_images, current_image_items, current_cost, current_text_chars
        if not current_text and not current_images:
            current_cost = 0
            current_text_chars = 0
            return
        body = clean_extracted_text("\n\n".join(current_text), 12000)
        body_len = max(1, len(body or ""))
        image_items: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in current_image_items:
            name = clean_text(item.get("filename"), 240)
            if not name or name in seen:
                continue
            seen.add(name)
            offset = max(0, min(body_len, clean_int(item.get("charOffset"), 0)))
            image_items.append({
                "filename": name,
                "charOffset": offset,
                "positionRatio": round(offset / body_len, 4),
            })
        pages.append({
            "sourcePageNumber": len(pages) + 1,
            "bodyMarkdown": body,
            "imageFilenames": list(dict.fromkeys(current_images)),
            "imageItems": image_items,
            "pageMapMethod": reason,
        })
        current_text = []
        current_images = []
        current_image_items = []
        current_cost = 0
        current_text_chars = 0

    for block in blocks:
        btype = str(block.get("type") or "text")
        if btype == "page_break":
            flush("docx_page_break")
            continue
        if btype == "image":
            filename = clean_text(block.get("filename"), 240)
            if filename and filename not in current_images:
                current_images.append(filename)
                current_image_items.append({"filename": filename, "charOffset": current_text_chars})
            current_cost += 520
            if current_cost >= target_chars * 1.18:
                flush("estimated_from_docx_flow")
            continue
        text = clean_extracted_text(block.get("text"), 5000)
        if not text:
            continue
        text_cost = len(text)
        if current_text and current_cost + text_cost > target_chars:
            flush("estimated_from_docx_flow")
        current_text.append(text)
        current_text_chars += text_cost + 2
        current_cost += text_cost
    flush("estimated_from_docx_flow")
    return pages


def source_pages_from_text(text: Any, target_chars: int = 1750) -> List[Dict[str, Any]]:
    body = clean_extracted_text(text, 60000)
    if not body:
        return []
    paragraphs = body.split("\n\n")
    blocks = [{"type": "text", "text": p} for p in paragraphs if p.strip()]
    return source_pages_from_blocks(blocks, target_chars=target_chars)


def count_pdf_pages_lightweight(data: bytes) -> int:
    """Return a best-effort PDF page count without external dependencies.

    This intentionally avoids full PDF parsing. It is good enough for source-document
    magazine import where a fallback of one page is safer than failing the conversion.
    """
    if not data:
        return 0
    head = data[:5]
    if head != b"%PDF-":
        return 0
    sample = data[: min(len(data), 50 * 1024 * 1024)]
    # Count real page objects but not the /Pages tree. This catches most PDFs produced
    # by Word/LibreOffice/Chrome and avoids treating every resource reference as a page.
    matches = re.findall(rb"/Type\s*/Page(?!s)\b", sample)
    if matches:
        return max(1, min(500, len(matches)))
    # Fallback for some compact/cross-reference-stream PDFs. /Count can overcount in
    # nested trees, so use the largest reasonable value found.
    counts = []
    for raw in re.findall(rb"/Count\s+(\d{1,4})", sample):
        try:
            value = int(raw)
            if 0 < value <= 500:
                counts.append(value)
        except Exception:
            pass
    return max(counts) if counts else 1


def pdf_source_pages(page_count: int) -> List[Dict[str, Any]]:
    count = max(1, min(500, clean_int(page_count, 1)))
    return [
        {
            "sourcePageNumber": n,
            "bodyMarkdown": "",
            "imageAssetIds": [],
            "imageFilenames": [],
            "imageItems": [],
            "sourcePageKind": "pdf_page",
            "pageMapMethod": "pdf_camera_ready",
        }
        for n in range(1, count + 1)
    ]


def extract_docx_text_and_media(data: bytes) -> Dict[str, Any]:
    paragraphs: List[str] = []
    media: List[Dict[str, Any]] = []
    blocks: List[Dict[str, Any]] = []
    seen_media: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        try:
            xml_data = zf.read("word/document.xml")
        except KeyError:
            return {"text": "", "media": [], "sourcePages": [], "status": "failed", "message": "DOCX has no word/document.xml."}
        rels = docx_relationship_targets(zf)
        root = ET.fromstring(xml_data)
        column_count = docx_detect_column_count(root)
        for paragraph in root.iter():
            if str(paragraph.tag).rsplit("}", 1)[-1] != "p":
                continue
            value = docx_xml_paragraph_text(paragraph)
            image_targets = docx_paragraph_image_targets(paragraph, rels)
            if value:
                paragraphs.append(value)
                blocks.append({"type": "text", "text": value})
            for target in image_targets:
                filename = safe_filename(target.rsplit("/", 1)[-1], "embedded-image")
                if filename:
                    blocks.append({"type": "image", "filename": filename})
                if target not in seen_media:
                    ext = extension_for_filename(target)
                    if ext in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff"}:
                        try:
                            blob = zf.read(target)
                        except Exception:
                            blob = b""
                        if blob and len(blob) <= 20 * 1024 * 1024:
                            media.append({"filename": filename, "bytes": blob, "mimeType": image_mime_for_filename(target)})
                            seen_media.add(target)
            if docx_paragraph_has_page_break(paragraph):
                blocks.append({"type": "page_break"})
        # Fallback: include any unreferenced media so it is still available to the editor.
        for name in zf.namelist():
            if len(media) >= 25:
                break
            if not name.startswith("word/media/") or name.endswith("/") or name in seen_media:
                continue
            ext = extension_for_filename(name)
            if ext not in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff"}:
                continue
            try:
                blob = zf.read(name)
            except Exception:
                continue
            if not blob or len(blob) > 20 * 1024 * 1024:
                continue
            filename = safe_filename(name.rsplit("/", 1)[-1], "embedded-image")
            media.append({"filename": filename, "bytes": blob, "mimeType": image_mime_for_filename(name)})
            blocks.append({"type": "image", "filename": filename})
            seen_media.add(name)
    text = clean_extracted_text("\n\n".join(paragraphs))
    pages = source_pages_from_blocks(blocks, target_chars=1750)
    source_blocks = []
    for block in blocks[:500]:
        btype = clean_text(block.get("type"), 40) or "text"
        entry = {"type": btype}
        if btype == "text":
            entry["text"] = clean_extracted_text(block.get("text"), 5000)
        elif btype == "image":
            entry["filename"] = safe_filename(block.get("filename"), "embedded-image")
        source_blocks.append(entry)
    return {"text": text, "media": media, "sourcePages": pages, "sourceBlocks": source_blocks, "sourceColumnCount": column_count, "status": "complete" if paragraphs or media else "no_text", "message": "DOCX extracted with source-layout page plan."}


def estimate_preferred_pages(body_markdown: Any, fallback: int = 1) -> int:
    text = str(body_markdown or "").strip()
    if not text:
        return max(1, fallback)
    # Conservative magazine estimate. Real fitting will be replaced by the
    # proof/render pipeline, but this keeps long pieces visible as multi-page.
    chars_per_page = 2800
    return max(1, min(20, (len(text) + chars_per_page - 1) // chars_per_page))


def create_extracted_image_asset(media_item: Dict[str, Any], *, kind: str, issue_id: str, source_slug: str, source_submission: Dict[str, Any] | None = None, source_content: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ensure_table()
    if not ASSETS_BUCKET:
        raise RuntimeError("MAGAZINE_ASSETS_BUCKET is not configured.")
    asset_id = f"asset-{uuid.uuid4().hex}"
    filename = safe_filename(media_item.get("filename") or f"image-{asset_id}.jpg", "embedded-image")
    key = f"{ASSETS_PREFIX}inbound/{kind}/{simple_slug(source_slug or asset_id)}/extracted-media/{asset_id}-{filename}"
    blob = media_item.get("bytes") or b""
    mime = clean_text(media_item.get("mimeType"), 120) or image_mime_for_filename(filename)
    s3.put_object(Bucket=ASSETS_BUCKET, Key=key, Body=blob, ContentType=mime, ServerSideEncryption="AES256", Metadata={"source": "docx_embedded_image", "source-kind": kind[:80]})
    asset_type = "trip_report_image" if kind == "tripreports" else "article_image"
    item = {
        "pk": asset_pk(asset_id),
        "sk": "METADATA",
        "entityType": "MagazineAsset",
        "assetId": asset_id,
        "assetType": asset_type,
        "issueId": issue_id or "unassigned",
        "fileName": filename,
        "mimeType": mime,
        "fileSizeBytes": len(blob),
        "s3Bucket": ASSETS_BUCKET,
        "s3Key": key,
        "source": "docx_embedded_image",
        "sourceSubmissionKind": kind,
        "sourceSubmissionId": str((source_submission or {}).get("submission_id") or ""),
        "sourceSubmissionSk": str((source_submission or {}).get("sk") or ""),
        "sourceContentItemId": str((source_content or {}).get("contentItemId") or ""),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "gsi1pk": "ASSETS",
        "gsi1sk": f"{now_iso()}#{asset_id}",
        "gsi2pk": f"ASSET_TYPE#{asset_type}",
        "gsi2sk": f"{now_iso()}#{asset_id}",
    }
    table.put_item(Item=dynamodb_safe(item))
    return item


def source_pages_with_asset_ids(source_pages: List[Dict[str, Any]], image_assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    asset_by_filename = {str(asset.get("fileName") or ""): asset.get("assetId") for asset in image_assets if asset.get("assetId")}
    output: List[Dict[str, Any]] = []
    for idx, page in enumerate(source_pages or []):
        filenames = [safe_filename(x, "") for x in (page.get("imageFilenames") or []) if safe_filename(x, "")]
        asset_ids = [asset_by_filename.get(name) for name in filenames if asset_by_filename.get(name)]
        image_items: List[Dict[str, Any]] = []
        seen: set[str] = set()
        raw_items = page.get("imageItems") if isinstance(page.get("imageItems"), list) else []
        if raw_items:
            for raw in raw_items:
                name = safe_filename((raw or {}).get("filename"), "")
                asset_id = asset_by_filename.get(name)
                if not name or not asset_id or asset_id in seen:
                    continue
                seen.add(asset_id)
                ratio = max(0.0, min(1.0, float((raw or {}).get("positionRatio") or 0)))
                image_items.append({
                    "assetId": asset_id,
                    "filename": name,
                    "charOffset": clean_int((raw or {}).get("charOffset"), 0),
                    "positionRatio": Decimal(str(round(ratio, 4))),
                })
        else:
            for pos, asset_id in enumerate(asset_ids):
                if not asset_id or asset_id in seen:
                    continue
                seen.add(asset_id)
                image_items.append({"assetId": asset_id, "filename": filenames[pos] if pos < len(filenames) else "", "positionRatio": Decimal(str(round(0.35 + (pos * 0.2), 4)))})
        output.append({
            "sourcePageNumber": clean_int(page.get("sourcePageNumber"), idx + 1),
            "bodyMarkdown": clean_extracted_text(page.get("bodyMarkdown"), 12000),
            "imageAssetIds": asset_ids,
            "imageFilenames": filenames,
            "imageItems": image_items,
            "sourcePageKind": clean_text(page.get("sourcePageKind") or page.get("source_page_kind"), 60),
            "pageMapMethod": clean_text(page.get("pageMapMethod"), 80) or "estimated",
        })
    return output


def extract_source_material(bucket: str, key: str, filename: str, content_type: str = "", *, kind: str = "magazinecontent", issue_id: str = "unassigned", source_slug: str = "", source_submission: Dict[str, Any] | None = None, source_content: Dict[str, Any] | None = None) -> Dict[str, Any]:
    source_format = source_format_for_filename(filename, content_type)
    if source_format in {"zip", "unknown"}:
        return {"bodyMarkdown": "", "sourceFormat": source_format, "extractionStatus": "unsupported" if source_format != "unknown" else "not_available", "extractionMessage": f"{source_format.upper()} text extraction is not implemented in this stage.", "extractedImageAssetIds": [], "extractedImageCount": 0, "extractedCharacterCount": 0}
    if not bucket or not key:
        return {"bodyMarkdown": "", "sourceFormat": source_format, "extractionStatus": "failed", "extractionMessage": "No S3 source object was available for extraction.", "extractedImageAssetIds": [], "extractedImageCount": 0, "extractedCharacterCount": 0}
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()
        media: List[Dict[str, Any]] = []
        source_pages: List[Dict[str, Any]] = []
        if source_format == "pdf":
            page_count = count_pdf_pages_lightweight(data)
            body = ""
            media = []
            source_pages = pdf_source_pages(page_count or 1)
            status = "camera_ready"
            message = f"PDF source document detected with {len(source_pages)} page(s). Use camera-ready PDF page import for faithful placement."
        elif source_format == "docx":
            extracted = extract_docx_text_and_media(data)
            body = extracted.get("text") or ""
            media = extracted.get("media") or []
            source_pages = extracted.get("sourcePages") or []
            status = extracted.get("status") or ("complete" if body else "no_text")
            message = extracted.get("message") or "DOCX extracted."
        elif source_format in {"txt", "md"} or str(content_type or "").lower().startswith("text/"):
            body = clean_extracted_text(decode_bytes_to_text(data))
            source_pages = source_pages_from_text(body)
            status = "complete" if body else "no_text"
            message = "Text document extracted."
        elif source_format == "eml":
            body = email_message_to_plain_text(data)
            source_pages = source_pages_from_text(body)
            status = "complete" if body else "no_text"
            message = "Email message extracted."
        elif source_format == "rtf":
            body = rtf_to_plain_text(data)
            source_pages = source_pages_from_text(body)
            status = "complete" if body else "no_text"
            message = "RTF text extracted with lightweight cleanup."
        elif source_format == "odt":
            # ODT is zipped XML. Pull text:p/text:h elements without external deps.
            paragraphs: List[str] = []
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                root = ET.fromstring(zf.read("content.xml"))
                for node in root.iter():
                    name = str(node.tag).rsplit("}", 1)[-1]
                    if name not in {"p", "h"}:
                        continue
                    value = "".join(node.itertext()).strip()
                    if value:
                        paragraphs.append(value)
            body = clean_extracted_text("\n\n".join(paragraphs))
            source_pages = source_pages_from_text(body)
            status = "complete" if body else "no_text"
            message = "ODT text extracted."
        else:
            return {"bodyMarkdown": "", "sourceFormat": source_format, "extractionStatus": "unsupported", "extractionMessage": f"{source_format.upper()} extraction is not supported yet.", "extractedImageAssetIds": [], "extractedImageCount": 0, "extractedCharacterCount": 0}
        image_assets: List[Dict[str, Any]] = []
        for media_item in media:
            try:
                image_assets.append(create_extracted_image_asset(media_item, kind=kind, issue_id=issue_id or "unassigned", source_slug=source_slug or key, source_submission=source_submission, source_content=source_content))
            except Exception as exc:
                print(f"Could not save extracted DOCX media {media_item.get('filename')}: {exc}")
        source_pages = source_pages_with_asset_ids(source_pages or source_pages_from_text(body), image_assets)
        source_blocks = extracted.get("sourceBlocks") if source_format == "docx" and isinstance(locals().get("extracted"), dict) else []
        source_column_count = clean_int(extracted.get("sourceColumnCount"), 1) if source_format == "docx" and isinstance(locals().get("extracted"), dict) else 1
        body_html = article_blocks_to_html(source_blocks, image_assets) if source_format == "docx" else article_text_to_html(body)
        return {"bodyMarkdown": body, "bodyHtml": body_html, "sourceFormat": source_format, "extractionStatus": status, "extractionMessage": message, "extractedImageAssetIds": [x.get("assetId") for x in image_assets if x.get("assetId")], "extractedImageCount": len(image_assets), "extractedCharacterCount": len(body or ""), "sourcePages": source_pages, "sourceBlocks": source_blocks, "sourceColumnCount": source_column_count, "sourcePageCount": len(source_pages), "sourceLayoutStatus": "ready" if source_pages else "not_available"}
    except Exception as exc:
        print(f"Source extraction failed for {bucket}/{key}: {exc}")
        return {"bodyMarkdown": "", "sourceFormat": source_format, "extractionStatus": "failed", "extractionMessage": str(exc)[:500], "extractedImageAssetIds": [], "extractedImageCount": 0, "extractedCharacterCount": 0}



def clean_text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def clean_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def clean_decimal(value: Any, default: Any = "0") -> Decimal:
    try:
        if isinstance(value, Decimal):
            return value
        # Always construct from string so DynamoDB never sees Python float types.
        return Decimal(str(value))
    except Exception:
        return Decimal(str(default))


def clean_float(value: Any, default: float = 0.0) -> Decimal:
    # Backwards-compatible name: returns Decimal, not float, for DynamoDB safety.
    return clean_decimal(value, default)


def clamp_float(value: Any, default: float, minimum: float, maximum: float) -> Decimal:
    number = clean_decimal(value, default)
    lo = Decimal(str(minimum))
    hi = Decimal(str(maximum))
    return max(lo, min(hi, number))




def dynamodb_safe(value: Any) -> Any:
    """Recursively convert Python floats into Decimal before DynamoDB writes.

    API Gateway JSON parsing produces Python float values for slider/geometry
    settings. boto3's DynamoDB serializer rejects floats, so all nested values
    must be converted before put_item/update_item calls.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, list):
        return [dynamodb_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: dynamodb_safe(item) for key, item in value.items()}
    return value

def clean_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def normalise_cover_layout(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "lrocName": clean_text(raw.get("lrocName"), 120),
        "lrocFontFamily": clean_text(raw.get("lrocFontFamily"), 80),
        "lrocPointSize": clean_int(raw.get("lrocPointSize"), 72),
        "lrocTopPercent": clean_int(raw.get("lrocTopPercent"), 3),
        "lrocLeftPercent": clean_int(raw.get("lrocLeftPercent"), 3),
        "lrocWidthPercent": clean_int(raw.get("lrocWidthPercent"), 68),
        "lrocLetterSpacing": clean_text(raw.get("lrocLetterSpacing"), 20),
        "subtitleEnabled": clean_bool(raw.get("subtitleEnabled"), True),
        "subtitleText": clean_text(raw.get("subtitleText"), 80),
        "subtitleFontFamily": clean_text(raw.get("subtitleFontFamily"), 80),
        "subtitlePointSize": clean_int(raw.get("subtitlePointSize"), 34),
        "subtitleTopPercent": clean_int(raw.get("subtitleTopPercent"), 19),
        "subtitleRightPercent": clean_int(raw.get("subtitleRightPercent", raw.get("subtitleLeftPercent")), 21),
        "logoEnabled": clean_bool(raw.get("logoEnabled"), True),
        "logoUrl": clean_text(raw.get("logoUrl"), 240),
        "logoPosition": clean_text(raw.get("logoPosition"), 40),
        "logoWidthPercent": clean_int(raw.get("logoWidthPercent"), 18),
        "logoTopPercent": clean_int(raw.get("logoTopPercent"), 3),
        "logoRightPercent": clean_int(raw.get("logoRightPercent", raw.get("logoLeftPercent")), 5),
        "logoMaxHeightPercent": clean_int(raw.get("logoMaxHeightPercent"), 24),
        "logoOpacityPercent": clean_int(raw.get("logoOpacityPercent"), 100),
        "topBannerEnabled": clean_bool(raw.get("topBannerEnabled"), True),
        "topBannerText": clean_text(raw.get("topBannerText"), 260),
        "bottomBannerEnabled": clean_bool(raw.get("bottomBannerEnabled"), True),
        "bottomBannerText": clean_text(raw.get("bottomBannerText"), 260),
        "issueLabel": clean_text(raw.get("issueLabel"), 180),
        "issueTopPercent": clean_int(raw.get("issueTopPercent"), 27),
        "issueLeftPercent": clean_int(raw.get("issueLeftPercent"), 3),
        "issuePointSize": clean_int(raw.get("issuePointSize"), 24),
        "siteUrl": clean_text(raw.get("siteUrl"), 120),
        "showGuides": clean_bool(raw.get("showGuides"), False),
        "showRulers": clean_bool(raw.get("showRulers"), False),
        "showTopRuler": clean_bool(raw.get("showTopRuler"), False),
        "lrocColor": clean_text(raw.get("lrocColor"), 24),
        "lrocOutlineColor": clean_text(raw.get("lrocOutlineColor"), 24),
        "subtitleColor": clean_text(raw.get("subtitleColor"), 24),
        "subtitleOutlineColor": clean_text(raw.get("subtitleOutlineColor"), 24),
        "issueColor": clean_text(raw.get("issueColor"), 24),
        "urlColor": clean_text(raw.get("urlColor"), 24),
        "topBannerBgColor": clean_text(raw.get("topBannerBgColor"), 24),
        "topBannerTextColor": clean_text(raw.get("topBannerTextColor"), 24),
        "bottomBannerBgColor": clean_text(raw.get("bottomBannerBgColor"), 24),
        "bottomBannerTextColor": clean_text(raw.get("bottomBannerTextColor"), 24),
    }


def normalise_calendar_events(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items: List[Dict[str, Any]] = []
    for item in raw[:80]:
        if not isinstance(item, dict):
            continue
        items.append({
            "event_id": clean_text(item.get("event_id") or item.get("eventId"), 120),
            "date_from": clean_text(item.get("date_from") or item.get("start_at") or item.get("start"), 40),
            "date_to": clean_text(item.get("date_to") or item.get("end_at") or item.get("end"), 40),
            "event_type": clean_text(item.get("event_type") or item.get("eventType") or item.get("type") or item.get("classification"), 120),
            "rating": clean_text(item.get("rating"), 120),
            "rating_color": clean_text(item.get("rating_color") or item.get("ratingColor"), 24),
            "title": clean_text(item.get("title") or item.get("trip_name") or item.get("name"), 240),
            "description": clean_text(item.get("description") or item.get("short_description") or item.get("shortDescription") or item.get("calendar_blurb"), 1200),
        })
    return items



def normalise_mce_pagination_diagnostics(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    warnings = raw.get("oversizedBlockWarnings") if isinstance(raw.get("oversizedBlockWarnings"), list) else []
    clean_warnings: List[Dict[str, Any]] = []
    for idx, item in enumerate(warnings[:24]):
        if not isinstance(item, dict):
            continue
        clean_warnings.append({
            "blockIndex": max(0, min(10000, clean_int(item.get("blockIndex"), idx + 1))),
            "heightPx": max(0, min(2000000, clean_int(item.get("heightPx"), 0))),
            "pageLimitPx": max(0, min(2000000, clean_int(item.get("pageLimitPx"), 0))),
            "mediaLike": clean_bool(item.get("mediaLike"), False),
        })
    return {
        "rendererVersion": clean_text(raw.get("rendererVersion"), 24),
        "sourceBlockCount": max(0, min(10000, clean_int(raw.get("sourceBlockCount"), 0))),
        "manualPageBreakCount": max(0, min(10000, clean_int(raw.get("manualPageBreakCount"), 0))),
        "pageFragmentCount": max(0, min(10000, clean_int(raw.get("pageFragmentCount"), 0))),
        "columns": max(1, min(4, clean_int(raw.get("columns"), 1))),
        "measureWidthPx": max(0, min(2000000, clean_int(raw.get("measureWidthPx"), 0))),
        "contentHeightPx": max(0, min(2000000, clean_int(raw.get("contentHeightPx"), 0))),
        "pageCapacityPx": max(0, min(2000000, clean_int(raw.get("pageCapacityPx"), 0))),
        "oversizedBlockWarnings": clean_warnings,
    }

def normalise_layout_slots(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    slots: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw[:24]):
        if not isinstance(item, dict):
            continue
        slot_id = clean_text(item.get("slotId") or item.get("slot_id"), 80) or f"slot-{idx + 1}"
        slot_type = clean_text(item.get("slotType") or item.get("slot_type"), 40) or "content"
        is_advert_slot = "advert" in slot_id.lower() or "advert" in clean_text(item.get("slotLabel") or item.get("slot_label"), 120).lower() or "sponsor" in slot_id.lower()
        focal_y_default = 0 if is_advert_slot else 50
        slots.append({
            "slotId": slot_id,
            "slotLabel": clean_text(item.get("slotLabel") or item.get("slot_label"), 120),
            "slotType": slot_type,
            "assetId": clean_text(item.get("assetId") or item.get("asset_id"), 120),
            "contentItemId": clean_text(item.get("contentItemId") or item.get("content_item_id"), 120),
            "fitMode": clean_text(item.get("fitMode") or item.get("fit_mode"), 40) or ("contain" if is_advert_slot else "cover"),
            "imageZoomPercent": max(25, min(300, clean_int(item.get("imageZoomPercent") or item.get("image_zoom_percent"), 100))),
            "imageFocalXPercent": max(0, min(100, clean_int(item.get("imageFocalXPercent") or item.get("image_focal_x_percent"), 50))),
            "imageFocalYPercent": max(0, min(100, clean_int(item.get("imageFocalYPercent") or item.get("image_focal_y_percent"), focal_y_default))),
            "caption": clean_text(item.get("caption"), 1000),
            "textOverride": clean_text(item.get("textOverride") or item.get("text_override"), 8000),
            "frameTitle": clean_text(item.get("frameTitle") or item.get("frame_title"), 160),
            "bodyAlign": clean_text(item.get("bodyAlign") or item.get("body_align"), 24),
            "titleAlign": clean_text(item.get("titleAlign") or item.get("title_align"), 24),
            "titleFontSize": clamp_float(item.get("titleFontSize") or item.get("title_font_size"), clamp_float(item.get("fontSize") or item.get("font_size"), 9, 6, 30) * Decimal("1.28"), 6, 36),
            "bodyFontSize": clamp_float(item.get("bodyFontSize") or item.get("body_font_size") or item.get("fontSize") or item.get("font_size"), 9, 6, 30),
            "titleLineHeight": clean_text(item.get("titleLineHeight") or item.get("title_line_height"), 16) or "1.05",
            "bodyLineHeight": clean_text(item.get("bodyLineHeight") or item.get("body_line_height") or item.get("lineHeight") or item.get("line_height"), 16),
            "fontSize": clamp_float(item.get("bodyFontSize") or item.get("body_font_size") or item.get("fontSize") or item.get("font_size"), 9, 6, 30),
            "lineHeight": clean_text(item.get("bodyLineHeight") or item.get("body_line_height") or item.get("lineHeight") or item.get("line_height"), 16),
            "padding": max(0, min(12, clean_int(item.get("padding"), 3))),
            "borderWidth": max(0, min(8, clean_int(item.get("borderWidth") or item.get("border_width"), 1))),
            "borderColor": clean_text(item.get("borderColor") or item.get("border_color"), 24),
            "backgroundColor": clean_text(item.get("backgroundColor") or item.get("background_color"), 24),
            "titleUnderline": clean_bool(item.get("titleUnderline") or item.get("title_underline"), True),
            "lineFormatter": clean_text(item.get("lineFormatter") or item.get("line_formatter"), 40) or "normal",
            "calendarMonths": max(1, min(24, clean_int(item.get("calendarMonths") or item.get("calendar_months"), 4))),
            "calendarTitle": clean_text(item.get("calendarTitle") or item.get("calendar_title"), 160),
            "calendarSubtitle": clean_text(item.get("calendarSubtitle") or item.get("calendar_subtitle"), 400),
            "calendarFontSize": clamp_float(item.get("calendarFontSize") or item.get("calendar_font_size"), 8, 5.5, 16),
            "calendarLineHeight": clamp_float(item.get("calendarLineHeight") or item.get("calendar_line_height"), 1.14, 0.85, 2),
            "calendarDateWidth": clamp_float(item.get("calendarDateWidth") or item.get("calendar_date_width"), 7, 4, 20),
            "calendarTypeWidth": clamp_float(item.get("calendarTypeWidth") or item.get("calendar_type_width"), 13, 8, 30),
            "calendarNameWidth": clamp_float(item.get("calendarNameWidth") or item.get("calendar_name_width"), 20, 12, 40),
            "calendarEvents": normalise_calendar_events(item.get("calendarEvents") or item.get("calendar_events")),
            # Geometry and article-flow fields must survive round-trips through the backend.
            # Without these, continuation pages lose their explicit text range and restart at
            # character 0 when the flatplan is reloaded.
            "x": clamp_float(item.get("x"), 0, 0, 100),
            "y": clamp_float(item.get("y"), 0, 0, 100),
            "w": clamp_float(item.get("w"), 100, 1, 100),
            "h": clamp_float(item.get("h"), 20, 1, 100),
            "renderMode": clean_text(item.get("renderMode") or item.get("render_mode"), 60),
            "leadCharacterLimit": max(0, min(5000, clean_int(item.get("leadCharacterLimit") or item.get("lead_character_limit"), 0))),
            "startCharacter": max(0, min(250000, clean_int(item.get("startCharacter") or item.get("start_character"), 0))),
            "previewCharacterLimit": max(0, min(250000, clean_int(item.get("previewCharacterLimit") or item.get("preview_character_limit"), 0))),
            "storyFlowAutoStart": clean_bool(item.get("storyFlowAutoStart") if "storyFlowAutoStart" in item else item.get("story_flow_auto_start"), False),
            "storyFlowStartCharacter": max(0, min(250000, clean_int(item.get("storyFlowStartCharacter") or item.get("story_flow_start_character"), 0))),
            "storyFlowCharacterLimit": max(0, min(250000, clean_int(item.get("storyFlowCharacterLimit") or item.get("story_flow_character_limit"), 0))),
            "sourcePageIndex": max(0, min(500, clean_int(item.get("sourcePageIndex") or item.get("source_page_index"), 0))),
            "sourcePageNumber": max(0, min(500, clean_int(item.get("sourcePageNumber") or item.get("source_page_number"), 0))),
            "sourceLayoutMode": clean_text(item.get("sourceLayoutMode") or item.get("source_layout_mode"), 60),
            # v3.4.0 MCE article-page fields. These must survive the backend
            # normalisation round-trip; otherwise each placed page loses its
            # page offset and renders from the beginning of the TinyMCE article.
            "articleHtml": clean_article_html(item.get("articleHtml") or item.get("article_html"), 120000),
            "articlePageHtml": clean_article_html(item.get("articlePageHtml") or item.get("article_page_html"), 120000),
            "mcePaginationMode": clean_text(item.get("mcePaginationMode") or item.get("mce_pagination_mode"), 40),
            "mcePageIndex": max(0, min(500, clean_int(item.get("mcePageIndex") or item.get("mce_page_index"), 0))),
            "mcePageNumber": max(1, min(500, clean_int(item.get("mcePageNumber") or item.get("mce_page_number"), 1))),
            "mcePageCount": max(1, min(500, clean_int(item.get("mcePageCount") or item.get("mce_page_count"), 1))),
            "mcePageOffsetPx": max(0, min(2000000, clean_int(item.get("mcePageOffsetPx") or item.get("mce_page_offset_px"), 0))),
            "mcePageHeightPx": max(1, min(2000000, clean_int(item.get("mcePageHeightPx") or item.get("mce_page_height_px"), 990))),
            "mcePageContentHeightPx": max(1, min(2000000, clean_int(item.get("mcePageContentHeightPx") or item.get("mce_page_content_height_px"), 944))),
            "mcePageFooterHeightPx": max(0, min(2000000, clean_int(item.get("mcePageFooterHeightPx") or item.get("mce_page_footer_height_px"), 46))),
            "mcePageWidthPx": max(1, min(2000000, clean_int(item.get("mcePageWidthPx") or item.get("mce_page_width_px"), 700))),
            "mceMeasuredHeightPx": max(0, min(2000000, clean_int(item.get("mceMeasuredHeightPx") or item.get("mce_measured_height_px"), 0))),
            "mcePaginationDiagnostics": normalise_mce_pagination_diagnostics(item.get("mcePaginationDiagnostics") or item.get("mce_pagination_diagnostics")),
            "articleFontSize": clamp_float(item.get("articleFontSize") or item.get("article_font_size"), 8.2, 5.5, 16),
            "articleLineHeight": clamp_float(item.get("articleLineHeight") or item.get("article_line_height"), 1.15, 0.8, 2.0),
            "autoUsePrimaryContent": clean_bool(item.get("autoUsePrimaryContent") if "autoUsePrimaryContent" in item else item.get("auto_use_primary_content"), False),
            "autoUseArticleImage": clean_bool(item.get("autoUseArticleImage") if "autoUseArticleImage" in item else item.get("auto_use_article_image"), False),
            # Magazine 3.1 composition/panel fields. These keep document-flow settings and
            # page-local image/advert panel geometry stable across save/reload.
            "documentColumns": max(1, min(4, clean_int(item.get("documentColumns") or item.get("document_columns"), 2))),
            "documentTargetPages": max(0, min(60, clean_int(item.get("documentTargetPages") or item.get("document_target_pages"), 0))),
            "documentImagePolicy": clean_text(item.get("documentImagePolicy") or item.get("document_image_policy"), 60),
            "documentFlowStartPage": max(0, min(500, clean_int(item.get("documentFlowStartPage") or item.get("document_flow_start_page"), 0))),
            "documentFlowPageIndex": max(0, min(500, clean_int(item.get("documentFlowPageIndex") or item.get("document_flow_page_index"), 0))),
            "documentFlowPageCount": max(0, min(500, clean_int(item.get("documentFlowPageCount") or item.get("document_flow_page_count"), 0))),
            "panelLocked": clean_bool(item.get("panelLocked") if "panelLocked" in item else item.get("panel_locked"), False),
            "panelKind": clean_text(item.get("panelKind") or item.get("panel_kind"), 60),
            "aspectRatioLocked": clean_bool(item.get("aspectRatioLocked") if "aspectRatioLocked" in item else item.get("aspect_ratio_locked"), True),
            "naturalAspectRatio": clamp_float(item.get("naturalAspectRatio") or item.get("natural_aspect_ratio"), 0, 0, 10),
            "updatedAt": now_iso(),
        })
    return slots


def layout_slot_is_locked(slot: Dict[str, Any]) -> bool:
    if not isinstance(slot, dict):
        return False
    return clean_bool(slot.get("panelLocked") if "panelLocked" in slot else slot.get("panel_locked"), False) or clean_bool(slot.get("locked"), False) or clean_bool(slot.get("slotLocked") if "slotLocked" in slot else slot.get("slot_locked"), False)


def locked_layout_slots_for_reset(page: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_slots = page.get("layoutSlots") if isinstance(page, dict) else []
    if not isinstance(raw_slots, list):
        return []
    preserved: List[Dict[str, Any]] = []
    seen: set = set()
    for idx, raw in enumerate(raw_slots):
        if not isinstance(raw, dict) or not layout_slot_is_locked(raw):
            continue
        normalised = normalise_layout_slots([raw])
        if not normalised:
            continue
        slot = normalised[0]
        slot["panelLocked"] = True
        slot_id = clean_text(slot.get("slotId"), 80) or f"locked-panel-{idx + 1}"
        while slot_id in seen:
            slot_id = f"{slot_id}-{idx + 1}"
        seen.add(slot_id)
        slot["slotId"] = slot_id
        if not slot.get("panelKind"):
            slot["panelKind"] = "advert" if "advert" in slot_id.lower() or "sponsor" in slot_id.lower() else "locked"
        preserved.append(slot)
    return preserved


def merge_locked_slots_for_reset(requested_slots: List[Dict[str, Any]], locked_slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not locked_slots:
        return requested_slots or []
    out = list(requested_slots or [])
    by_id = {str(slot.get("slotId") or ""): idx for idx, slot in enumerate(out) if isinstance(slot, dict)}
    for locked in locked_slots:
        slot_id = str(locked.get("slotId") or "")
        if slot_id and slot_id in by_id:
            out[by_id[slot_id]] = locked
        else:
            out.append(locked)
    return out


def magazine_page_content_ids(page: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for field in ("layoutSlots", "contentSlots"):
        raw = page.get(field)
        if not isinstance(raw, list):
            continue
        for slot in raw:
            if not isinstance(slot, dict):
                continue
            cid = clean_text(slot.get("contentItemId") or slot.get("content_item_id"), 120)
            if cid and cid not in ids:
                ids.append(cid)
    return ids


def refresh_content_placement_after_page_clear(issue_id: str, cleared_page_numbers: List[int], content_ids: List[str]) -> None:
    cleared = {clean_int(n, 0) for n in cleared_page_numbers if clean_int(n, 0) > 0}
    if not cleared:
        return
    for content_id in sorted({clean_text(cid, 120) for cid in content_ids if clean_text(cid, 120)}):
        try:
            item = table.get_item(Key={"pk": content_pk(content_id), "sk": "METADATA"}).get("Item")
            if not item:
                continue
            assigned_raw = item.get("assignedPageNumbers") if isinstance(item.get("assignedPageNumbers"), list) else []
            assigned = sorted({clean_int(n, 0) for n in assigned_raw if clean_int(n, 0) > 0 and clean_int(n, 0) not in cleared})
            preferred = max(1, clean_int(item.get("preferredPageCount"), 1))
            if assigned:
                item["assignedPageNumbers"] = assigned
                item["placementStatus"] = "partially_placed" if len(assigned) < preferred else "placed"
                item["publicationStatus"] = "in_issue"
                item["issueId"] = issue_id or item.get("issueId") or "unassigned"
                mark_submission_used_for_content(item, issue_id, assigned)
            else:
                item["assignedPageNumbers"] = []
                item["placementStatus"] = "unplaced"
                item["publicationStatus"] = "pending"
                # Keep the issue association so issue-scoped content lists still show the item as pending/available.
                item["issueId"] = issue_id or item.get("issueId") or "unassigned"
                kind = clean_text(item.get("sourceSubmissionKind"), 80)
                sk = clean_text(item.get("sourceSubmissionSk"), 220)
                sid = clean_text(item.get("sourceSubmissionId"), 180)
                if kind and (sk or sid):
                    try:
                        submission = get_submission(kind, sid, sk)
                        mark_submission_record(submission, status="converted", publication_status="pending", content_item_id=content_id, issue_id=item.get("issueId"), placed_page_numbers=[])
                    except Exception as exc:
                        print(f"Could not mark submission pending after clearing {content_id}: {exc}")
            item["updatedAt"] = now_iso()
            item["gsi2pk"] = f"CONTENT_ISSUE#{item.get('issueId') or 'unassigned'}"
            item["gsi2sk"] = f"{item.get('status') or 'draft'}#{clean_int(item.get('priority'), 50):04d}#{item['updatedAt']}#{content_id}"
            table.put_item(Item=dynamodb_safe(item))
        except Exception as exc:
            print(f"Could not refresh content placement after page clear for {content_id}: {exc}")


def validate_page_count(page_count: int) -> None:
    if page_count < 4:
        raise ValueError("Page count must be at least 4.")
    if page_count % 4 != 0:
        raise ValueError("Page count must be a multiple of 4.")


def make_flatplan_page(num: int, page_count: int) -> Dict[str, Any]:
    if num == 1:
        page_type = "front_cover"
    elif num == page_count:
        page_type = "back_cover_ad"
    else:
        page_type = "mixed_content"
    page_item: Dict[str, Any] = {
        "pageNumber": num,
        "pageType": page_type,
        "templateId": page_type,
        "locked": num in (1, page_count),
        "contentSlots": [],
        "layoutSlots": [],
        "notes": "",
        "previewAssetId": "",
    }
    if num == 1:
        page_item["coverLayout"] = {
            "lrocName": "LROC",
            "lrocFontFamily": "Georgia, serif",
            "lrocPointSize": 72,
            "logoEnabled": True,
            "logoUrl": "assets/lroc-logo.png",
            "logoPosition": "custom",
            "logoWidthPercent": 18,
            "logoTopPercent": 3,
            "logoRightPercent": 5,
            "logoMaxHeightPercent": 24,
            "logoOpacityPercent": 100,
            "showRulers": False,
            "showTopRuler": False,
            "topBannerEnabled": True,
            "topBannerText": "Trips • Technical • Club news",
            "bottomBannerEnabled": True,
            "bottomBannerText": "Members, vehicles, events and adventures",
            "issueLabel": "Magazine issue",
            "siteUrl": "www.lroc.com.au",
        }
    return page_item


def make_flatplan(issue_id: str, page_count: int) -> Dict[str, Any]:
    pages = [make_flatplan_page(num, page_count) for num in range(1, page_count + 1)]
    return {
        "pk": issue_pk(issue_id),
        "sk": "FLATPLAN#CURRENT",
        "entityType": "Flatplan",
        "issueId": issue_id,
        "pageCount": page_count,
        "version": 1,
        "pages": pages,
        "generatedBy": "system",
        "generatedAt": now_iso(),
        "updatedAt": now_iso(),
    }


def resize_flatplan_preserve(issue_id: str, old_flatplan: Dict[str, Any], old_page_count: int, new_page_count: int) -> Dict[str, Any]:
    """Resize a flatplan without wiping already-composed pages.

    The magazine has to stay on a multiple-of-four page count, but increasing the
    count must not destroy the editor's flatplan.  Preserve cover and interior
    pages, move the system back-cover role to the new final page, and turn the
    former back cover into a normal blank interior page.
    """
    if not old_flatplan or not isinstance(old_flatplan.get("pages"), list):
        return make_flatplan(issue_id, new_page_count)
    now = now_iso()
    old_pages_by_no: Dict[int, Dict[str, Any]] = {}
    for raw_page in old_flatplan.get("pages") or []:
        if not isinstance(raw_page, dict):
            continue
        n = clean_int(raw_page.get("pageNumber"), 0)
        if n > 0:
            old_pages_by_no[n] = dict(raw_page)
    pages: List[Dict[str, Any]] = []
    for n in range(1, new_page_count + 1):
        if n == 1:
            page = old_pages_by_no.get(1, make_flatplan_page(1, new_page_count))
            page["pageNumber"] = 1
            page["pageType"] = "front_cover"
            page["templateId"] = "front_cover"
            page["locked"] = True
            if not isinstance(page.get("coverLayout"), dict):
                page["coverLayout"] = make_flatplan_page(1, new_page_count).get("coverLayout", {})
        elif n == new_page_count:
            old_back = old_pages_by_no.get(old_page_count, {}) if old_page_count and old_page_count != new_page_count else old_pages_by_no.get(n, {})
            page = make_flatplan_page(n, new_page_count)
            if isinstance(old_back, dict):
                # Keep any deliberate back-cover notes/layout metadata, but force the role/lock.
                for key in ("notes", "layoutSlots", "contentSlots", "previewAssetId"):
                    if key in old_back:
                        page[key] = old_back.get(key)
            page["pageType"] = "back_cover_ad"
            page["templateId"] = "back_cover_ad"
            page["locked"] = True
        else:
            page = old_pages_by_no.get(n)
            if not page:
                page = make_flatplan_page(n, new_page_count)
            page["pageNumber"] = n
            if n == old_page_count and old_page_count != new_page_count and str(page.get("pageType") or "") == "back_cover_ad":
                page = make_flatplan_page(n, new_page_count)
                page["pageType"] = "filler"
                page["templateId"] = "blank_page"
                page["locked"] = False
                page["notes"] = "Former back cover converted to a blank interior page when the magazine was expanded."
            elif str(page.get("pageType") or "") in {"front_cover", "back_cover_ad"}:
                page["pageType"] = "filler"
                page["templateId"] = "blank_page"
                page["locked"] = False
            else:
                page["locked"] = bool(page.get("locked", False))
        page["updatedAt"] = page.get("updatedAt") or now
        pages.append(page)
    return {
        **old_flatplan,
        "pk": issue_pk(issue_id),
        "sk": "FLATPLAN#CURRENT",
        "entityType": "Flatplan",
        "issueId": issue_id,
        "pageCount": new_page_count,
        "version": clean_int(old_flatplan.get("version"), 1) + 1,
        "pages": pages,
        "resizedAt": now,
        "updatedAt": now,
    }


def list_issues() -> Dict[str, Any]:
    ensure_table()
    result = table.query(
        IndexName="gsi1",
        KeyConditionExpression=Key("gsi1pk").eq("ISSUES")
    )
    items = sorted(result.get("Items", []), key=lambda x: str(x.get("updatedAt") or ""), reverse=True)
    return {"items": items}


def create_or_update_issue(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    issue_id = clean_text(payload.get("issueId") or payload.get("issue_id"), 80) or f"issue-{datetime.now(timezone.utc).strftime('%Y%m')}-{uuid.uuid4().hex[:8]}"
    page_count = clean_int(payload.get("pageCount") or payload.get("page_count"), 24)
    validate_page_count(page_count)
    existing = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "METADATA"}).get("Item") or {}
    created_at = existing.get("createdAt") or now_iso()
    item = {
        **existing,
        "pk": issue_pk(issue_id),
        "sk": "METADATA",
        "entityType": "MagazineIssue",
        "issueId": issue_id,
        "title": clean_text(payload.get("title"), 240) or existing.get("title") or "LROC Magazine",
        "issueNumber": clean_text(payload.get("issueNumber") or payload.get("issue_number"), 80) or existing.get("issueNumber") or "",
        "publicationMonth": clean_text(payload.get("publicationMonth") or payload.get("publication_month"), 40) or existing.get("publicationMonth") or "",
        "publicationYear": clean_text(payload.get("publicationYear") or payload.get("publication_year"), 10) or existing.get("publicationYear") or str(datetime.now(timezone.utc).year),
        "pageCount": page_count,
        "pageSize": clean_text(payload.get("pageSize") or payload.get("page_size"), 40) or existing.get("pageSize") or "A4",
        "orientation": clean_text(payload.get("orientation"), 40) or existing.get("orientation") or "portrait",
        "bleedMm": clean_int(payload.get("bleedMm") or payload.get("bleed_mm"), int(existing.get("bleedMm") or 3)),
        "marginTopMm": clean_int(payload.get("marginTopMm") or payload.get("margin_top_mm"), int(existing.get("marginTopMm") or 12)),
        "marginBottomMm": clean_int(payload.get("marginBottomMm") or payload.get("margin_bottom_mm"), int(existing.get("marginBottomMm") or 12)),
        "marginInsideMm": clean_int(payload.get("marginInsideMm") or payload.get("margin_inside_mm"), int(existing.get("marginInsideMm") or 12)),
        "marginOutsideMm": clean_int(payload.get("marginOutsideMm") or payload.get("margin_outside_mm"), int(existing.get("marginOutsideMm") or 12)),
        "coverImageAssetId": clean_text(payload.get("coverImageAssetId") or payload.get("cover_image_asset_id"), 120) or existing.get("coverImageAssetId") or "",
        "backCoverAdAssetId": clean_text(payload.get("backCoverAdAssetId") or payload.get("back_cover_ad_asset_id"), 120) or existing.get("backCoverAdAssetId") or "",
        "status": clean_text(payload.get("status"), 40) or existing.get("status") or "draft",
        "locked": bool(payload.get("locked") if "locked" in payload else existing.get("locked", False)),
        "createdAt": created_at,
        "createdBy": existing.get("createdBy") or user_id(c),
        "updatedAt": now_iso(),
        "updatedBy": user_id(c),
        "gsi1pk": "ISSUES",
        "gsi1sk": f"{clean_text(payload.get('publicationYear'), 10) or existing.get('publicationYear') or ''}#{clean_text(payload.get('publicationMonth'), 40) or existing.get('publicationMonth') or ''}#{issue_id}",
        "gsi2pk": f"ISSUE_STATUS#{clean_text(payload.get('status'), 40) or existing.get('status') or 'draft'}",
        "gsi2sk": f"{now_iso()}#{issue_id}",
    }
    table.put_item(Item=dynamodb_safe(item))
    old_page_count = clean_int(existing.get("pageCount"), 0)
    if not existing:
        table.put_item(Item=dynamodb_safe(make_flatplan(issue_id, page_count)))
    elif old_page_count != page_count:
        current_flatplan = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "FLATPLAN#CURRENT"}).get("Item") or {}
        table.put_item(Item=dynamodb_safe(resize_flatplan_preserve(issue_id, current_flatplan, old_page_count, page_count)))
    return {"item": item}


def get_issue(issue_id: str) -> Dict[str, Any]:
    ensure_table()
    meta = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "METADATA"}).get("Item")
    if not meta:
        raise FileNotFoundError("Magazine issue not found.")
    flatplan = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "FLATPLAN#CURRENT"}).get("Item")
    return {"item": meta, "flatplan": flatplan}


def allowed_mime(mime: str) -> bool:
    if not mime:
        return False
    return any(mime == prefix.rstrip("/") or mime.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES)




def magazine_asset_is_internal_metadata(item: Dict[str, Any]) -> bool:
    asset_type = str(item.get("assetType") or "").lower()
    material_type = str(item.get("materialType") or item.get("assetPurpose") or "").lower()
    source = str(item.get("source") or "").lower()
    return asset_type in {"advert_version_json", "advert_design_json", "metadata_json"} or material_type == "metadata" or source == "advert_builder_version_json"


def magazine_asset_is_image(item: Dict[str, Any]) -> bool:
    return str(item.get("mimeType") or "").lower().startswith("image/")


def magazine_asset_can_be_reused_by_hash(item: Dict[str, Any]) -> bool:
    """Reusable images are deduplicated by content hash. Immutable generated advert renders are deliberately excluded."""
    if not item or magazine_asset_is_internal_metadata(item):
        return False
    if not magazine_asset_is_image(item):
        return False
    if item.get("isAdvertRender"):
        return False
    if str(item.get("status") or "").lower() in {"deleted", "archived", "duplicate", "superseded"}:
        return False
    if item.get("hiddenInAssetGallery"):
        return False
    return bool(str(item.get("contentHash") or "").strip())


def magazine_asset_can_be_cleanup_candidate(item: Dict[str, Any]) -> bool:
    """Image assets that are safe to hash/compare for cleanup. Generated advert render versions are excluded."""
    if not item or magazine_asset_is_internal_metadata(item):
        return False
    if not magazine_asset_is_image(item):
        return False
    if item.get("isAdvertRender"):
        return False
    status = str(item.get("status") or "").lower()
    if status in {"deleted", "archived", "duplicate", "superseded"}:
        return False
    if item.get("hiddenInAssetGallery"):
        return False
    return True


def find_image_asset_by_hash(content_hash: str, *, include_hidden: bool = False, exclude_asset_id: str = "") -> Dict[str, Any]:
    h = clean_text(content_hash, 140)
    if not h:
        return {}
    ensure_table()
    result = table.query(IndexName="gsi1", KeyConditionExpression=Key("gsi1pk").eq("ASSETS"))
    candidates = []
    for item in result.get("Items", []):
        if exclude_asset_id and str(item.get("assetId") or "") == exclude_asset_id:
            continue
        if str(item.get("contentHash") or "").strip() != h:
            continue
        if magazine_asset_is_internal_metadata(item) or not magazine_asset_is_image(item) or item.get("isAdvertRender"):
            continue
        if not include_hidden and not magazine_asset_can_be_reused_by_hash(item):
            continue
        candidates.append(item)
    candidates.sort(key=lambda x: str(x.get("createdAt") or ""))
    return candidates[0] if candidates else {}


def find_reusable_image_asset_by_hash(content_hash: str, exclude_asset_id: str = "") -> Dict[str, Any]:
    return find_image_asset_by_hash(content_hash, include_hidden=False, exclude_asset_id=exclude_asset_id)


def cleanup_asset_dedupe_text(value: Any) -> str:
    text = clean_text(value, 260).lower().strip()
    text = re.sub(r"\.[a-z0-9]{2,8}$", "", text)
    text = re.sub(r"\b(copy|duplicate|final|edited|normalised|normalized|source|image|asset)\b", " ", text)
    text = re.sub(r"[-_()\[\]{}]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def cleanup_duplicate_group_keys(item: Dict[str, Any]) -> List[str]:
    """Return conservative duplicate keys for reusable image assets.

    Byte hashes are best, but old advert-builder/source-image records may have been re-saved
    before hashing was consistent. The fallback keys catch the common gallery mess without
    touching immutable advert renders. They only hide duplicates; they do not delete S3 files.
    """
    keys: List[str] = []
    h = str(item.get("contentHash") or item.get("sourceImageContentHash") or "").strip()
    if h:
        keys.append(f"hash#{h}")
    bucket = clean_text(item.get("s3Bucket") or ASSETS_BUCKET, 240)
    s3_key = clean_text(item.get("s3Key"), 1000)
    if bucket and s3_key:
        keys.append(f"s3#{bucket}/{s3_key}")
    size = clean_int(item.get("fileSizeBytes"), 0)
    mime = clean_text(item.get("mimeType"), 160).lower()
    if size and mime:
        for name in (item.get("originalFileName"), item.get("fileName"), item.get("title"), item.get("displayName")):
            cleaned = cleanup_asset_dedupe_text(name)
            if cleaned and len(cleaned) >= 3:
                keys.append(f"name-size#{cleaned}#{mime}#{size}")
    return list(dict.fromkeys(keys))


def cleanup_duplicate_image_assets(event: Dict[str, Any]) -> Dict[str, Any]:
    """Mark duplicate reusable image assets as duplicate without deleting S3 objects.

    Cleanup now has two passes:
    1. Calculate SHA-256 hashes for older image assets when possible.
    2. Hide later duplicate records by hash, exact S3 object, or conservative filename/title+size keys.

    Generated advert render versions remain excluded because published/draft issues may need their
    exact immutable PNG UUID.
    """
    ensure_table()
    require_editor(event)
    result = table.query(IndexName="gsi1", KeyConditionExpression=Key("gsi1pk").eq("ASSETS"))
    now = now_iso()
    max_hash_bytes = int(os.environ.get("MAGAZINE_CLEANUP_HASH_MAX_BYTES", str(25 * 1024 * 1024)))
    candidates: List[Dict[str, Any]] = []
    groups: Dict[str, List[Dict[str, Any]]] = {}
    hashes_calculated = 0
    skipped_too_large = 0
    skipped_missing_file = 0

    for item in result.get("Items", []):
        if not magazine_asset_can_be_cleanup_candidate(item):
            continue
        asset_id = str(item.get("assetId") or "")
        h = str(item.get("contentHash") or "").strip()
        if not h:
            bucket = clean_text(item.get("s3Bucket") or ASSETS_BUCKET, 240)
            key = clean_text(item.get("s3Key"), 1000)
            if not bucket or not key:
                skipped_missing_file += 1
            else:
                size_hint = clean_int(item.get("fileSizeBytes"), 0)
                if size_hint and size_hint > max_hash_bytes:
                    skipped_too_large += 1
                else:
                    try:
                        obj = s3.get_object(Bucket=bucket, Key=key)
                        content_length = int(obj.get("ContentLength") or 0)
                        if content_length and content_length > max_hash_bytes:
                            skipped_too_large += 1
                        else:
                            hasher = hashlib.sha256()
                            total = 0
                            body = obj["Body"]
                            while True:
                                chunk = body.read(1024 * 1024)
                                if not chunk:
                                    break
                                total += len(chunk)
                                if total > max_hash_bytes:
                                    skipped_too_large += 1
                                    h = ""
                                    break
                                hasher.update(chunk)
                            if not h:
                                h = hasher.hexdigest() if total else ""
                            if h and asset_id:
                                table.update_item(
                                    Key={"pk": asset_pk(asset_id), "sk": "METADATA"},
                                    UpdateExpression="SET contentHash = :hash, hashCalculatedAt = :now, updatedAt = :now",
                                    ExpressionAttributeValues={":hash": h, ":now": now},
                                )
                                item["contentHash"] = h
                                hashes_calculated += 1
                    except Exception as exc:
                        print(f"Could not hash asset {asset_id}: {exc}")
                        skipped_missing_file += 1
        candidates.append(item)
        for key in cleanup_duplicate_group_keys(item):
            groups.setdefault(key, []).append(item)

    duplicate_to_canonical: Dict[str, Dict[str, str]] = {}
    for key, items in groups.items():
        unique = {str(item.get("assetId") or ""): item for item in items if item.get("assetId")}
        if len(unique) < 2:
            continue
        ordered = sorted(unique.values(), key=lambda x: (str(x.get("createdAt") or ""), str(x.get("assetId") or "")))
        canonical = ordered[0]
        canonical_id = str(canonical.get("assetId") or "")
        if not canonical_id:
            continue
        for duplicate in ordered[1:]:
            duplicate_id = str(duplicate.get("assetId") or "")
            if not duplicate_id or duplicate_id in duplicate_to_canonical:
                continue
            duplicate_to_canonical[duplicate_id] = {"duplicateOfAssetId": canonical_id, "dedupeKey": key}

    marked = []
    for duplicate_id, info in duplicate_to_canonical.items():
        table.update_item(
            Key={"pk": asset_pk(duplicate_id), "sk": "METADATA"},
            UpdateExpression="SET #status = :status, duplicateOfAssetId = :canonical, hiddenInAssetGallery = :true, updatedAt = :now, duplicateCleanupAt = :now, duplicateCleanupKey = :dedupeKey",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": "duplicate", ":canonical": info["duplicateOfAssetId"], ":true": True, ":now": now, ":dedupeKey": info["dedupeKey"]},
        )
        marked.append({"assetId": duplicate_id, **info})
    return {
        "candidateImages": len(candidates),
        "duplicateGroups": sum(1 for items in groups.values() if len({str(item.get("assetId") or "") for item in items if item.get("assetId")}) > 1),
        "duplicatesMarked": len(marked),
        "hashesCalculated": hashes_calculated,
        "skippedTooLarge": skipped_too_large,
        "skippedMissingFile": skipped_missing_file,
        "items": marked,
    }


def asset_reference_labels(asset_id: str) -> List[str]:
    labels: List[str] = []
    if not asset_id:
        return labels
    try:
        all_assets = table.query(IndexName="gsi1", KeyConditionExpression=Key("gsi1pk").eq("ASSETS")).get("Items", [])
    except Exception:
        all_assets = []
    for asset in all_assets:
        status = str(asset.get("status") or "").lower()
        if status in {"deleted", "duplicate", "superseded"}:
            continue
        current_id = str(asset.get("assetId") or "")
        for field in ("sourceImageAssetId", "sourcePdfAssetId", "currentRenderAssetId", "baseRenderAssetId", "advertVersionMetadataAssetId"):
            if str(asset.get(field) or "") == asset_id:
                labels.append(f"asset {current_id} references this as {field}")
        inline_meta = str(asset.get("advertVersionMetadataJson") or "")
        if inline_meta and asset_id in inline_meta:
            labels.append(f"advert metadata {current_id} references this asset")
    try:
        issues = table.query(IndexName="gsi1", KeyConditionExpression=Key("gsi1pk").eq("ISSUES")).get("Items", [])
    except Exception:
        issues = []
    for issue in issues:
        issue_id = str(issue.get("issueId") or "")
        if str(issue.get("coverImageAssetId") or "") == asset_id:
            labels.append(f"issue {issue_id} front cover")
        if str(issue.get("backCoverAdAssetId") or "") == asset_id:
            labels.append(f"issue {issue_id} back cover")
        if issue_id:
            try:
                flatplan = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "FLATPLAN#CURRENT"}).get("Item") or {}
                for page in flatplan.get("pages") or []:
                    for slot in page.get("layoutSlots") or []:
                        if str(slot.get("assetId") or "") == asset_id:
                            labels.append(f"issue {issue_id} page {page.get('pageNumber')} slot")
            except Exception as exc:
                print(f"Could not inspect flatplan references for issue {issue_id}: {exc}")
    return labels


def delete_asset_completely(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    asset_id = clean_text(payload.get("assetId") or payload.get("asset_id"), 120)
    delete_file = clean_bool(payload.get("deleteFile") if "deleteFile" in payload else payload.get("delete_file"), True)
    if not asset_id:
        raise ValueError("assetId is required.")
    item = table.get_item(Key={"pk": asset_pk(asset_id), "sk": "METADATA"}).get("Item")
    if not item:
        raise FileNotFoundError("Asset was not found.")
    if magazine_asset_is_internal_metadata(item):
        raise ValueError("Internal metadata records cannot be deleted from the gallery.")
    if item.get("isAdvertRender"):
        raise ValueError("Generated advert render versions are immutable. Archive/hide them, but do not delete them completely.")
    refs = asset_reference_labels(asset_id)
    if refs:
        raise ValueError("This asset is still referenced and was not deleted: " + "; ".join(refs[:8]))
    bucket = clean_text(item.get("s3Bucket") or ASSETS_BUCKET, 240)
    key = clean_text(item.get("s3Key"), 1000)
    deleted_file = False
    if delete_file and bucket and key:
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            deleted_file = True
        except ClientError as exc:
            raise RuntimeError(f"Could not delete S3 object for asset {asset_id}: {exc}") from exc
    table.delete_item(Key={"pk": asset_pk(asset_id), "sk": "METADATA"})
    return {"deleted": True, "assetId": asset_id, "deletedFile": deleted_file, "deletedBy": user_id(c), "deletedAt": now_iso()}

def create_upload_url(event: Dict[str, Any]) -> Dict[str, Any]:
    require_editor(event)
    if not ASSETS_BUCKET:
        raise RuntimeError("MAGAZINE_ASSETS_BUCKET is not configured.")
    payload = parse_body(event)
    file_name = clean_text(payload.get("fileName") or payload.get("filename"), 240) or "upload.bin"
    mime_type = clean_text(payload.get("mimeType") or payload.get("mime_type"), 160) or "application/octet-stream"
    file_size = clean_int(payload.get("fileSizeBytes") or payload.get("file_size_bytes"), 0)
    asset_type = clean_text(payload.get("assetType") or payload.get("asset_type"), 80) or "asset"
    issue_id = clean_text(payload.get("issueId") or payload.get("issue_id"), 80) or "unassigned"
    if file_size and file_size > MAX_UPLOAD_BYTES:
        raise ValueError(f"File is larger than the configured magazine upload limit of {MAX_UPLOAD_BYTES} bytes.")
    if not allowed_mime(mime_type):
        raise ValueError("This file type is not currently allowed for magazine production uploads.")
    content_hash = clean_text(payload.get("contentHash") or payload.get("content_hash") or payload.get("sha256"), 140)
    # If the client already calculated a hash for an image upload, avoid creating another S3 object.
    # Generated advert render versions deliberately do not pass contentHash, because those immutable PNG
    # versions must remain separately addressable for issue history.
    if content_hash and mime_type.lower().startswith("image/"):
        existing = find_reusable_image_asset_by_hash(content_hash)
        if existing:
            return {"reuseAsset": True, "assetId": existing.get("assetId"), "existingAsset": asset_with_view_url(existing), "maxUploadBytes": MAX_UPLOAD_BYTES}
    asset_id = f"asset-{uuid.uuid4().hex}"
    safe_name = file_name.replace("/", "_").replace("\\", "_")
    key = f"{ASSETS_PREFIX}issues/{issue_id}/uploads/{asset_id}/{safe_name}"
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": ASSETS_BUCKET, "Key": key, "ContentType": mime_type},
        ExpiresIn=UPLOAD_EXPIRY_SECONDS,
    )
    return {"assetId": asset_id, "bucket": ASSETS_BUCKET, "key": key, "uploadUrl": url, "expiresIn": UPLOAD_EXPIRY_SECONDS, "maxUploadBytes": MAX_UPLOAD_BYTES}



def mark_previous_advert_versions_not_current(design_id: str, keep_asset_id: str) -> None:
    """Keep the editor-facing advert library on the latest version while preserving immutable render assets."""
    if not design_id or not keep_asset_id:
        return
    try:
        result = table.query(IndexName="gsi1", KeyConditionExpression=Key("gsi1pk").eq("ASSETS"))
        for old in result.get("Items", []):
            if old.get("assetId") == keep_asset_id:
                continue
            if old.get("advertDesignId") != design_id:
                continue
            if not old.get("isAdvertRender"):
                continue
            table.update_item(
                Key={"pk": asset_pk(str(old.get("assetId") or "")), "sk": "METADATA"},
                UpdateExpression="SET isCurrentAdvertVersion = :false, updatedAt = :now",
                ExpressionAttributeValues={":false": False, ":now": now_iso()},
            )
    except Exception as exc:
        print(f"Could not mark previous advert versions for {design_id}: {exc}")

def confirm_upload(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    asset_id = clean_text(payload.get("assetId") or payload.get("asset_id"), 120)
    key = clean_text(payload.get("key"), 1000)
    if not asset_id or not key:
        raise ValueError("assetId and key are required.")
    try:
        head = s3.head_object(Bucket=ASSETS_BUCKET, Key=key)
    except ClientError as exc:
        raise FileNotFoundError("Uploaded object was not found in S3.") from exc
    size = int(head.get("ContentLength") or 0)
    if size > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded object exceeds configured magazine asset size limit.")
    file_name = clean_text(payload.get("fileName") or key.rsplit("/", 1)[-1], 240)
    mime_type = clean_text(payload.get("mimeType") or head.get("ContentType"), 160)
    asset_type = clean_text(payload.get("assetType") or payload.get("asset_type"), 80) or "asset"
    material_type = infer_material_type(asset_type, file_name, mime_type, payload.get("materialType") or payload.get("material_type"))
    status = clean_text(payload.get("status"), 40) or ("active" if material_type == "advert" else "available")
    item = {
        "pk": asset_pk(asset_id),
        "sk": "METADATA",
        "entityType": "MagazineAsset",
        "assetId": asset_id,
        "s3Bucket": ASSETS_BUCKET,
        "s3Key": key,
        "fileName": file_name,
        "mimeType": mime_type,
        "fileSizeBytes": size,
        "assetType": asset_type,
        "materialType": material_type,
        "issueId": clean_text(payload.get("issueId") or payload.get("issue_id"), 80) or "unassigned",
        "title": clean_text(payload.get("title") or payload.get("assetTitle") or payload.get("advertTitle"), 240),
        "advertiserName": clean_text(payload.get("advertiserName") or payload.get("advertiser_name") or payload.get("businessName"), 180),
        "sizeType": clean_text(payload.get("sizeType") or payload.get("advertSizeType") or payload.get("size_type"), 80),
        "advertSizeType": clean_text(payload.get("advertSizeType") or payload.get("sizeType") or payload.get("advert_size_type"), 80),
        "orientation": clean_text(payload.get("orientation"), 40),
        "expiryDate": clean_text(payload.get("expiryDate") or payload.get("expiry_date"), 40),
        "layoutTemplate": clean_text(payload.get("layoutTemplate") or payload.get("layout_template"), 100),
        "bodyText": clean_text(payload.get("bodyText") or payload.get("body_text"), 4000),
        "contactDetails": clean_text(payload.get("contactDetails") or payload.get("contact_details"), 1200),
        "notes": clean_text(payload.get("notes"), 2000),
        "source": clean_text(payload.get("source"), 80) or "editor_upload",
        "sourcePdfAssetId": clean_text(payload.get("sourcePdfAssetId") or payload.get("source_pdf_asset_id"), 120),
        "originalSourcePath": clean_text(payload.get("originalSourcePath") or payload.get("original_source_path"), 1000),
        "generatedImagePath": clean_text(payload.get("generatedImagePath") or payload.get("generated_image_path"), 1000),
        "logoPath": clean_text(payload.get("logoPath") or payload.get("logo_path"), 1000),
        "displayName": clean_text(payload.get("displayName") or payload.get("display_name") or payload.get("title"), 240),
        "contentHash": clean_text(payload.get("contentHash") or payload.get("content_hash") or payload.get("sha256"), 140),
        "originalFileName": clean_text(payload.get("originalFileName") or payload.get("original_file_name"), 240),
        "headline": clean_text(payload.get("headline"), 1200),
        "bodyCopy": clean_text(payload.get("bodyCopy") or payload.get("body_copy"), 4000),
        "washColor": clean_text(payload.get("washColor") or payload.get("wash_color"), 40),
        "washStrength": clean_int(payload.get("washStrength") or payload.get("wash_strength"), 0),
        "borderColor": clean_text(payload.get("borderColor") or payload.get("border_color"), 40),
        "showInnerBoxes": clean_bool(payload.get("showInnerBoxes") or payload.get("show_inner_boxes"), False),
        "headerPct": clean_decimal(payload.get("headerPct") or payload.get("header_pct"), "0"),
        "imagePct": clean_decimal(payload.get("imagePct") or payload.get("image_pct"), "0"),
        "imageWidthPct": clean_decimal(payload.get("imageWidthPct") or payload.get("image_width_pct"), "0"),
        "contactPct": clean_decimal(payload.get("contactPct") or payload.get("contact_pct"), "0"),
        "paddingPct": clean_decimal(payload.get("paddingPct") or payload.get("padding_pct"), "0"),
        "gapPct": clean_decimal(payload.get("gapPct") or payload.get("gap_pct"), "0"),
        "borderWidth": clean_int(payload.get("borderWidth") or payload.get("border_width"), 0),
        "businessFontSize": clean_int(payload.get("businessFontSize") or payload.get("business_font_size"), 0),
        "headlineFontSize": clean_int(payload.get("headlineFontSize") or payload.get("headline_font_size"), 0),
        "bodyFontSize": clean_int(payload.get("bodyFontSize") or payload.get("body_font_size"), 0),
        "contactFontSize": clean_int(payload.get("contactFontSize") or payload.get("contact_font_size"), 0),
        "sourceImageAssetId": clean_text(payload.get("sourceImageAssetId") or payload.get("source_image_asset_id"), 120),
        "sourceImageContentHash": clean_text(payload.get("sourceImageContentHash") or payload.get("source_image_content_hash"), 140),
        "advertDesignId": clean_text(payload.get("advertDesignId") or payload.get("advert_design_id"), 140),
        "advertVersionNumber": clean_int(payload.get("advertVersionNumber") or payload.get("advert_version_number"), 0),
        "advertVersionLabel": clean_text(payload.get("advertVersionLabel") or payload.get("advert_version_label"), 60),
        "advertVersionSortKey": clean_text(payload.get("advertVersionSortKey") or payload.get("advert_version_sort_key"), 120),
        "isAdvertRender": clean_bool(payload.get("isAdvertRender") or payload.get("is_advert_render"), False),
        "isCurrentAdvertVersion": clean_bool(payload.get("isCurrentAdvertVersion") or payload.get("is_current_advert_version"), False),
        "baseRenderAssetId": clean_text(payload.get("baseRenderAssetId") or payload.get("base_render_asset_id"), 120),
        "currentRenderAssetId": clean_text(payload.get("currentRenderAssetId") or payload.get("current_render_asset_id"), 120),
        "advertVersionMetadataAssetId": clean_text(payload.get("advertVersionMetadataAssetId") or payload.get("advert_version_metadata_asset_id"), 120),
        "advertVersionMetadataPath": clean_text(payload.get("advertVersionMetadataPath") or payload.get("advert_version_metadata_path"), 1000),
        "advertVersionMetadataJson": clean_text(payload.get("advertVersionMetadataJson") or payload.get("advert_version_metadata_json"), 120000),
        "active": bool(payload.get("active", True)),
        "status": status,
        "createdAt": now_iso(),
        "createdBy": user_id(c),
        "updatedAt": now_iso(),
        "gsi1pk": "ASSETS",
        "gsi1sk": f"{now_iso()}#{asset_id}",
        "gsi2pk": f"ASSET_TYPE#{asset_type}",
        "gsi2sk": f"{now_iso()}#{asset_id}",
        "gsi3pk": f"MATERIAL_TYPE#{material_type}",
        "gsi3sk": f"{now_iso()}#{asset_id}",
    }
    table.put_item(Item=dynamodb_safe(item))
    if item.get("advertDesignId") and item.get("isAdvertRender") and item.get("isCurrentAdvertVersion"):
        mark_previous_advert_versions_not_current(str(item.get("advertDesignId") or ""), asset_id)
    return {"item": item}



def get_asset_file_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """Return a same-origin data URL for an image asset so canvas editing does not depend on S3/CORS image loading.

    This is intended for editor previews/source images, not large magazine PDFs. Direct S3 URLs remain
    the normal path for opening/downloading assets.
    """
    ensure_table()
    require_editor(event)
    params = event.get("queryStringParameters") or {}
    asset_id = clean_text(params.get("assetId") or params.get("asset_id"), 120)
    content_hash = clean_text(params.get("contentHash") or params.get("content_hash") or params.get("sha256"), 140)
    if asset_id:
        item = table.get_item(Key={"pk": asset_pk(asset_id), "sk": "METADATA"}).get("Item")
    elif content_hash:
        item = find_image_asset_by_hash(content_hash, include_hidden=True)
        asset_id = clean_text(item.get("assetId"), 120) if item else ""
    else:
        raise ValueError("assetId or contentHash is required.")
    if not item:
        raise FileNotFoundError("Asset was not found.")
    mime_type = clean_text(item.get("mimeType"), 160).lower()
    if not mime_type.startswith("image/"):
        raise ValueError("Only image assets can be loaded into the advert editor preview.")
    bucket = clean_text(item.get("s3Bucket") or ASSETS_BUCKET, 240)
    key = clean_text(item.get("s3Key"), 1000)
    if not bucket or not key:
        raise FileNotFoundError("Asset storage location is missing.")
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()
    # API Gateway/Lambda responses have practical payload limits. Large source images should still
    # exist in S3 and can be replaced/re-uploaded, but the editor should not try to inline huge files.
    max_inline = int(os.environ.get("MAGAZINE_INLINE_IMAGE_MAX_BYTES", str(4 * 1024 * 1024)))
    if len(data) > max_inline:
        raise ValueError("This source image is too large to inline into the editor preview. Reselect the image once so the advert builder can save a normalised editable working copy.")
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "assetId": asset_id,
        "fileName": clean_text(item.get("fileName"), 240),
        "title": clean_text(item.get("title") or item.get("displayName"), 240),
        "mimeType": mime_type,
        "contentHash": clean_text(item.get("contentHash"), 140),
        "fileSizeBytes": len(data),
        "dataUrl": f"data:{mime_type};base64,{encoded}",
    }

def asset_with_view_url(asset: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(asset or {})
    key = str(item.get("s3Key") or "").strip()
    bucket = str(item.get("s3Bucket") or ASSETS_BUCKET).strip()
    mime = str(item.get("mimeType") or "").lower()
    if bucket and key and (mime.startswith("image/") or mime == "application/pdf"):
        try:
            item["viewUrl"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=min(UPLOAD_EXPIRY_SECONDS, 3600),
            )
            item["viewUrlExpiresIn"] = min(UPLOAD_EXPIRY_SECONDS, 3600)
        except Exception as exc:
            print(f"Could not create magazine asset view URL for {item.get('assetId')}: {exc}")
    return item


def list_assets() -> Dict[str, Any]:
    ensure_table()
    result = table.query(IndexName="gsi1", KeyConditionExpression=Key("gsi1pk").eq("ASSETS"))
    items = sorted(result.get("Items", []), key=lambda x: str(x.get("createdAt") or ""), reverse=True)
    return {"items": [asset_with_view_url(item) for item in items], "maxUploadBytes": MAX_UPLOAD_BYTES}




def content_summary_for_slot(content: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "contentItemId": content.get("contentItemId") or "",
        "title": content.get("title") or "Untitled content",
        "contentType": content.get("contentType") or "article",
        "authorName": content.get("authorName") or "",
        "status": content.get("status") or "draft",
    }


def list_content(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    params = event.get("queryStringParameters") or {}
    content_id = clean_text(params.get("contentItemId") or params.get("content_id"), 120)
    if content_id:
        item = table.get_item(Key={"pk": content_pk(content_id), "sk": "METADATA"}).get("Item")
        if not item:
            raise FileNotFoundError("Magazine content item not found.")
        return {"item": item}
    issue_id = clean_text(params.get("issueId") or params.get("issue_id"), 80)
    if issue_id:
        result = table.query(IndexName="gsi2", KeyConditionExpression=Key("gsi2pk").eq(f"CONTENT_ISSUE#{issue_id}"))
    else:
        result = table.query(IndexName="gsi1", KeyConditionExpression=Key("gsi1pk").eq("CONTENT"))
    items = sorted(result.get("Items", []), key=lambda x: str(x.get("updatedAt") or x.get("createdAt") or ""), reverse=True)
    return {"items": items}


def create_or_update_content(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    content_id = clean_text(payload.get("contentItemId") or payload.get("content_id"), 120) or f"content-{uuid.uuid4().hex}"
    existing = table.get_item(Key={"pk": content_pk(content_id), "sk": "METADATA"}).get("Item") or {}
    issue_id = clean_text(payload.get("issueId") or payload.get("issue_id"), 80) or existing.get("issueId") or "unassigned"
    status = clean_text(payload.get("status"), 40) or existing.get("status") or "draft"
    content_type = clean_text(payload.get("contentType") or payload.get("content_type"), 80) or existing.get("contentType") or "article"
    priority = clean_int(payload.get("priority"), int(existing.get("priority") or 50))
    item = {
        **existing,
        "pk": content_pk(content_id),
        "sk": "METADATA",
        "entityType": "MagazineContentItem",
        "contentItemId": content_id,
        "title": clean_text(payload.get("title"), 240) or existing.get("title") or "Untitled content",
        "subtitle": clean_text(payload.get("subtitle"), 300) or existing.get("subtitle") or "",
        "authorName": clean_text(payload.get("authorName") or payload.get("author_name"), 180) or existing.get("authorName") or "",
        "source": clean_text(payload.get("source"), 80) or existing.get("source") or "manual",
        "contentType": content_type,
        "bodyMarkdown": clean_extracted_text(payload.get("bodyMarkdown") or payload.get("body_markdown"), 60000) or existing.get("bodyMarkdown") or "",
        "bodyHtml": clean_article_html(payload.get("bodyHtml") or payload.get("body_html"), 120000) or existing.get("bodyHtml") or "",
        "editorFormat": clean_text(payload.get("editorFormat") or payload.get("editor_format"), 80) or existing.get("editorFormat") or "plain_text",
        "notes": clean_text(payload.get("notes"), 4000) or existing.get("notes") or "",
        "assetIds": payload.get("assetIds") if isinstance(payload.get("assetIds"), list) else existing.get("assetIds", []),
        "issueId": issue_id,
        "placementStatus": clean_text(payload.get("placementStatus") or payload.get("placement_status"), 40) or existing.get("placementStatus") or "unplaced",
        "publicationStatus": clean_text(payload.get("publicationStatus") or payload.get("publication_status"), 40) or existing.get("publicationStatus") or ("in_issue" if existing.get("placementStatus") == "placed" else "pending"),
        "sourceSubmissionKind": clean_text(payload.get("sourceSubmissionKind") or payload.get("source_submission_kind"), 80) or existing.get("sourceSubmissionKind") or "",
        "sourceSubmissionId": clean_text(payload.get("sourceSubmissionId") or payload.get("source_submission_id"), 160) or existing.get("sourceSubmissionId") or "",
        "sourceSubmissionSk": clean_text(payload.get("sourceSubmissionSk") or payload.get("source_submission_sk"), 220) or existing.get("sourceSubmissionSk") or "",
        "sourceMessageId": clean_text(payload.get("sourceMessageId") or payload.get("source_message_id"), 180) or existing.get("sourceMessageId") or "",
        "sourceFileName": clean_text(payload.get("sourceFileName") or payload.get("source_file_name"), 240) or existing.get("sourceFileName") or "",
        "sourceFormat": clean_text(payload.get("sourceFormat") or payload.get("source_format"), 40) or existing.get("sourceFormat") or "",
        "sourceAssetId": clean_text(payload.get("sourceAssetId") or payload.get("source_asset_id"), 120) or existing.get("sourceAssetId") or "",
        "extractionStatus": clean_text(payload.get("extractionStatus") or payload.get("extraction_status"), 40) or existing.get("extractionStatus") or "not_available",
        "extractionMessage": clean_text(payload.get("extractionMessage") or payload.get("extraction_message"), 500) or existing.get("extractionMessage") or "",
        "extractedCharacterCount": clean_int(payload.get("extractedCharacterCount") or payload.get("extracted_character_count"), int(existing.get("extractedCharacterCount") or 0)),
        "extractedImageCount": clean_int(payload.get("extractedImageCount") or payload.get("extracted_image_count"), int(existing.get("extractedImageCount") or 0)),
        "extractedImageAssetIds": payload.get("extractedImageAssetIds") if isinstance(payload.get("extractedImageAssetIds"), list) else existing.get("extractedImageAssetIds", []),
        "sourcePages": payload.get("sourcePages") if isinstance(payload.get("sourcePages"), list) else existing.get("sourcePages", []),
        "sourceBlocks": payload.get("sourceBlocks") if isinstance(payload.get("sourceBlocks"), list) else existing.get("sourceBlocks", []),
        "sourcePageCount": clean_int(payload.get("sourcePageCount") or payload.get("source_page_count"), int(existing.get("sourcePageCount") or 0)),
        "sourceLayoutStatus": clean_text(payload.get("sourceLayoutStatus") or payload.get("source_layout_status"), 40) or existing.get("sourceLayoutStatus") or "not_available",
        "sourceColumnCount": clean_int(payload.get("sourceColumnCount") or payload.get("source_column_count"), int(existing.get("sourceColumnCount") or 1)),
        "editorColumnCount": clean_int(payload.get("editorColumnCount") or payload.get("editor_column_count"), int(existing.get("editorColumnCount") or payload.get("sourceColumnCount") or 1)),
        "assignedPageNumbers": payload.get("assignedPageNumbers") if isinstance(payload.get("assignedPageNumbers"), list) else existing.get("assignedPageNumbers", []),
        "priority": priority,
        "preferredPageCount": clean_int(payload.get("preferredPageCount") or payload.get("preferred_page_count"), int(existing.get("preferredPageCount") or 1)),
        "minPageCount": clean_int(payload.get("minPageCount") or payload.get("min_page_count"), int(existing.get("minPageCount") or 1)),
        "maxPageCount": clean_int(payload.get("maxPageCount") or payload.get("max_page_count"), int(existing.get("maxPageCount") or 4)),
        "status": status,
        "createdAt": existing.get("createdAt") or now_iso(),
        "createdBy": existing.get("createdBy") or user_id(c),
        "updatedAt": now_iso(),
        "updatedBy": user_id(c),
        "gsi1pk": "CONTENT",
        "gsi1sk": f"{status}#{priority:04d}#{now_iso()}#{content_id}",
        "gsi2pk": f"CONTENT_ISSUE#{issue_id}",
        "gsi2sk": f"{status}#{priority:04d}#{now_iso()}#{content_id}",
    }
    table.put_item(Item=dynamodb_safe(item))
    return {"item": item}


def archive_content_item(event: Dict[str, Any]) -> Dict[str, Any]:
    """Soft-delete an unplaced/unpublished article/content copy.

    This deliberately does not purge source assets. It makes accidental duplicate
    editor copies inactive while protecting anything already placed or published.
    """
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    content_id = clean_text(payload.get("contentItemId") or payload.get("content_id"), 120)
    if not content_id:
        raise ValueError("contentItemId is required.")
    item = table.get_item(Key={"pk": content_pk(content_id), "sk": "METADATA"}).get("Item")
    if not item:
        raise FileNotFoundError("Magazine content item not found.")
    placement_status = str(item.get("placementStatus") or "").lower()
    publication_status = str(item.get("publicationStatus") or "").lower()
    status = str(item.get("status") or "").lower()
    assigned_pages = item.get("assignedPageNumbers") if isinstance(item.get("assignedPageNumbers"), list) else []
    if placement_status in {"placed", "partially_placed"} or publication_status in {"in_issue", "published"} or assigned_pages:
        raise ValueError("This article is already placed or published. Remove it from the issue before deleting the copy.")
    if status in {"archived", "deleted"} or publication_status == "archived":
        return {"item": item, "alreadyArchived": True}
    now = now_iso()
    priority = clean_int(item.get("priority"), 50)
    issue_id = clean_text(item.get("issueId"), 80) or "unassigned"
    archived = {
        **item,
        "status": "archived",
        "publicationStatus": "archived",
        "placementStatus": item.get("placementStatus") or "unplaced",
        "archivedAt": now,
        "archivedBy": user_id(c),
        "updatedAt": now,
        "updatedBy": user_id(c),
        "gsi1pk": "CONTENT",
        "gsi1sk": f"archived#{priority:04d}#{now}#{content_id}",
        "gsi2pk": f"CONTENT_ISSUE#{issue_id}",
        "gsi2sk": f"archived#{priority:04d}#{now}#{content_id}",
    }
    table.put_item(Item=dynamodb_safe(archived))
    return {"item": archived, "archived": True}

def place_content_on_page(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    require_editor(event)
    payload = parse_body(event)
    issue_id = clean_text(payload.get("issueId") or payload.get("issue_id"), 80)
    content_id = clean_text(payload.get("contentItemId") or payload.get("content_id"), 120)
    page_number = clean_int(payload.get("pageNumber") or payload.get("page_number"), 0)
    slot_type = clean_text(payload.get("slotType") or payload.get("slot_type"), 80) or "content"
    if not issue_id or not content_id or page_number < 1:
        raise ValueError("issueId, contentItemId and pageNumber are required.")
    issue = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "METADATA"}).get("Item")
    if not issue:
        raise FileNotFoundError("Magazine issue not found.")
    page_count = clean_int(issue.get("pageCount"), 0)
    if page_number < 1 or page_number > page_count:
        raise ValueError("Page number is outside the issue page range.")
    if page_number in (1, page_count):
        raise ValueError("Page 1 and the final back-cover page are locked by rule.")
    content = table.get_item(Key={"pk": content_pk(content_id), "sk": "METADATA"}).get("Item")
    if not content:
        raise FileNotFoundError("Magazine content item not found.")
    flat = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "FLATPLAN#CURRENT"}).get("Item") or make_flatplan(issue_id, page_count)
    pages = flat.get("pages") if isinstance(flat.get("pages"), list) else []
    if not pages:
        pages = make_flatplan(issue_id, page_count)["pages"]
    slot_id = f"slot-{uuid.uuid4().hex[:10]}"
    slot = {
        "slotId": slot_id,
        "slotType": slot_type,
        "contentItemId": content_id,
        "title": content.get("title") or "Untitled content",
        "contentType": content.get("contentType") or "article",
        "assetId": clean_text(payload.get("assetId") or payload.get("asset_id"), 120),
        "textOverride": clean_text(payload.get("textOverride") or payload.get("text_override"), 2000),
        "placedAt": now_iso(),
    }
    for page in pages:
        if clean_int(page.get("pageNumber"), 0) == page_number:
            slots = page.get("contentSlots") if isinstance(page.get("contentSlots"), list) else []
            # Avoid duplicate content on the same page if the editor clicks twice.
            slots = [existing for existing in slots if existing.get("contentItemId") != content_id]
            slots.append(slot)
            page["contentSlots"] = slots
            page["pageType"] = page.get("pageType") if page.get("pageType") not in {"mixed_content", "filler", ""} else content.get("contentType") or "mixed_content"
            page["updatedAt"] = now_iso()
            break
    flat["pages"] = pages
    flat["updatedAt"] = now_iso()
    flat["version"] = clean_int(flat.get("version"), 1) + 1
    table.put_item(Item=dynamodb_safe(flat))
    assigned = list(content.get("assignedPageNumbers") or [])
    if page_number not in assigned:
        assigned.append(page_number)
    preferred_pages = max(1, clean_int(content.get("preferredPageCount"), 1))
    placement_status = "partially_placed" if len(set(assigned)) < preferred_pages else "placed"
    content["issueId"] = issue_id
    content["placementStatus"] = placement_status
    content["publicationStatus"] = "in_issue"
    content["assignedPageNumbers"] = sorted(assigned)
    content["updatedAt"] = now_iso()
    content["gsi2pk"] = f"CONTENT_ISSUE#{issue_id}"
    content["gsi2sk"] = f"{content.get('status') or 'draft'}#{clean_int(content.get('priority'), 50):04d}#{now_iso()}#{content_id}"
    table.put_item(Item=dynamodb_safe(content))
    mark_submission_used_for_content(content, issue_id, sorted(assigned))
    return {"flatplan": flat, "content": content, "slot": slot}


MAGAZINE_PAGE_TYPES = [
    "front_cover", "back_cover_ad", "editorial", "article", "trip_report",
    "photo_gallery", "event_calendar", "committee_list", "classifieds",
    "advertisement", "external_contribution", "mixed_content", "filler",
]

MAGAZINE_PAGE_TEMPLATES = [
    {"templateId": "front_cover", "name": "Front cover", "pageTypes": ["front_cover"], "description": "Fixed cover page using the selected issue cover artwork."},
    {"templateId": "back_cover_ad", "name": "Back cover advert", "pageTypes": ["back_cover_ad"], "description": "Fixed back-cover advertisement using the selected issue back-cover asset."},
    {"templateId": "blank_page", "name": "Blank / reset page", "pageTypes": ["mixed_content", "filler"], "description": "Empty interior page used by reset/cleanup. Add a template later when you are ready to lay it out.", "slots": []},
    {"templateId": "article_one_column", "name": "Article - one column", "pageTypes": ["article", "editorial", "mixed_content"], "description": "Simple article page with one main text flow and optional image slot later."},
    {"templateId": "article_two_column", "name": "Article - two column", "pageTypes": ["article", "editorial", "trip_report", "mixed_content"], "description": "Magazine article page with headline, lead image, intro excerpt and a two-column body flow.", "slots": [
        {"slotId": "headline", "slotLabel": "Article headline", "slotType": "content", "renderMode": "headline_only", "x": 0, "y": 0, "w": 100, "h": 9, "autoUsePrimaryContent": True},
        {"slotId": "feature_image", "slotLabel": "Feature image", "slotType": "image", "x": 0, "y": 11, "w": 46, "h": 24, "autoUseArticleImage": True},
        {"slotId": "intro", "slotLabel": "Intro / lead paragraph", "slotType": "content", "renderMode": "lead_excerpt", "leadCharacterLimit": 620, "x": 50, "y": 11, "w": 50, "h": 24, "autoUsePrimaryContent": True},
        {"slotId": "article_body", "slotLabel": "Article body - two columns", "slotType": "content", "renderMode": "story_flow_body", "storyFlowAutoStart": True, "x": 0, "y": 38, "w": 100, "h": 56, "autoUsePrimaryContent": True},
    ]},
    {"templateId": "article_continuation_two_column", "name": "Article - continuation two column", "pageTypes": ["article", "editorial", "trip_report", "mixed_content"], "description": "Continuation page that flows the next segment of a long article through two columns, with optional image/sidebar slots.", "slots": [
        {"slotId": "article_body", "slotLabel": "Article continuation - two columns", "slotType": "content", "renderMode": "story_flow_body", "storyFlowAutoStart": True, "x": 0, "y": 0, "w": 100, "h": 72, "autoUsePrimaryContent": True},
        {"slotId": "support_image", "slotLabel": "Optional continuation image", "slotType": "image", "x": 0, "y": 74, "w": 48, "h": 20, "autoUseArticleImage": False},
        {"slotId": "sidebar", "slotLabel": "Sidebar / pull quote / advert note", "slotType": "text", "x": 52, "y": 74, "w": 48, "h": 20},
    ]},
    {"templateId": "source_document_text_page", "name": "Imported document - text page", "pageTypes": ["article", "editorial", "trip_report", "committee_list", "mixed_content"], "description": "Composition page generated from an imported DOCX/PDF. Document text uses document-level columns/font controls and can flow around locked advert/image panels.", "slots": [
        {"slotId": "source_page_body", "slotLabel": "Source document page text", "slotType": "content", "renderMode": "source_page_body", "x": 0, "y": 0, "w": 100, "h": 94, "autoUsePrimaryContent": True},
    ]},
    {"templateId": "source_document_image_page", "name": "Imported document - text plus images", "pageTypes": ["article", "editorial", "trip_report", "committee_list", "mixed_content"], "description": "Composition page with document text plus source images/adverts as page-local panels.", "slots": [
        {"slotId": "source_page_body", "slotLabel": "Source document page text", "slotType": "content", "renderMode": "source_page_body", "x": 0, "y": 0, "w": 62, "h": 94, "autoUsePrimaryContent": True},
        {"slotId": "source_page_image_1", "slotLabel": "Source page image 1", "slotType": "image", "x": 66, "y": 0, "w": 34, "h": 30, "autoUseArticleImage": False},
        {"slotId": "source_page_image_2", "slotLabel": "Source page image 2", "slotType": "image", "x": 66, "y": 32, "w": 34, "h": 30, "autoUseArticleImage": False},
        {"slotId": "source_page_image_3", "slotLabel": "Source page image 3", "slotType": "image", "x": 66, "y": 64, "w": 34, "h": 30, "autoUseArticleImage": False},
    ]},
    {"templateId": "source_document_camera_page", "name": "Imported document - camera-ready page/PDF", "pageTypes": ["article", "editorial", "trip_report", "committee_list", "external_contribution", "mixed_content"], "description": "Places a source PDF/document as camera-ready supplied artwork until backend page rendering is available.", "slots": [
        {"slotId": "source_pdf_page", "slotLabel": "Source PDF / camera-ready page", "slotType": "content", "renderMode": "source_pdf_page", "x": 0, "y": 0, "w": 100, "h": 94, "autoUsePrimaryContent": True},
        {"slotId": "source_pdf_note", "slotLabel": "Source document note", "slotType": "text", "x": 0, "y": 95, "w": 100, "h": 5},
    ]},
    {"templateId": "composer_document_page", "name": "Composer - editable document flow", "pageTypes": ["article", "editorial", "trip_report", "committee_list", "mixed_content"], "description": "Generated magazine-composer page. Dynamic text, image and locked advert panels are stored on the page so text can flow around available real estate.", "slots": []},
    {"templateId": "mce_article_page", "name": "TinyMCE article page", "pageTypes": ["article", "editorial", "trip_report", "mixed_content"], "description": "Rendered page generated from an Article Library / TinyMCE article. Used by direct article placement so Issue Builder preserves the edited article structure.", "slots": []},
    {"templateId": "trip_report_image_lead", "name": "Trip report - image lead", "pageTypes": ["trip_report", "photo_gallery", "mixed_content"], "description": "Trip report with a prominent lead image area and supporting text."},
    {"templateId": "photo_gallery_grid", "name": "Photo gallery grid", "pageTypes": ["photo_gallery", "trip_report", "mixed_content"], "description": "Image-heavy page foundation for later drag/drop image slots."},
    {"templateId": "advert_full_page", "name": "Advertisement - full page", "pageTypes": ["advertisement", "external_contribution"], "description": "Single full-page advert or supplied PDF placement."},
    {"templateId": "advert_two_half_pages", "name": "Advertisement - two half-page adverts", "pageTypes": ["advertisement", "mixed_content"], "description": "Two stacked half-page advertisements; useful for page 2 advert spreads."},
    {"templateId": "advert_four_quarters", "name": "Advertisement - four quarter-page adverts", "pageTypes": ["advertisement", "mixed_content"], "description": "Four equal quarter-page advert slots."},
    {"templateId": "advert_top_half_content_bottom", "name": "Advertisement - top half + content", "pageTypes": ["advertisement", "article", "mixed_content"], "description": "Top half advert with lower article/notice/content slot."},
    {"templateId": "content_top_advert_bottom", "name": "Content top + advertisement bottom", "pageTypes": ["advertisement", "article", "mixed_content"], "description": "Content or club notice above a lower half-page advert."},
    {"templateId": "advert_strip_plus_article", "name": "Advert strip + article", "pageTypes": ["advertisement", "article", "mixed_content"], "description": "Small sponsor/advert strip with article-style content below."},
    {"templateId": "notice_stack", "name": "Notices / classifieds stack", "pageTypes": ["notice", "classifieds", "filler", "mixed_content"], "description": "Stacked notices, classifieds or filler blocks."},
    {"templateId": "committee_contacts", "name": "Committee / contacts", "pageTypes": ["committee_list"], "description": "Structured club contacts or committee page."},
    {"templateId": "calendar_list", "name": "Event calendar - list", "pageTypes": ["event_calendar"], "description": "Generated calendar list using the editor-selected number of upcoming club-event months for this issue."},
    {"templateId": "event_calendar_next_four_months", "name": "Event calendar - selected months", "pageTypes": ["event_calendar"], "description": "Magazine-style event calendar generated from the editor-selected number of upcoming months."},
    {"templateId": "text_panels_two_column", "name": "Text panels - two column notices", "pageTypes": ["notice", "filler", "mixed_content"], "description": "Two-column framed text panel layout for notices, member lists and club information."},
    {"templateId": "club_notices_roles", "name": "Text panels - VIP and committee", "pageTypes": ["notice", "committee_list", "mixed_content"], "description": "Framed panels similar to the current magazine VIP/roles/contact page."},
    {"templateId": "four_notice_boxes", "name": "Text panels - four notice boxes", "pageTypes": ["notice", "classifieds", "filler", "mixed_content"], "description": "Four framed text panels for short notices or classifieds."},
]


def template_pk() -> str:
    return "TEMPLATES"


def normalise_template_slots(raw: Any) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return slots
    for idx, item in enumerate(raw[:32]):
        if not isinstance(item, dict):
            continue
        slot_id = clean_text(item.get("slotId") or item.get("slot_id"), 80) or f"slot_{idx + 1}"
        slot_type = clean_text(item.get("slotType") or item.get("slot_type"), 40) or "content"
        slots.append({
            "slotId": slot_id,
            "slotLabel": clean_text(item.get("slotLabel") or item.get("slot_label") or item.get("label"), 120) or slot_id.replace("_", " ").title(),
            "slotType": slot_type,
            "x": max(0, min(100, clean_int(item.get("x"), 0))),
            "y": max(0, min(100, clean_int(item.get("y"), 0))),
            "w": max(1, min(100, clean_int(item.get("w"), 100))),
            "h": max(1, min(100, clean_int(item.get("h"), 20))),
            "frameTitle": clean_text(item.get("frameTitle") or item.get("frame_title"), 160),
            "bodyAlign": clean_text(item.get("bodyAlign") or item.get("body_align"), 24) or "left",
            "titleAlign": clean_text(item.get("titleAlign") or item.get("title_align"), 24) or "center",
            "titleFontSize": clamp_float(item.get("titleFontSize") or item.get("title_font_size"), clamp_float(item.get("fontSize") or item.get("font_size"), 9, 6, 30) * Decimal("1.28"), 6, 36),
            "bodyFontSize": clamp_float(item.get("bodyFontSize") or item.get("body_font_size") or item.get("fontSize") or item.get("font_size"), 9, 6, 30),
            "titleLineHeight": clean_text(item.get("titleLineHeight") or item.get("title_line_height"), 16) or "1.05",
            "bodyLineHeight": clean_text(item.get("bodyLineHeight") or item.get("body_line_height") or item.get("lineHeight") or item.get("line_height"), 16) or "1.15",
            "fontSize": clamp_float(item.get("bodyFontSize") or item.get("body_font_size") or item.get("fontSize") or item.get("font_size"), 9, 6, 30),
            "lineHeight": clean_text(item.get("bodyLineHeight") or item.get("body_line_height") or item.get("lineHeight") or item.get("line_height"), 16) or "1.15",
            "padding": max(0, min(12, clean_int(item.get("padding"), 3))),
            "borderWidth": max(0, min(8, clean_int(item.get("borderWidth") or item.get("border_width"), 1))),
            "borderColor": clean_text(item.get("borderColor") or item.get("border_color"), 24) or "#777777",
            "backgroundColor": clean_text(item.get("backgroundColor") or item.get("background_color"), 24) or "#f7f7f7",
            "titleUnderline": clean_bool(item.get("titleUnderline") or item.get("title_underline"), True),
            "lineFormatter": clean_text(item.get("lineFormatter") or item.get("line_formatter"), 40) or "normal",
            "renderMode": clean_text(item.get("renderMode") or item.get("render_mode"), 40),
            "leadCharacterLimit": max(0, min(5000, clean_int(item.get("leadCharacterLimit") or item.get("lead_character_limit"), 0))),
            "skipLeadCharacters": max(0, min(20000, clean_int(item.get("skipLeadCharacters") or item.get("skip_lead_characters"), 0))),
            "startCharacter": max(0, min(200000, clean_int(item.get("startCharacter") or item.get("start_character"), 0))),
            "previewCharacterLimit": max(0, min(20000, clean_int(item.get("previewCharacterLimit") or item.get("preview_character_limit"), 0))),
            "autoUsePrimaryContent": clean_bool(item.get("autoUsePrimaryContent") or item.get("auto_use_primary_content"), False),
            "autoUseArticleImage": clean_bool(item.get("autoUseArticleImage") or item.get("auto_use_article_image"), False),
        })
    return slots


def list_custom_templates() -> List[Dict[str, Any]]:
    ensure_table()
    try:
        resp = table.query(KeyConditionExpression=Key("pk").eq(template_pk()))
        items = [x for x in resp.get("Items", []) if not x.get("retired")]
        items.sort(key=lambda x: str(x.get("name") or x.get("templateId") or "").lower())
        return items
    except Exception as exc:
        print(f"Magazine template query failed: {exc}")
        return []


def all_templates() -> List[Dict[str, Any]]:
    templates = [dict(t, source="builtin") for t in MAGAZINE_PAGE_TEMPLATES]
    seen = {str(t.get("templateId")) for t in templates}
    for item in list_custom_templates():
        tid = str(item.get("templateId") or "")
        if tid and tid not in seen:
            templates.append(item)
            seen.add(tid)
    return templates


def save_custom_template(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    name = clean_text(payload.get("name"), 120)
    if not name:
        raise ValueError("Template name is required.")
    template_id = clean_text(payload.get("templateId"), 120)
    if not template_id:
        base = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")[:80] or "custom_template"
        template_id = f"custom_{base}_{uuid.uuid4().hex[:8]}"
    if template_id in {str(t.get("templateId")) for t in MAGAZINE_PAGE_TEMPLATES}:
        raise ValueError("Built-in templates cannot be overwritten. Save as a new custom template name.")
    slots = normalise_template_slots(payload.get("slots"))
    if not slots:
        raise ValueError("At least one template slot is required.")
    page_types = payload.get("pageTypes") if isinstance(payload.get("pageTypes"), list) else [payload.get("pageType") or "mixed_content"]
    item = {
        "pk": template_pk(),
        "sk": f"TEMPLATE#{template_id}",
        "templateId": template_id,
        "name": name,
        "description": clean_text(payload.get("description"), 500),
        "pageTypes": [clean_text(x, 80) for x in page_types if clean_text(x, 80)] or ["mixed_content"],
        "source": "custom",
        "slots": slots,
        "createdBy": user_id(c),
        "updatedAt": now_iso(),
        "retired": False,
        "gsi1pk": "TEMPLATE",
        "gsi1sk": f"ACTIVE#{name.lower()}#{template_id}",
    }
    table.put_item(Item=dynamodb_safe(item))
    return {"template": item, "templates": all_templates()}


def get_templates(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    require_editor(event)
    return {"templates": all_templates()}


def update_flatplan_page(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    require_editor(event)
    payload = parse_body(event)
    issue_id = clean_text(payload.get("issueId") or payload.get("issue_id"), 80)
    page_number = clean_int(payload.get("pageNumber") or payload.get("page_number"), 0)
    if not issue_id or page_number < 1:
        raise ValueError("issueId and pageNumber are required.")
    issue = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "METADATA"}).get("Item")
    if not issue:
        raise FileNotFoundError("Magazine issue not found.")
    page_count = clean_int(issue.get("pageCount"), 0)
    if page_number < 1 or page_number > page_count:
        raise ValueError("Page number is outside the issue page range.")
    flat = table.get_item(Key={"pk": issue_pk(issue_id), "sk": "FLATPLAN#CURRENT"}).get("Item") or make_flatplan(issue_id, page_count)
    pages = flat.get("pages") if isinstance(flat.get("pages"), list) else make_flatplan(issue_id, page_count)["pages"]
    page = None
    for existing in pages:
        if clean_int(existing.get("pageNumber"), 0) == page_number:
            page = existing
            break
    if page is None:
        raise FileNotFoundError("Page not found in flatplan.")

    requested_type = clean_text(payload.get("pageType") or payload.get("page_type"), 80)
    requested_template = clean_text(payload.get("templateId") or payload.get("template_id"), 120)
    requested_notes = clean_text(payload.get("notes"), 5000)
    requested_locked = payload.get("locked")
    requested_cover_layout = normalise_cover_layout(payload.get("coverLayout"))
    layout_slots_supplied = "layoutSlots" in payload or "layout_slots" in payload
    content_slots_supplied = "contentSlots" in payload or "content_slots" in payload
    requested_layout_slots = normalise_layout_slots(payload.get("layoutSlots") if "layoutSlots" in payload else payload.get("layout_slots"))
    requested_content_slots = normalise_layout_slots(payload.get("contentSlots") if "contentSlots" in payload else payload.get("content_slots"))
    reset_page = clean_bool(payload.get("resetPage") if "resetPage" in payload else payload.get("reset_page"), False)
    was_fixed_or_locked = bool(page.get("locked") or page_number == 1 or page_number == page_count or str(page.get("pageType") or "") in {"front_cover", "back_cover_ad"})
    if reset_page and was_fixed_or_locked:
        raise ValueError("Locked/fixed pages cannot be reset. Unlock the page before resetting it.")
    if reset_page:
        preserved_locked_slots = locked_layout_slots_for_reset(page)
        if preserved_locked_slots:
            requested_layout_slots = merge_locked_slots_for_reset(requested_layout_slots if layout_slots_supplied else [], preserved_locked_slots)
            layout_slots_supplied = True
    old_content_ids = magazine_page_content_ids(page) if reset_page or content_slots_supplied or layout_slots_supplied else []

    if page_number == 1:
        page["pageType"] = "front_cover"
        page["templateId"] = "front_cover"
        page["locked"] = True
        if requested_cover_layout:
            existing_layout = page.get("coverLayout") if isinstance(page.get("coverLayout"), dict) else {}
            page["coverLayout"] = {**existing_layout, **requested_cover_layout}
    elif page_number == page_count:
        page["pageType"] = "back_cover_ad"
        page["templateId"] = "back_cover_ad"
        page["locked"] = True
    else:
        if requested_type:
            if requested_type not in MAGAZINE_PAGE_TYPES or requested_type in {"front_cover", "back_cover_ad"}:
                raise ValueError("Unsupported magazine page type for an interior page.")
            page["pageType"] = requested_type
        if requested_template:
            valid_templates = {str(t.get("templateId")) for t in all_templates()}
            if requested_template not in valid_templates or requested_template in {"front_cover", "back_cover_ad"}:
                raise ValueError("Unsupported magazine page template for an interior page.")
            page["templateId"] = requested_template
        if requested_locked is not None:
            page["locked"] = bool(requested_locked)
        if layout_slots_supplied:
            page["layoutSlots"] = requested_layout_slots
        if content_slots_supplied or reset_page:
            page["contentSlots"] = requested_content_slots if content_slots_supplied else []
        if reset_page:
            # Remove stale story/placement fields from older editor builds so the flatplan tile
            # and continuation engine do not keep showing/using cleared content.
            for stale_key in ("storyId", "storyStartPage", "storyContentItemId", "articleFlow", "primaryContentItemId", "previewAssetId"):
                page.pop(stale_key, None)
    page["notes"] = requested_notes
    page["updatedAt"] = now_iso()
    flat["pages"] = pages
    flat["updatedAt"] = now_iso()
    flat["version"] = clean_int(flat.get("version"), 1) + 1
    table.put_item(Item=dynamodb_safe(flat))
    if reset_page:
        refresh_content_placement_after_page_clear(issue_id, [page_number], old_content_ids)
    return {"flatplan": flat, "page": page}

def inbound_submission_with_url(item: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(item or {})
    key = str(out.get("s3_key") or "")
    bucket = str(out.get("s3_bucket") or ASSETS_BUCKET)
    if bucket and key:
        try:
            out["viewUrl"] = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=min(UPLOAD_EXPIRY_SECONDS, 3600))
            out["viewUrlExpiresIn"] = min(UPLOAD_EXPIRY_SECONDS, 3600)
        except Exception as exc:
            print(f"Could not create inbound submission view URL for {out.get('submission_id')}: {exc}")
    status = str(out.get("status") or "stored")
    out["canConvert"] = status not in {"converted", "used_in_issue", "published", "rejected", "archived"}
    return out


def query_submission_kind(kind: str, limit: int = 75, include_all: bool = False) -> List[Dict[str, Any]]:
    if email_state_table is None:
        return []
    try:
        result = email_state_table.query(KeyConditionExpression=Key("pk").eq(submission_pk(kind)), ScanIndexForward=False, Limit=max(1, min(200, int(limit or 75))))
    except Exception as exc:
        print(f"Could not query magazine inbound submissions for {kind}: {exc}")
        return []
    items = [x for x in result.get("Items", []) if isinstance(x, dict)]
    if not include_all:
        items = [x for x in items if str(x.get("status") or "stored") not in {"converted", "used_in_issue", "published", "rejected", "archived"}]
    items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or x.get("received_at") or ""), reverse=True)
    return [inbound_submission_with_url(x) for x in items]


def list_inbound(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    params = event.get("queryStringParameters") or {}
    include_all = str(params.get("all") or params.get("includeAll") or "").lower() in {"1", "true", "yes", "on"}
    try:
        limit = max(1, min(200, int(params.get("limit") or 75)))
    except Exception:
        limit = 75
    kinds = ["magazinecontent", "vendorcontent", "tripreports"]
    if str(params.get("kind") or "").strip().lower() in kinds:
        kinds = [str(params.get("kind")).strip().lower()]
    items: List[Dict[str, Any]] = []
    for kind in kinds:
        items.extend(query_submission_kind(kind, limit=limit, include_all=include_all))
    items.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or x.get("received_at") or ""), reverse=True)
    sources = [
        {"address": "magazinecontent@<fqdn>", "kind": "raw magazine article/source-material submission", "status": "active"},
        {"address": "vendorcontent@<fqdn>", "kind": "vendor/external advert or supplied content", "status": "active"},
        {"address": "tripreports@<fqdn>", "kind": "trip report/editor intake", "status": "active"},
        {"address": "magazines@<fqdn>", "kind": "finished magazine PDF archive upload", "status": "separate-public-archive"},
    ]
    return {"items": items[:limit], "sources": sources, "message": "Magazine editor inbound queue is wired to magazinecontent@, vendorcontent@ and tripreports@ submissions."}


def get_submission(kind: str, submission_id: str = "", sk: str = "") -> Dict[str, Any]:
    if email_state_table is None:
        raise RuntimeError("EMAIL_STATE_TABLE is not configured for magazine inbound conversion.")
    kind = clean_text(kind, 80) or "magazinecontent"
    if sk:
        item = email_state_table.get_item(Key={"pk": submission_pk(kind), "sk": sk}).get("Item")
        if item:
            return item
    results = email_state_table.query(KeyConditionExpression=Key("pk").eq(submission_pk(kind)), Limit=200).get("Items", [])
    for item in results:
        if str(item.get("submission_id") or "") == str(submission_id or ""):
            return item
    raise FileNotFoundError("Inbound magazine submission was not found.")


def create_asset_from_submission(submission: Dict[str, Any], issue_id: str) -> Dict[str, Any]:
    if not ASSETS_BUCKET:
        raise RuntimeError("MAGAZINE_ASSETS_BUCKET is not configured.")
    kind = clean_text(submission.get("kind"), 80) or "magazinecontent"
    source_bucket = str(submission.get("s3_bucket") or ASSETS_BUCKET)
    source_key = str(submission.get("s3_key") or "")
    if not source_bucket or not source_key:
        raise ValueError("Submission has no stored source object.")
    filename = safe_filename(submission.get("filename") or "submission")
    content_type = clean_text(submission.get("content_type"), 120) or "application/octet-stream"
    asset_id = f"asset-{uuid.uuid4().hex}"
    dest_key = f"{ASSETS_PREFIX}inbound/{kind}/{simple_slug(submission.get('submission_id') or submission.get('sk') or asset_id)}/{filename}"
    s3.copy_object(Bucket=ASSETS_BUCKET, Key=dest_key, CopySource={"Bucket": source_bucket, "Key": source_key}, ContentType=content_type, MetadataDirective="REPLACE", Metadata={"source": "webmail_submission", "submission-kind": kind[:80], "submission-id": str(submission.get("submission_id") or "")[:180]}, ServerSideEncryption="AES256")
    asset_type = infer_asset_type_from_submission(kind, filename, content_type)
    material_type = infer_material_type(asset_type, filename, content_type)
    item = {"pk": asset_pk(asset_id), "sk": "METADATA", "entityType": "MagazineAsset", "assetId": asset_id, "assetType": asset_type, "materialType": material_type, "issueId": issue_id or "unassigned", "fileName": filename, "mimeType": content_type, "fileSizeBytes": clean_int(submission.get("size"), 0), "s3Bucket": ASSETS_BUCKET, "s3Key": dest_key, "title": clean_text(submission.get("subject") or filename, 240), "advertiserName": clean_text(submission.get("from_name") or submission.get("from_email"), 180) if material_type == "advert" else "", "source": "webmail_submission", "sourceSubmissionKind": kind, "sourceSubmissionId": str(submission.get("submission_id") or ""), "sourceSubmissionSk": str(submission.get("sk") or ""), "status": "active" if material_type == "advert" else "available", "createdAt": now_iso(), "updatedAt": now_iso(), "gsi1pk": "ASSETS", "gsi1sk": f"{now_iso()}#{asset_id}", "gsi2pk": f"ASSET_TYPE#{asset_type}", "gsi2sk": f"{now_iso()}#{asset_id}", "gsi3pk": f"MATERIAL_TYPE#{material_type}", "gsi3sk": f"{now_iso()}#{asset_id}"}
    table.put_item(Item=dynamodb_safe(item))
    return item


def mark_submission_record(submission: Dict[str, Any], **updates: Any) -> None:
    if email_state_table is None or not submission:
        return
    item = dict(submission)
    item.update({k: v for k, v in updates.items() if v is not None})
    item["updated_at"] = now_iso()
    email_state_table.put_item(Item=dynamodb_safe(item))


def mark_submission_used_for_content(content: Dict[str, Any], issue_id: str, page_numbers: List[int]) -> None:
    kind = clean_text(content.get("sourceSubmissionKind"), 80)
    sk = clean_text(content.get("sourceSubmissionSk"), 220)
    sid = clean_text(content.get("sourceSubmissionId"), 180)
    if not kind or not (sk or sid):
        return
    try:
        submission = get_submission(kind, sid, sk)
        mark_submission_record(submission, status="used_in_issue", publication_status="in_issue", content_item_id=content.get("contentItemId"), issue_id=issue_id, placed_page_numbers=page_numbers)
    except Exception as exc:
        print(f"Could not mark submission as used for content {content.get('contentItemId')}: {exc}")


def convert_inbound_submission(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    kind = clean_text(payload.get("kind"), 80) or "magazinecontent"
    submission = get_submission(kind, clean_text(payload.get("submissionId") or payload.get("submission_id"), 180), clean_text(payload.get("sk"), 220))
    status = str(submission.get("status") or "stored")
    if status in {"converted", "used_in_issue", "published", "rejected", "archived"} and not clean_bool(payload.get("force"), False):
        raise ValueError(f"Submission is already {status}; use force=true to convert again.")
    issue_id = clean_text(payload.get("issueId") or payload.get("issue_id"), 80) or "unassigned"
    asset = create_asset_from_submission(submission, issue_id)
    content_id = clean_text(payload.get("contentItemId") or payload.get("content_id"), 120) or f"content-{uuid.uuid4().hex}"
    filename = str(submission.get("filename") or "")
    title = clean_text(payload.get("title"), 240) or clean_text(submission.get("subject"), 240) or filename or "Inbound magazine content"
    content_type = infer_content_type_from_submission(kind, filename, payload.get("contentType") or payload.get("content_type"))
    extraction = extract_source_material(str(submission.get("s3_bucket") or ASSETS_BUCKET), str(submission.get("s3_key") or ""), filename, clean_text(submission.get("content_type"), 120), kind=kind, issue_id=issue_id, source_slug=submission.get("submission_id") or submission.get("sk") or content_id, source_submission=submission)
    supplied_body = clean_extracted_text(payload.get("bodyMarkdown") or payload.get("body_markdown"), 60000)
    extracted_body = clean_extracted_text(extraction.get("bodyMarkdown"), 60000)
    body_markdown = supplied_body or extracted_body
    if not body_markdown:
        body_lines = [
            f"Source file: {filename}" if filename else "",
            f"From: {clean_text(submission.get('from'), 250)}" if submission.get("from") else "",
            f"Received: {clean_text(submission.get('received_at'), 80)}" if submission.get("received_at") else "",
            extraction.get("extractionMessage") or "",
        ]
        body_markdown = "\n\n".join([str(x) for x in body_lines if x])[:60000]
    priority = clean_int(payload.get("priority"), 50)
    image_asset_ids = [x for x in (extraction.get("extractedImageAssetIds") or []) if x]
    asset_ids = [asset.get("assetId")] + image_asset_ids
    preferred_pages = clean_int(payload.get("preferredPageCount") or payload.get("preferred_page_count"), 0) or clean_int(extraction.get("sourcePageCount"), 0) or estimate_preferred_pages(body_markdown, 1)
    item = {
        "pk": content_pk(content_id),
        "sk": "METADATA",
        "entityType": "MagazineContentItem",
        "contentItemId": content_id,
        "title": title,
        "subtitle": clean_text(payload.get("subtitle"), 300),
        "authorName": clean_text(payload.get("authorName") or payload.get("author_name") or submission.get("from"), 180),
        "source": f"{kind}_email",
        "contentType": content_type,
        "bodyMarkdown": body_markdown,
        "notes": clean_text(payload.get("notes"), 4000),
        "assetIds": asset_ids,
        "sourceAssetId": asset.get("assetId"),
        "extractedImageAssetIds": image_asset_ids,
        "sourcePages": extraction.get("sourcePages") if isinstance(extraction.get("sourcePages"), list) else [],
        "sourceBlocks": extraction.get("sourceBlocks") if isinstance(extraction.get("sourceBlocks"), list) else [],
        "sourcePageCount": clean_int(extraction.get("sourcePageCount"), 0),
        "sourceLayoutStatus": extraction.get("sourceLayoutStatus") or ("ready" if extraction.get("sourcePages") else "not_available"),
        "issueId": issue_id,
        "placementStatus": "unplaced",
        "publicationStatus": "pending",
        "assignedPageNumbers": [],
        "priority": priority,
        "preferredPageCount": preferred_pages,
        "minPageCount": clean_int(payload.get("minPageCount") or payload.get("min_page_count"), 1),
        "maxPageCount": clean_int(payload.get("maxPageCount") or payload.get("max_page_count"), max(4, preferred_pages)),
        "status": clean_text(payload.get("status"), 40) or "pending",
        "sourceSubmissionKind": kind,
        "sourceSubmissionId": str(submission.get("submission_id") or ""),
        "sourceSubmissionSk": str(submission.get("sk") or ""),
        "sourceMessageId": str(submission.get("message_id") or ""),
        "sourceFileName": filename,
        "sourceFormat": extraction.get("sourceFormat") or source_format_for_filename(filename, submission.get("content_type")),
        "extractionStatus": extraction.get("extractionStatus") or "not_available",
        "extractionMessage": clean_text(extraction.get("extractionMessage"), 500),
        "extractedCharacterCount": clean_int(extraction.get("extractedCharacterCount"), len(body_markdown or "")),
        "extractedImageCount": clean_int(extraction.get("extractedImageCount"), 0),
        "createdAt": now_iso(),
        "createdBy": user_id(c),
        "updatedAt": now_iso(),
        "updatedBy": user_id(c),
        "gsi1pk": "CONTENT",
        "gsi1sk": f"pending#{priority:04d}#{now_iso()}#{content_id}",
        "gsi2pk": f"CONTENT_ISSUE#{issue_id}",
        "gsi2sk": f"pending#{priority:04d}#{now_iso()}#{content_id}",
    }
    table.put_item(Item=dynamodb_safe(item))
    mark_submission_record(submission, status="converted", publication_status="pending", content_item_id=content_id, asset_id=asset.get("assetId"), issue_id=issue_id, converted_at=now_iso(), converted_by=user_id(c), extraction_status=item.get("extractionStatus"), extracted_character_count=item.get("extractedCharacterCount"), extracted_image_count=item.get("extractedImageCount"))
    return {"item": item, "asset": asset, "extraction": extraction, "submission": inbound_submission_with_url({**submission, "status": "converted", "content_item_id": content_id, "asset_id": asset.get("assetId"), "issue_id": issue_id})}


def extract_content_source(event: Dict[str, Any]) -> Dict[str, Any]:
    ensure_table()
    c = require_editor(event)
    payload = parse_body(event)
    content_id = clean_text(payload.get("contentItemId") or payload.get("content_id"), 120)
    if not content_id:
        raise ValueError("contentItemId is required.")
    content = table.get_item(Key={"pk": content_pk(content_id), "sk": "METADATA"}).get("Item")
    if not content:
        raise FileNotFoundError("Magazine content item not found.")
    asset_id = clean_text(payload.get("assetId") or payload.get("asset_id") or content.get("sourceAssetId"), 120)
    if not asset_id:
        for candidate in content.get("assetIds") or []:
            candidate = clean_text(candidate, 120)
            if candidate:
                asset_id = candidate
                break
    if not asset_id:
        raise ValueError("This content item has no source asset to extract.")
    asset = table.get_item(Key={"pk": asset_pk(asset_id), "sk": "METADATA"}).get("Item")
    if not asset:
        raise FileNotFoundError("Source asset was not found.")
    issue_id = clean_text(content.get("issueId"), 80) or "unassigned"
    kind = clean_text(content.get("sourceSubmissionKind"), 80) or "magazinecontent"
    extraction = extract_source_material(str(asset.get("s3Bucket") or ASSETS_BUCKET), str(asset.get("s3Key") or ""), str(asset.get("fileName") or content.get("sourceFileName") or ""), clean_text(asset.get("mimeType"), 120), kind=kind, issue_id=issue_id, source_slug=content_id, source_content=content)
    body = clean_extracted_text(extraction.get("bodyMarkdown"), 60000)
    source_pages = extraction.get("sourcePages") if isinstance(extraction.get("sourcePages"), list) else []
    if not body and not source_pages:
        raise ValueError(extraction.get("extractionMessage") or "No source pages could be extracted from the source asset.")
    new_asset_ids = [x for x in (content.get("assetIds") or []) if x]
    for image_id in extraction.get("extractedImageAssetIds") or []:
        if image_id and image_id not in new_asset_ids:
            new_asset_ids.append(image_id)
    existing_image_ids = [x for x in (content.get("extractedImageAssetIds") or []) if x]
    for image_id in extraction.get("extractedImageAssetIds") or []:
        if image_id and image_id not in existing_image_ids:
            existing_image_ids.append(image_id)
    content.update({
        "bodyMarkdown": body or content.get("bodyMarkdown") or "",
        "bodyHtml": clean_article_html(extraction.get("bodyHtml"), 120000) or content.get("bodyHtml") or article_text_to_html(body),
        "editorFormat": "tinymce_html" if extraction.get("bodyHtml") else content.get("editorFormat") or "plain_text",
        "assetIds": new_asset_ids,
        "extractedImageAssetIds": existing_image_ids,
        "sourcePages": extraction.get("sourcePages") if isinstance(extraction.get("sourcePages"), list) else content.get("sourcePages", []),
        "sourceBlocks": extraction.get("sourceBlocks") if isinstance(extraction.get("sourceBlocks"), list) else content.get("sourceBlocks", []),
        "sourcePageCount": clean_int(extraction.get("sourcePageCount"), len(extraction.get("sourcePages") or content.get("sourcePages", []) or [])),
        "sourceLayoutStatus": extraction.get("sourceLayoutStatus") or ("ready" if extraction.get("sourcePages") else content.get("sourceLayoutStatus") or "not_available"),
        "sourceColumnCount": clean_int(extraction.get("sourceColumnCount"), int(content.get("sourceColumnCount") or 1)),
        "editorColumnCount": (
            clean_int(extraction.get("sourceColumnCount"), 1)
            if clean_int(extraction.get("sourceColumnCount"), 1) > 1 and clean_int(content.get("editorColumnCount"), 1) <= 1
            else clean_int(content.get("editorColumnCount"), clean_int(extraction.get("sourceColumnCount"), 1))
        ),
        "sourceFormat": extraction.get("sourceFormat") or content.get("sourceFormat") or "unknown",
        "extractionStatus": extraction.get("extractionStatus") or "complete",
        "extractionMessage": clean_text(extraction.get("extractionMessage"), 500),
        "extractedCharacterCount": clean_int(extraction.get("extractedCharacterCount"), len(body)),
        "extractedImageCount": len(existing_image_ids),
        "preferredPageCount": max(clean_int(content.get("preferredPageCount"), 1), clean_int(extraction.get("sourcePageCount"), 0), estimate_preferred_pages(body, 1)),
        "updatedAt": now_iso(),
        "updatedBy": user_id(c),
    })
    table.put_item(Item=dynamodb_safe(content))
    return {"item": content, "asset": asset, "extraction": extraction}


def bootstrap() -> Dict[str, Any]:
    return {
        "module": "lroc-magazine-production",
        "phase": "advert-builder-wysiwyg-foundation",
        "maxUploadBytes": MAX_UPLOAD_BYTES,
        "allowedMimePrefixes": list(ALLOWED_MIME_PREFIXES),
        "contentTypes": ["article", "trip_report", "notice", "calendar", "committee_list", "generated_section", "advertisement", "classified", "finished_pdf", "external_pdf", "image_gallery", "filler"],
        "assetTypes": [
            "image",
            "logo",
            "cover_image",
            "back_cover_ad",
            "advertisement",
            "advert_pdf",
            "article_image",
            "finished_pdf",
            "source_pdf",
            "source_document",
            "vendor_pdf",
            "trip_report_image",
            "production_file",
            "asset",
        ],
        "materialTypes": ["article", "advert", "image", "generated_section", "finished_pdf", "article_source", "asset"],
        "advertSizeTypes": ["full_page_portrait", "half_page_landscape", "half_page_portrait", "quarter_page", "banner_strip", "square", "unknown"],
        "pageCountRules": {"minimum": 4, "multipleOf": 4, "frontCoverPage": 1, "backCoverAdPage": "last"},
        "pageTypes": MAGAZINE_PAGE_TYPES,
        "pageTemplates": all_templates(),
        "printQualityPolicy": {
            "outputDpi": 300,
            "preferredDpi": 300,
            "acceptableDpi": 200,
            "warningBelowDpi": 200,
            "strongWarningBelowDpi": 150,
            "notes": "Quality checks use effective DPI at the placed size. Output aims for 300 DPI, but 200 DPI is acceptable for normal club printed copy.",
            "a4FullPagePixelsAt300Dpi": {"width": 2480, "height": 3508},
            "a4FullPagePixelsAt200Dpi": {"width": 1654, "height": 2339},
        },
        "inboundSources": ["magazinecontent@<fqdn>", "vendorcontent@<fqdn>", "tripreports@<fqdn>", "magazines@<fqdn>"],
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
            return response(204, {})
        route = event.get("routeKey", "")
        params = event.get("queryStringParameters") or {}
        require_editor(event)
        if route == "GET /member/magazine/bootstrap":
            return response(200, bootstrap())
        if route == "GET /member/magazine/issues":
            issue_id = clean_text(params.get("issueId") or params.get("issue_id"), 80)
            return response(200, get_issue(issue_id) if issue_id else list_issues())
        if route == "POST /member/magazine/issues":
            return response(200, create_or_update_issue(event))
        if route == "GET /member/magazine/content":
            return response(200, list_content(event))
        if route == "POST /member/magazine/content":
            return response(200, create_or_update_content(event))
        if route == "POST /member/magazine/content/extract":
            return response(200, extract_content_source(event))
        if route == "POST /member/magazine/content/archive":
            return response(200, archive_content_item(event))
        if route == "POST /member/magazine/flatplan/place":
            return response(200, place_content_on_page(event))
        if route == "POST /member/magazine/flatplan/page":
            return response(200, update_flatplan_page(event))
        if route == "GET /member/magazine/templates":
            return response(200, get_templates(event))
        if route == "POST /member/magazine/templates":
            return response(200, save_custom_template(event))
        if route == "GET /member/magazine/assets":
            return response(200, list_assets())
        if route == "GET /member/magazine/assets/file-data":
            return response(200, get_asset_file_data(event))
        if route == "POST /member/magazine/assets/cleanup-duplicates":
            return response(200, cleanup_duplicate_image_assets(event))
        if route == "POST /member/magazine/assets/delete":
            return response(200, delete_asset_completely(event))
        if route == "POST /member/magazine/assets/upload-url":
            return response(200, create_upload_url(event))
        if route == "POST /member/magazine/assets/confirm-upload":
            return response(200, confirm_upload(event))
        if route == "GET /member/magazine/inbound":
            return response(200, list_inbound(event))
        if route == "POST /member/magazine/inbound/convert":
            return response(200, convert_inbound_submission(event))
        return response(404, {"message": f"Unknown magazine route: {route}"})
    except PermissionError as exc:
        return response(403, {"message": str(exc)})
    except FileNotFoundError as exc:
        return response(404, {"message": str(exc)})
    except ValueError as exc:
        return response(400, {"message": str(exc)})
    except Exception as exc:
        print(f"Magazine API error: {exc}")
        return response(500, {"message": str(exc)})
