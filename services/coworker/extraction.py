from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .errors import CoworkerError

MAX_EXPANDED_DOCX = 32 * 1024 * 1024


def extract_text(data: bytes, kind: str, max_chars=20000) -> str:
    """Parser entry point. Production calls it in a resource-limited child."""
    if kind == "txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise CoworkerError("text_encoding", "Please save this text file as UTF-8 and upload it again.", 415) from None
    elif kind == "docx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > 2000 or sum(item.file_size for item in members) > MAX_EXPANDED_DOCX:
                raise CoworkerError("document_expansion_limit", "This document is too large to unpack safely.", 413)
            if len({item.filename for item in members}) != len(members):
                raise CoworkerError("document_invalid", "This document contains duplicate package entries.", 415)
            for item in members:
                if item.flag_bits & 1 or "vbaproject" in item.filename.lower() or "/embeddings/" in item.filename.lower() or "/activex/" in item.filename.lower():
                    raise CoworkerError("document_active_content", "Upload a standard DOCX without macros, embedded files, or encrypted content.", 415)
            xml = archive.read("word/document.xml")
            if len(xml) > 8 * 1024 * 1024 or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise CoworkerError("document_invalid", "This DOCX cannot be processed safely.", 415)
            root = ElementTree.fromstring(xml)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            text = "\n".join("".join(node.text or "" for node in paragraph.iter(ns + "t")) for paragraph in root.iter(ns + "p"))
    elif kind == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise CoworkerError("encrypted_pdf", "Upload an unlocked copy of this PDF.", 415)
        if len(reader.pages) > 40:
            raise CoworkerError("page_limit", "Choose a PDF with no more than 40 pages.", 413)
        pages = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            if not extracted.strip() and len(page.images):
                raise CoworkerError("ocr_required", "This PDF contains scanned pages. Upload a text-based PDF, DOCX, or pasted notes; OCR is not available yet.", 415)
            pages.append(extracted)
            if sum(len(value) for value in pages) > max_chars:
                raise CoworkerError("source_too_large", "Choose a shorter document for this workflow.", 413)
        text = "\n".join(pages)
    elif kind in {"csv", "xlsx", "pptx"}:
        from .office_sources import extract_office_text
        text = extract_office_text(data, kind)
    else:
        raise CoworkerError("unsupported_file", "Supported files: TXT, DOCX, text-based PDF, CSV, XLSX, and PPTX.", 415)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise CoworkerError("empty_document", "No readable text was found. Add notes or use a text-based document.", 415)
    if len(text) > max_chars:
        raise CoworkerError("source_too_large", "Choose a shorter document for this workflow.", 413)
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise CoworkerError("document_invalid", "This file contains unsupported control characters.", 415)
    return text


def extract_in_subprocess(data: bytes, kind: str, max_chars: int) -> str:
    with tempfile.TemporaryDirectory(prefix="shuddho-parse-") as directory:
        source = Path(directory) / "source"
        output = Path(directory) / "result.json"
        source.write_bytes(data)
        try:
            # Child receives no provider, database, storage, or identity secrets.
            result = subprocess.run(
                [sys.executable, "-m", "services.coworker.parse_worker", kind, str(source), str(output), str(max_chars)],
                cwd=Path(__file__).resolve().parents[2], env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
            )
        except subprocess.TimeoutExpired:
            raise CoworkerError("parse_timeout", "This file took too long to read. Try a smaller or simpler document.", 422) from None
        if result.returncode or not output.is_file() or output.stat().st_size > 200000:
            raise CoworkerError("document_invalid", "This file could not be read safely. Try exporting a fresh copy.", 415)
        payload = json.loads(output.read_text(encoding="utf-8"))
        if "error" in payload:
            raise CoworkerError(payload["error"], payload["message"], 415)
        return payload["text"]
