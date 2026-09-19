"""Private, bounded document-rendering subprocess. Never runs model code."""
import json
import sys
from pathlib import Path


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
        resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
    except ImportError:  # Windows development; production uses the Linux image.
        pass
    from .exports import render_artifacts
    from .schemas import parse_draft
    from .work_exports import render_work_artifacts
    folder = Path(sys.argv[1])
    value = json.loads((folder / "input.json").read_text(encoding="utf-8"))
    skill_id = value.get("skill_id", "report_email")
    draft = parse_draft(skill_id, value["draft"])
    outputs = (render_artifacts(draft, value["sources"]) if skill_id == "report_email"
               else render_work_artifacts(skill_id, draft, value["sources"]))
    manifest = []
    for filename, content_type, body in outputs:
        (folder / filename).write_bytes(body)
        manifest.append([filename, content_type])
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    main()
