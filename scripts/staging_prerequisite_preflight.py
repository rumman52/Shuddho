from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_BUCKET = "shuddho-coworker-staging"
EXPECTED_TASK_QUEUE = "shuddho-documents-v1"
REQUIRED_SECRETS = (
    "RENDER_API_KEY",
    "SHUDDHO_TEMPORAL_ADDRESS",
    "SHUDDHO_TEMPORAL_NAMESPACE",
    "SHUDDHO_TEMPORAL_API_KEY",
    "SHUDDHO_STAGING_S3_ACCESS_KEY_ID",
    "SHUDDHO_STAGING_S3_SECRET_ACCESS_KEY",
)


class PreflightFailure(RuntimeError):
    pass


def _require_present(env: dict[str, str], name: str) -> None:
    value = env.get(name, "")
    if not isinstance(value, str) or not value.strip():
        raise PreflightFailure(f"BLOCKED_EXTERNAL — {name} REQUIRED")


def _validate_temporal_address(value: str) -> None:
    candidate = value.strip()
    if "://" in candidate:
        raise PreflightFailure(
            "SHUDDHO_TEMPORAL_ADDRESS must be host:port, not an HTTP(S) URL."
        )
    if any(char.isspace() for char in candidate):
        raise PreflightFailure("SHUDDHO_TEMPORAL_ADDRESS must not contain whitespace.")
    if any(char in candidate for char in "/@?#"):
        raise PreflightFailure(
            "SHUDDHO_TEMPORAL_ADDRESS must contain only a host and port."
        )
    if ":" not in candidate:
        raise PreflightFailure("SHUDDHO_TEMPORAL_ADDRESS must include a port.")
    host, port_text = candidate.rsplit(":", 1)
    if not host or not port_text.isdecimal():
        raise PreflightFailure("SHUDDHO_TEMPORAL_ADDRESS must be host:port.")
    port = int(port_text)
    if port < 1 or port > 65535:
        raise PreflightFailure("SHUDDHO_TEMPORAL_ADDRESS port is outside 1..65535.")


def _validate_https_endpoint(value: str, name: str) -> None:
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise PreflightFailure(
            f"{name} must be an HTTPS endpoint without credentials, query or fragment."
        )


def validate(env: dict[str, str]) -> dict:
    for name in REQUIRED_SECRETS:
        _require_present(env, name)

    _validate_temporal_address(env["SHUDDHO_TEMPORAL_ADDRESS"])

    namespace = env["SHUDDHO_TEMPORAL_NAMESPACE"].strip()
    if not namespace or any(char.isspace() for char in namespace):
        raise PreflightFailure(
            "SHUDDHO_TEMPORAL_NAMESPACE must be a non-empty namespace without whitespace."
        )

    tls = env.get("SHUDDHO_TEMPORAL_TLS", "").strip().lower()
    if tls != "true":
        raise PreflightFailure("SHUDDHO_TEMPORAL_TLS must be true for controlled staging.")

    task_queue = env.get("SHUDDHO_TEMPORAL_TASK_QUEUE", "").strip()
    if task_queue != EXPECTED_TASK_QUEUE:
        raise PreflightFailure(
            f"SHUDDHO_TEMPORAL_TASK_QUEUE must be {EXPECTED_TASK_QUEUE}."
        )

    storage = env.get("SHUDDHO_COWORKER_STORAGE", "").strip()
    if storage != "s3":
        raise PreflightFailure("SHUDDHO_COWORKER_STORAGE must be s3.")

    bucket = env.get("SHUDDHO_COWORKER_BUCKET", "").strip()
    if bucket != EXPECTED_BUCKET:
        raise PreflightFailure(
            f"SHUDDHO_COWORKER_BUCKET must be {EXPECTED_BUCKET}."
        )

    endpoint = env.get("SHUDDHO_COWORKER_S3_ENDPOINT", "")
    _validate_https_endpoint(endpoint, "SHUDDHO_COWORKER_S3_ENDPOINT")

    region = env.get("AWS_DEFAULT_REGION", "").strip()
    if not region or any(char.isspace() for char in region):
        raise PreflightFailure("AWS_DEFAULT_REGION must be a non-empty region.")

    return {
        "status": "passed",
        "checks": {
            **{name: "present" for name in REQUIRED_SECRETS},
            "DEEPSEEK_API_KEY": (
                "present_optional"
                if env.get("DEEPSEEK_API_KEY", "").strip()
                else "not_configured_optional"
            ),
            "temporal_address": "valid_host_port",
            "temporal_namespace": "present",
            "temporal_tls": "true",
            "temporal_task_queue": EXPECTED_TASK_QUEUE,
            "storage_backend": "s3",
            "storage_bucket": EXPECTED_BUCKET,
            "storage_endpoint": "valid_https_endpoint",
            "storage_region": "present",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate PA-10 staging prerequisite presence and non-secret configuration "
            "shape without provisioning infrastructure or contacting providers."
        )
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result = validate(dict(os.environ))
    except PreflightFailure as error:
        payload = {"status": "blocked_external", "error": str(error)}
        print(json.dumps(payload, indent=2))
        if args.output:
            args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1) from None

    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
