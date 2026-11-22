from __future__ import annotations

import html
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pypdf import PdfReader

from .schemas import AnyDraft, DraftPackage
from .skills import SkillId, artifact_filenames
from .errors import CoworkerError

RTL_LANGUAGES = {"ar", "fa", "he", "ur", "ps", "dv"}


def validate_day6_exports(skill_id, draft, outputs, *, expected_sources):
    """Validate native Day 6 artifacts before publication and after private-storage readback."""
    if skill_id not in {"research", "report_email"}:
        return

    expected = artifact_filenames(skill_id)
    if not isinstance(outputs, (list, tuple)) or len(outputs) != 4:
        raise ValueError("Day 6 export must contain exactly four artifacts")

    content_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".json": "application/json",
    }
    rows = {}
    for row in outputs:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError("Malformed artifact row")
        filename, content_type, body = row
        if not isinstance(filename, str) or filename not in expected or filename in rows:
            raise ValueError("Unexpected or duplicate artifact filename")
        expected_type = content_types.get(Path(filename).suffix.lower())
        if expected_type is None or content_type != expected_type:
            raise ValueError("Artifact MIME type does not match its native format")
        if not isinstance(body, (bytes, bytearray)) or not 0 < len(body) <= 16 * 1024 * 1024:
            raise ValueError("Artifact is empty or exceeds the size limit")
        rows[filename] = bytes(body)

    if set(rows) != expected:
        raise ValueError("Day 6 artifact set is incomplete")

    if skill_id == "report_email":
        title = draft.report.title
        headings = [section.heading for section in draft.report.sections]
        # The native renderer owns the full unsent email text. Substring
        # matches would permit injected recipient headers, duplicate content
        # or a fabricated "Sent" receipt to reach the owner's download.
        expected_email_text = draft.email.subject + "\n\n" + draft.email.body
        docx_name, pdf_name, text_name = "report.docx", "report.pdf", "email-draft.txt"
    else:
        title = draft.title
        headings = [finding.heading for finding in draft.findings]
        docx_name, pdf_name, text_name = "research-report.docx", "research-report.pdf", "research-report.txt"

    try:
        document = Document(io.BytesIO(rows[docx_name]))
        document_paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
        document_text = "\n".join(document_paragraphs)
        if not document_text.strip() or not title or title not in document_text:
            raise ValueError("DOCX title or readable content is missing")
        if any(not heading or heading not in document_text for heading in headings):
            raise ValueError("DOCX is missing an expected section heading")

        # Opening a well-formed native file is not sufficient. A renderer (or
        # an altered checkpoint at completion) could replace all report facts,
        # section source IDs or bibliography entries while preserving the
        # filename, title, and headings. For report/email the native renderer
        # produces a deterministic paragraph sequence: verify it in full,
        # including duplicates, rather than accepting substring matches.
        pdf_claims = [title]
        if skill_id == "report_email":
            expected_paragraphs = [draft.report.title, draft.report.summary]
            pdf_claims.append(draft.report.summary)
            for section in draft.report.sections:
                section_ref = "[" + ", ".join(section.source_ids) + "]"
                expected_paragraphs.extend([section.heading, *section.paragraphs, section_ref])
                pdf_claims.extend([section.heading, *section.paragraphs, section_ref])
            for source in expected_sources:
                source_ref = f'[{source["id"]}] {source["label"]}'
                expected_paragraphs.append(source_ref)
                pdf_claims.append(source_ref)
            for gap in draft.missing_information:
                expected_paragraphs.append("[ ] " + gap)
                pdf_claims.append(gap)
            if document_paragraphs != expected_paragraphs:
                raise ValueError("DOCX content differs from the reviewed report, references or evidence gaps")
        else:
            # A valid, readable DOCX can still add unsupported claims, change
            # retrieval dates or redirect a trusted-looking bibliography link.
            # Rebuild the exact native block sequence from the reviewed draft
            # and authorized source snapshot. Read XML text nodes so source
            # hyperlinks remain visible across python-docx versions.
            from docx.opc.constants import RELATIONSHIP_TYPE as RT
            from .work_exports import content_blocks

            research_title, research_blocks = content_blocks(draft, expected_sources)
            expected_paragraphs = [research_title] + [
                ("☐ " if block.kind == "check" else "") + block.text
                for block in research_blocks
            ]
            actual_paragraphs = [
                "".join(node.text or "" for node in paragraph._p.iter(qn("w:t"))).strip()
                for paragraph in document.paragraphs
            ]
            if actual_paragraphs != expected_paragraphs:
                raise ValueError(
                    "DOCX research content differs from reviewed findings, citations or source metadata"
                )

            # Visible source labels alone do not prove that clickable links
            # resolve to authorized origins. Check every source-bearing
            # hyperlink's actual relationship target, and reject extra links.
            expected_links = [None] + [block.url for block in research_blocks]
            for paragraph, expected_url in zip(document.paragraphs, expected_links):
                links = list(paragraph._p.iter(qn("w:hyperlink")))
                if expected_url is None:
                    if links:
                        raise ValueError("DOCX contains an unreviewed hyperlink")
                    continue
                if len(links) != 1:
                    raise ValueError("DOCX source hyperlink is missing or duplicated")
                relationship = document.part.rels.get(links[0].get(qn("r:id")))
                if (relationship is None or relationship.reltype != RT.HYPERLINK
                        or not relationship.is_external
                        or relationship.target_ref != expected_url):
                    raise ValueError("DOCX source hyperlink is not the reviewed URL")

            for finding in draft.findings:
                pdf_claims.extend([finding.heading, finding.text])
                for citation in finding.citations:
                    pdf_claims.append(citation.quote)
            pdf_claims.extend(draft.missing_information)

        reader = PdfReader(io.BytesIO(rows[pdf_name]))
        if reader.is_encrypted or not reader.pages:
            raise ValueError("PDF has no readable pages")
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not pdf_text.strip():
            raise ValueError("PDF contains no extractable text")
        # PDF text extraction is whitespace- and shaping-dependent, notably
        # for Bangla. Require the unchanged ASCII claims/reference IDs that
        # can be unambiguously extracted, without falsely rejecting a valid
        # Bengali native document because glyph shaping changes transcription.
        # In right-to-left languages, pypdf can reorder even ASCII source
        # quotations inside Arabic/Hebrew text. Do not reject valid native
        # exports based on a visual-order vs extracted-order mismatch.
        # The source-bound DOCX, manifest, and PDF parseability checks still
        # apply; independent hosted review must inspect RTL glyph fidelity.
        if draft.output_language.split("-")[0].lower() not in RTL_LANGUAGES:
            compact_pdf = "".join(pdf_text.split())
            # A section heading can repeat the report title. Merely finding
            # that string somewhere in the PDF would accept an unrelated
            # cover title; the renderer writes the reviewed title first.
            if title.isascii() and not compact_pdf.startswith("".join(title.split())):
                raise ValueError("PDF does not open with the reviewed report title")
            if any("".join(claim.split()) not in compact_pdf
                   for claim in pdf_claims if claim and claim.isascii()):
                raise ValueError("PDF text differs from the reviewed title, facts or references")

        text_content = rows[text_name].decode("utf-8")
        if not text_content.strip():
            raise ValueError("Text artifact is empty")
        if skill_id == "report_email":
            if text_content != expected_email_text:
                raise ValueError("Email draft bytes differ from the reviewed unsent subject and body")
        else:
            # Research text is a first-class downloadable artifact. Checking
            # only title/headings would permit substituted findings, invented
            # evidence quotations, removed source metadata or appended claims
            # while its PDF/DOCX and manifest remained unchanged. Recreate the
            # canonical block sequence from the reviewed draft and authorized
            # source snapshot instead of trusting the renderer's text bytes.
            from .work_exports import content_blocks, serialize_work_text

            research_title, research_blocks = content_blocks(draft, expected_sources)
            if research_title != title or text_content != serialize_work_text(
                research_title, research_blocks
            ):
                raise ValueError(
                    "Research text differs from the reviewed findings, citations, or sources"
                )

        manifest = json.loads(rows["source-manifest.json"].decode("utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
            raise ValueError("Source manifest is malformed")
        if manifest.get("output_language") != draft.output_language:
            raise ValueError("Source manifest language does not match the draft")
        if manifest.get("missing_information") != list(draft.missing_information):
            raise ValueError("Source manifest completeness state does not match the draft")
        expected_status = "needs_input" if draft.missing_information else "draft_ready"
        if manifest.get("delivery_status") != expected_status:
            raise ValueError("Source manifest has an invalid draft status")
        if skill_id == "research" and manifest.get("skill_id") != "research":
            raise ValueError("Research source manifest has the wrong skill")
        if any(not isinstance(source, dict) or "text" in source for source in manifest["sources"]):
            raise ValueError("Source manifest must not contain raw source text")
        # The renderer is not an authority for provenance. Its manifest must
        # reproduce the exact source snapshot saved with the validated draft,
        # including source IDs, versions, hashes and ordering. Merely checking
        # that sources is a list allows omitted, substituted or injected data.
        if not isinstance(expected_sources, list) or manifest["sources"] != expected_sources:
            raise ValueError("Source manifest does not match the authorized draft sources")
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("A native Day 6 artifact could not be opened or verified") from exc


def render_in_subprocess(draft: AnyDraft, sources: list[dict], *, skill_id: SkillId = "report_email"):
    with tempfile.TemporaryDirectory(prefix="shuddho-export-") as directory:
        folder = Path(directory)
        (folder / "input.json").write_text(json.dumps({"draft": draft.model_dump(), "sources": sources, "skill_id": skill_id}, ensure_ascii=False), encoding="utf-8")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "services.coworker.render_worker", directory],
                cwd=Path(__file__).resolve().parents[2], env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
            )
            manifest_path = folder / "manifest.json"
            if result.returncode or not manifest_path.is_file() or manifest_path.stat().st_size > 2000:
                raise ValueError()
            manifest = json.loads(manifest_path.read_text())
            expected = artifact_filenames(skill_id)
            if {row[0] for row in manifest} != expected or len(manifest) != 4:
                raise ValueError()
            outputs = []
            for filename, content_type in manifest:
                path = folder / filename
                if not 0 < path.stat().st_size <= 16 * 1024 * 1024:
                    raise ValueError()
                outputs.append((filename, content_type, path.read_bytes()))
            return outputs
        except (subprocess.TimeoutExpired, ValueError, OSError, TypeError):
            raise CoworkerError("export_failed", "The file export could not finish. Try a shorter draft.", 422) from None


def font_for(language):
    root = language.split("-")[0].lower()
    return {"bn": "Noto Sans Bengali", "hi": "Noto Sans Devanagari", "ar": "Noto Sans Arabic",
            "fa": "Noto Sans Arabic", "ur": "Noto Sans Arabic", "he": "Noto Sans Hebrew",
            "zh": "Noto Sans CJK SC", "ja": "Noto Sans CJK JP", "ko": "Noto Sans CJK KR"}.get(root, "Noto Sans")


def render_artifacts(draft: DraftPackage, sources: list[dict]) -> list[tuple[str, str, bytes]]:
    language = draft.output_language
    rtl = language.split("-")[0].lower() in RTL_LANGUAGES
    report = draft.report
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.27), Inches(11.69)
    section.top_margin = section.bottom_margin = Inches(0.8)
    section.left_margin = section.right_margin = Inches(0.85)
    for name in ["Normal", "Title", "Heading 1", "Heading 2"]:
        style = document.styles[name]
        style.font.name = font_for(language)
        style.font.color.rgb = RGBColor.from_string("173A39")
        for key in ["ascii", "hAnsi", "eastAsia", "cs"]:
            style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:" + key), font_for(language))
    normal = document.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.3

    def paragraph(text, style=None):
        value = document.add_paragraph(text, style)
        props = value._p.get_or_add_pPr()
        if rtl:
            element = OxmlElement("w:bidi")
            element.set(qn("w:val"), "1")
            props.append(element)
        for run in value.runs:
            lang = OxmlElement("w:lang")
            lang.set(qn("w:val"), language)
            lang.set(qn("w:bidi"), language)
            run._r.get_or_add_rPr().append(lang)
            if rtl:
                run.font.rtl = True
        return value

    paragraph(report.title, "Title")
    paragraph(report.summary)
    parts = [f"<h1>{html.escape(report.title)}</h1><p class='summary'>{html.escape(report.summary)}</p>"]
    for item in report.sections:
        paragraph(item.heading, "Heading 1")
        parts.append(f"<h2>{html.escape(item.heading)}</h2>")
        for text in item.paragraphs:
            paragraph(text)
            parts.append(f"<p>{html.escape(text)}</p>")
        references = "[" + ", ".join(item.source_ids) + "]"
        paragraph(references)
        parts.append(f"<p class='reference'>{html.escape(references)}</p>")
    for source in sources:
        reference = f'[{source["id"]}] {source["label"]}'
        paragraph(reference)
        parts.append(f"<p class='reference'>{html.escape(reference)}</p>")
    if draft.missing_information:
        for item in draft.missing_information:
            paragraph("[ ] " + item)
            parts.append(f"<p class='missing'>□ {html.escape(item)}</p>")
    buffer = io.BytesIO()
    document.save(buffer)
    docx = buffer.getvalue()
    # Re-open the generated package before exposing it as a successful export.
    if not Document(io.BytesIO(docx)).paragraphs:
        raise ValueError("DOCX export is empty")
    direction = "rtl" if rtl else "ltr"
    markup = f"""<!doctype html><html lang="{html.escape(language, quote=True)}" dir="{direction}"><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 20mm 22mm; @bottom-center {{ content: counter(page); font-size: 9pt; color: #667; }} }}
      body {{ font-family: '{font_for(language)}', 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 11pt; line-height: 1.55; color: #203636; overflow-wrap: anywhere; }}
      h1 {{ font-size: 26pt; line-height: 1.22; color: #143f3c; margin: 0 0 7mm; }}
      h2 {{ font-size: 14pt; margin: 7mm 0 2mm; break-after: avoid; }}
      p {{ orphans: 3; widows: 3; margin: 0 0 3mm; white-space: pre-wrap; }}
      .summary {{ font-size: 12pt; color: #455c5b; margin-bottom: 7mm; }}
      .reference {{ font-size: 8.5pt; color: #667; }} .missing {{ color: #72501c; }}
    </style></head><body>{''.join(parts)}</body></html>"""
    from weasyprint import HTML

    def no_external_resources(*_args, **_kwargs):
        raise ValueError("External resources are disabled for document export")

    pdf = HTML(string=markup, url_fetcher=no_external_resources).write_pdf()
    if not pdf.startswith(b"%PDF-") or not PdfReader(io.BytesIO(pdf)).pages:
        raise ValueError("PDF export is invalid")
    email = draft.email.subject + "\n\n" + draft.email.body
    return [
        ("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx),
        ("report.pdf", "application/pdf", pdf),
        ("email-draft.txt", "text/plain; charset=utf-8", email.encode("utf-8")),
        ("source-manifest.json", "application/json", json.dumps({
            "sources": sources, "output_language": draft.output_language,
            "missing_information": draft.missing_information, "delivery_status": "needs_input" if draft.missing_information else "draft_ready",
        }, ensure_ascii=False, indent=2).encode("utf-8")),
    ]
