from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx


SCHEMA_VERSION = 1
PRODUCTION_NAMES = {"prod", "production"}


class BrowserPushProbeFailure(RuntimeError):
    pass


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_BROWSER_PUSH", "").lower() != "true":
        raise BrowserPushProbeFailure(
            "Set SHUDDHO_STAGING_ALLOW_BROWSER_PUSH=true only in approved controlled staging."
        )
    if os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true":
        raise BrowserPushProbeFailure(
            "Set SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true only for a synthetic staging account."
        )


def env_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise BrowserPushProbeFailure(f"{name} is required.")
    return value


def require_https_base(value: str) -> str:
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise BrowserPushProbeFailure(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        )
    return clean


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BrowserPushProbeFailure(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise BrowserPushProbeFailure(f"{label} must contain a JSON object.")
    return value


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def json_object(response: httpx.Response, label: str) -> dict:
    if response.status_code != 200:
        raise BrowserPushProbeFailure(
            f"{label} returned HTTP {response.status_code}; expected 200."
        )
    try:
        value = response.json()
    except ValueError:
        raise BrowserPushProbeFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise BrowserPushProbeFailure(f"{label} returned an unexpected JSON shape.")
    return value


def release_identity(
    client: httpx.Client,
    token: str,
    rollout_path: Path,
    provider_policy_path: Path,
) -> dict:
    rollout = load_json(rollout_path, "rollout manifest")
    policy = load_json(provider_policy_path, "provider-policy plan")
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise BrowserPushProbeFailure("Rollout manifest release_id is required.")
    manifest = json_object(
        client.get("/api/v1/runtime-manifest", headers=auth(token)),
        "runtime manifest",
    )
    expected_environment = env_secret("SHUDDHO_STAGING_EXPECTED_ENVIRONMENT").strip()
    if expected_environment.lower() in PRODUCTION_NAMES:
        raise BrowserPushProbeFailure(
            "SHUDDHO_STAGING_EXPECTED_ENVIRONMENT must be non-production."
        )
    if manifest.get("environment") != expected_environment:
        raise BrowserPushProbeFailure(
            "Deployed runtime environment does not match the expected staging environment."
        )
    revision = manifest.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise BrowserPushProbeFailure(
            "Deployed runtime manifest must expose a full lowercase source revision."
        )
    capabilities = manifest.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("automations") is not True
        or capabilities.get("browser_push") is not True
    ):
        raise BrowserPushProbeFailure(
            "Automations and Browser Push must both be enabled in the controlled-staging release."
        )
    deployment_reference = env_secret(
        "SHUDDHO_STAGING_DEPLOYMENT_REFERENCE"
    ).strip()
    if not deployment_reference:
        raise BrowserPushProbeFailure(
            "SHUDDHO_STAGING_DEPLOYMENT_REFERENCE must not be blank."
        )
    return {
        "release_id": release_id.strip(),
        "source_revision": revision,
        "environment": expected_environment,
        "deployment_reference": deployment_reference,
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "provider_policy_sha256": sha256_file(provider_policy_path),
    }


def owner_id(client: httpx.Client, token: str) -> str:
    me = json_object(
        client.get("/api/v1/me", headers=auth(token)),
        "staging account",
    )
    value = str(me.get("account_id") or "")
    if not value:
        raise BrowserPushProbeFailure(
            "Synthetic staging account did not expose an account_id."
        )
    return value


def load_state(client: httpx.Client, token: str) -> dict:
    config = json_object(
        client.get("/api/v1/browser-push/config", headers=auth(token)),
        "browser push config",
    )
    if config.get("enabled") is not True:
        raise BrowserPushProbeFailure(
            "Browser Push is not enabled in the deployed staging release."
        )
    preferences = json_object(
        client.get("/api/v1/notification-preferences", headers=auth(token)),
        "notification preferences",
    )
    if (
        preferences.get("in_app_enabled") is not True
        or preferences.get("browser_push_enabled") is not True
    ):
        raise BrowserPushProbeFailure(
            "Use a synthetic account with in-app and Browser Push consent enabled."
        )
    receipts = json_object(
        client.get("/api/v1/browser-push/deliveries", headers=auth(token)),
        "browser push deliveries",
    )
    if receipts.get("enabled") is not True:
        raise BrowserPushProbeFailure(
            "Browser Push delivery receipts are not enabled."
        )
    deliveries = receipts.get("deliveries")
    notices = json_object(
        client.get("/api/v1/notifications", headers=auth(token)),
        "notifications",
    ).get("notifications")
    if not isinstance(deliveries, list) or not isinstance(notices, list):
        raise BrowserPushProbeFailure(
            "Browser Push evidence endpoints returned an unexpected shape."
        )
    return {"deliveries": deliveries, "notifications": notices}


def prepare(args: argparse.Namespace) -> dict:
    require_guard()
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    label = env_secret("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL").strip()
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        release = release_identity(
            client, token, args.rollout, args.provider_policy_plan
        )
        owner = owner_id(client, token)
        current = load_state(client, token)
    state = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": "pa10_browser_push",
        "release": release,
        "synthetic_account_label": label,
        "owner_id": owner,
        "baseline_delivery_ids": sorted(
            str(item.get("id"))
            for item in current["deliveries"]
            if item.get("id") is not None
        ),
        "baseline_notification_ids": sorted(
            str(item.get("id"))
            for item in current["notifications"]
            if item.get("id") is not None
        ),
        "prepared_at": utcnow_iso(),
    }
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def verify(args: argparse.Namespace) -> dict:
    require_guard()
    state = load_json(args.state, "browser push probe state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise BrowserPushProbeFailure(
            "Browser Push probe state has an unexpected schema."
        )
    if not args.device_confirmation_reference.strip():
        raise BrowserPushProbeFailure(
            "A durable real-device display confirmation reference is required."
        )
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    deadline = time.monotonic() + max(1, args.timeout)
    old_deliveries = set(state.get("baseline_delivery_ids") or [])
    old_notices = set(state.get("baseline_notification_ids") or [])
    last_error: BrowserPushProbeFailure | None = None

    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            try:
                release = release_identity(
                    client, token, args.rollout, args.provider_policy_plan
                )
                if release != state.get("release"):
                    raise BrowserPushProbeFailure(
                        "Deployed release identity changed between prepare and verify."
                    )
                if owner_id(client, token) != state.get("owner_id"):
                    raise BrowserPushProbeFailure(
                        "Synthetic account identity changed between prepare and verify."
                    )
                current = load_state(client, token)
                new_notices = [
                    item
                    for item in current["notifications"]
                    if str(item.get("id") or "") not in old_notices
                ]
                new_receipts = [
                    item
                    for item in current["deliveries"]
                    if str(item.get("id") or "") not in old_deliveries
                ]
                accepted = [
                    item
                    for item in new_receipts
                    if item.get("state") == "provider_accepted"
                    and item.get("notification_id")
                    in {item.get("id") for item in new_notices}
                    and isinstance(item.get("provider_status"), int)
                    and 200 <= item["provider_status"] < 300
                    and item.get("accepted_at")
                ]
                if len(accepted) != 1:
                    raise BrowserPushProbeFailure(
                        f"Expected exactly one new provider-accepted Browser Push receipt; found {len(accepted)}."
                    )
                receipt = accepted[0]
                evidence = {
                    "schema_version": SCHEMA_VERSION,
                    "evidence_kind": "pa10_browser_push",
                    "status": "passed",
                    "release": release,
                    "synthetic_account_label": state["synthetic_account_label"],
                    "owner_id": state["owner_id"],
                    "prepared_at": state["prepared_at"],
                    "verified_at": utcnow_iso(),
                    "notification_id": receipt["notification_id"],
                    "delivery_id": receipt["id"],
                    "delivery_state": receipt["state"],
                    "provider_status": receipt["provider_status"],
                    "attempts": receipt["attempts"],
                    "provider_accepted_at": receipt["accepted_at"],
                    "device_confirmation_reference": args.device_confirmation_reference.strip(),
                    "device_display_claim": "operator-confirmed",
                }
                args.output.write_text(
                    json.dumps(evidence, indent=2) + "\n",
                    encoding="utf-8",
                )
                return evidence
            except BrowserPushProbeFailure as error:
                last_error = error
                time.sleep(max(1, args.poll_interval))
    raise last_error or BrowserPushProbeFailure(
        "Browser Push evidence did not become available before timeout."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect release-bound Browser Push evidence from an approved synthetic staging "
            "account. Provider acceptance is not treated as device display; verify requires a "
            "separate durable real-device confirmation reference."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--rollout", type=Path, required=True)
    prepare_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--rollout", type=Path, required=True)
    verify_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--device-confirmation-reference", required=True)
    verify_parser.add_argument("--timeout", type=int, default=180)
    verify_parser.add_argument("--poll-interval", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        result = prepare(args) if args.command == "prepare" else verify(args)
    except (httpx.HTTPError, BrowserPushProbeFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    if args.command == "prepare":
        print(json.dumps({
            "status": "prepared",
            "state": str(args.state),
            "release": result["release"],
            "next": (
                "With the approved real browser/device subscribed and Browser Push consent enabled, "
                "generate exactly one eligible Shuddho staging notification through the normal product path, "
                "confirm the generic notification visibly appears on that device, retain a durable confirmation "
                "reference, then run verify."
            ),
        }, indent=2))
    else:
        print(json.dumps({
            "status": result["status"],
            "output": str(args.output),
            "notification_id": result["notification_id"],
            "delivery_id": result["delivery_id"],
            "device_confirmation_reference": result["device_confirmation_reference"],
        }, indent=2))


if __name__ == "__main__":
    main()
