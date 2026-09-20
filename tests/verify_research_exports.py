"""Produce multilingual native files/PDF previews for manual CI artifact review."""
import copy
import re
import subprocess
import sys
from pathlib import Path

from coworker_samples import work_draft
from research_samples import search_data
from services.coworker.exports import render_in_subprocess
from services.coworker.research import TavilyResearchProvider, validate_evidence
from services.coworker.schemas import ResearchOptions


def main(folder):
    folder.mkdir(parents=True, exist_ok=True)
    data = search_data()
    # Five sources and longer text exercise citation order, page breaks and URLs.
    data["results"] = [data["results"][0] | {"url": f"https://example.org/research/long-document-path/{i}?language=multilingual&view=source"}
                       for i in range(5)]
    evidence = TavilyResearchProvider.parse(data, ResearchOptions(query="simulated project reviews"))
    for language in ("en", "bn", "ar"):
        draft = work_draft("research", language)
        draft.findings = [copy.deepcopy(draft.findings[0]) for _ in range(5)]
        for i, finding in enumerate(draft.findings):
            finding.text = " ".join([finding.text] * 8)
            finding.citations[0].source_id = f"web-{i + 1}"
        validate_evidence(draft, evidence.sources)
        manifest = [{key: value for key, value in source.items() if key != "text"} for source in evidence.sources]
        for name, _content_type, body in render_in_subprocess(draft, manifest, skill_id="research"):
            (folder / f"{language}-{name}").write_bytes(body)
        subprocess.run(["pdftoppm", "-scale-to", "1400", "-png", str(folder / f"{language}-research-report.pdf"),
                        str(folder / language)], check=True, capture_output=True, timeout=30)
        layout = subprocess.run(["pdftotext", "-layout", str(folder / f"{language}-research-report.pdf"), "-"],
                                check=True, capture_output=True, text=True, timeout=30).stdout
        date = evidence.sources[0]["retrieved_at"][:10]
        assert layout.count(date) == 10, f"ISO date order changed in {language}"
        # Every source stays on the same page as its URL and both dates.
        for page in layout.split("\f"):
            count = len(re.findall(r"https://example\.org/", page))
            assert page.count(date) == count * 2, f"Source metadata split across pages in {language}"
    print("Research export previews ready: English, Bangla, Arabic, five sources, clickable links, long text.")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
