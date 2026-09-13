"""Restricted parser process. No network requests, macros, or external resources."""
import json
import sys
from pathlib import Path


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (256000, 256000))
    except ImportError:
        pass  # Windows development; production worker runs Linux.
    from .errors import CoworkerError
    from .extraction import extract_text
    kind, source, output, max_chars = sys.argv[1:]
    try:
        payload = {"text": extract_text(Path(source).read_bytes(), kind, int(max_chars))}
    except CoworkerError as error:
        payload = {"error": error.code, "message": error.message}
    except Exception:
        payload = {"error": "document_invalid", "message": "This file could not be read safely. Try exporting a fresh copy."}
    Path(output).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
