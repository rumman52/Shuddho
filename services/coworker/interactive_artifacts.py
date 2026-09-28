from __future__ import annotations

import hashlib
import hmac
import re
import time
from html.parser import HTMLParser

from .errors import CoworkerError


ALLOWED_TAGS = {
    "html", "head", "body", "title", "style",
    "main", "section", "article", "header", "footer", "aside",
    "div", "span", "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "small", "code", "pre", "blockquote",
    "ul", "ol", "li",
    "table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td",
    "details", "summary", "label", "input", "a", "img",
}
VOID_TAGS = {"br", "hr", "input", "img"}
GLOBAL_ATTRS = {
    "id", "class", "title", "dir", "lang", "role",
    "aria-label", "aria-describedby", "aria-labelledby",
}
TABLE_ATTRS = {"colspan", "rowspan", "scope"}
CSS_FORBIDDEN = (
    "url(", "@import", "expression(", "-moz-binding", "javascript:",
    "behavior:", "binding:",
)
DATA_IMAGE = re.compile(
    r"^data:image/(?:png|jpeg|gif|webp);base64,[a-zA-Z0-9+/=]+$"
)
FRAGMENT = re.compile(r"^#[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class _PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.in_style = False
        self.seen_html = False
        self.seen_body = False

    @staticmethod
    def _safe_css(value: str) -> None:
        compact = value.lower().replace("\\", "")
        if any(token in compact for token in CSS_FORBIDDEN):
            raise CoworkerError(
                "sandbox_artifact_unsafe",
                "Interactive artifact styles cannot load external resources.",
                422,
            )

    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        seen: set[str] = set()
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = "" if raw_value is None else raw_value
            if name in seen or name.startswith("on"):
                raise CoworkerError(
                    "sandbox_artifact_unsafe",
                    "Interactive artifact attributes are not allowed.",
                    422,
                )
            seen.add(name)
            if name == "style":
                self._safe_css(value)
                continue
            if name.startswith("data-"):
                if len(name) > 64 or len(value) > 1024:
                    raise CoworkerError(
                        "sandbox_artifact_unsafe",
                        "Interactive artifact metadata is too large.",
                        422,
                    )
                continue
            if name in GLOBAL_ATTRS:
                continue
            if tag in {"th", "td"} and name in TABLE_ATTRS:
                if not value.isdecimal() or not 1 <= int(value) <= 100:
                    raise CoworkerError("sandbox_artifact_unsafe", "Invalid table span.", 422)
                continue
            if tag == "details" and name == "open":
                continue
            if tag == "input":
                if name == "type" and value.lower() in {"checkbox", "radio"}:
                    continue
                if name in {"checked", "disabled"}:
                    continue
                if name in {"name", "value"} and len(value) <= 128:
                    continue
            if tag == "label" and name == "for" and FRAGMENT.fullmatch("#" + value):
                continue
            if tag == "a" and name == "href" and FRAGMENT.fullmatch(value):
                continue
            if tag == "img" and name in {"alt", "width", "height"}:
                if len(value) <= 256:
                    continue
            if tag == "img" and name == "src" and DATA_IMAGE.fullmatch(value):
                continue
            raise CoworkerError(
                "sandbox_artifact_unsafe",
                "Interactive artifact contains an unsupported attribute.",
                422,
            )

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            raise CoworkerError(
                "sandbox_artifact_unsafe",
                "Interactive artifact contains an unsupported HTML element.",
                422,
            )
        self._attrs(tag, attrs)
        if tag == "html":
            if self.seen_html:
                raise CoworkerError("sandbox_artifact_unsafe", "Invalid HTML structure.", 422)
            self.seen_html = True
        if tag == "body":
            self.seen_body = True
        if tag == "style":
            self.in_style = True
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs):
        tag = tag.lower()
        if tag not in VOID_TAGS:
            raise CoworkerError("sandbox_artifact_unsafe", "Invalid self-closing element.", 422)
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in VOID_TAGS or not self.stack or self.stack[-1] != tag:
            raise CoworkerError("sandbox_artifact_unsafe", "Invalid HTML structure.", 422)
        self.stack.pop()
        if tag == "style":
            self.in_style = False

    def handle_data(self, data: str):
        if self.in_style:
            self._safe_css(data)

    def handle_decl(self, decl: str):
        if decl.strip().lower() != "doctype html":
            raise CoworkerError("sandbox_artifact_unsafe", "Unsupported HTML declaration.", 422)

    def handle_entityref(self, name: str):
        return None

    def handle_charref(self, name: str):
        return None

    def unknown_decl(self, data: str):
        raise CoworkerError("sandbox_artifact_unsafe", "Unsupported HTML declaration.", 422)

    def handle_pi(self, data: str):
        raise CoworkerError("sandbox_artifact_unsafe", "Processing instructions are not allowed.", 422)

    def close(self):
        super().close()
        if self.stack or not self.seen_html or not self.seen_body:
            raise CoworkerError("sandbox_artifact_unsafe", "Interactive artifact HTML is incomplete.", 422)


def validate_static_preview_html(body: bytes, max_bytes: int) -> str:
    if not body or len(body) > max_bytes:
        raise CoworkerError(
            "sandbox_artifact_limit",
            "Interactive artifact exceeded its byte limit.",
            413,
        )
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise CoworkerError(
            "sandbox_artifact_encoding",
            "Interactive artifact must be valid UTF-8 HTML.",
            422,
        ) from None
    if "\x00" in text:
        raise CoworkerError("sandbox_artifact_unsafe", "Interactive artifact contains invalid text.", 422)
    parser = _PreviewParser()
    try:
        parser.feed(text)
        parser.close()
    except CoworkerError:
        raise
    except Exception:
        raise CoworkerError(
            "sandbox_artifact_unsafe",
            "Interactive artifact HTML could not be validated.",
            422,
        ) from None
    return text



def create_preview_token(
    secret: str,
    artifact_id: str,
    sha256: str,
    expires_at: int,
) -> str:
    payload = f"{artifact_id}:{sha256}:{expires_at}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{expires_at}.{signature}"


def verify_preview_token(
    secret: str,
    artifact_id: str,
    sha256: str,
    token: str,
    *,
    now: int | None = None,
    max_future_seconds: int = 300,
) -> int:
    try:
        raw_expiry, signature = token.split(".", 1)
        if not raw_expiry.isdecimal() or len(raw_expiry) > 12:
            raise ValueError()
        expires_at = int(raw_expiry)
    except (TypeError, ValueError):
        raise CoworkerError(
            "sandbox_preview_invalid",
            "This interactive preview link is invalid.",
            404,
        ) from None
    current = int(time.time()) if now is None else now
    if expires_at < current or expires_at > current + max_future_seconds:
        raise CoworkerError(
            "sandbox_preview_expired",
            "This interactive preview link expired. Open it again from Shuddho.",
            410,
        )
    expected = create_preview_token(secret, artifact_id, sha256, expires_at).split(".", 1)[1]
    if len(signature) != 64 or not hmac.compare_digest(signature, expected):
        raise CoworkerError(
            "sandbox_preview_invalid",
            "This interactive preview link is invalid.",
            404,
        )
    return expires_at
