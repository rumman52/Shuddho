"""Read-only Shuddho API liveness and exact-source smoke check.

The fixed origins prevent turning this operator tool into an arbitrary-network
probe. It only issues unauthenticated GET /health and GET /version. It does not
qualify readiness, exercise analysis, or activate production capabilities.
"""
from __future__ import annotations

import argparse
import json
import re

import httpx


class ApiSmokeError(ValueError):
    """The checked deployment does not satisfy this narrow smoke contract."""


ORIGINS = {
    "production": "https://shuddho-api.onrender.com",
    "staging": "https://shuddho-api-staging.onrender.com",
}
FULL_SHA = re.compile(r"[a-fA-F0-9]{40}\Z")


def _json_object(response: httpx.Response, path: str) -> dict:
    if response.status_code != 200:
        raise ApiSmokeError(f"{path} returned HTTP {response.status_code}, expected 200")
    if "application/json" not in response.headers.get("content-type", "").lower():
        raise ApiSmokeError(f"{path} returned a non-JSON content type")
    try:
        value = response.json()
    except ValueError:
        raise ApiSmokeError(f"{path} returned invalid JSON") from None
    if not isinstance(value, dict):
        raise ApiSmokeError(f"{path} returned a non-object JSON response")
    return value


def check_api_deployment(
    environment: str,
    expected_sha: str,
    *,
    require_analysis_ready: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Check only public liveness and the *exact* 40-character deployed revision.

    No redirects, proxy environment, bearer tokens, POSTs, or user data.
    A green result is intentionally not a production-readiness assertion.
    """
    if not isinstance(environment, str) or environment not in ORIGINS:
        raise ApiSmokeError("unknown environment; only pinned Shuddho origins are allowed")
    if not isinstance(expected_sha, str) or FULL_SHA.fullmatch(expected_sha) is None:
        raise ApiSmokeError("expected source revision must be a full 40-character Git SHA")

    try:
        with httpx.Client(
            base_url=ORIGINS[environment],
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            health = _json_object(client.get("/health", headers={"Accept": "application/json"}), "/health")
            if (
                health.get("ok") is not True
                or health.get("service") != "shuddho-api"
                or health.get("status") != "ok"
            ):
                raise ApiSmokeError("/health did not confirm Shuddho API liveness")
            reasons = health.get("degraded_reasons")
            if not isinstance(reasons, list) or any(
                not isinstance(reason, str) or not reason for reason in reasons
            ):
                raise ApiSmokeError("/health returned invalid degraded-reasons metadata")
            # The absence of a degradation reason is not evidence that the
            # optional checkpoint-backed engines are loaded. A strict operator
            # check requires the actual full-local profile reported by the API.
            analysis_profile = health.get("analysis_profile")
            degraded_profiles = {
                "backend_without_detector",
                "backend_without_corrector",
                "backend_rules_and_spell_only",
                "frontend_local_fallback",
            }
            if reasons or analysis_profile in degraded_profiles:
                analysis_status = "degraded"
            elif analysis_profile == "full_local":
                analysis_status = "ready"
            else:
                analysis_status = "unverified"
            if require_analysis_ready and analysis_status != "ready":
                raise ApiSmokeError("analysis components are degraded or unverified")

            version = _json_object(client.get("/version", headers={"Accept": "application/json"}), "/version")
            actual = version.get("commit")
            if not isinstance(actual, str) or FULL_SHA.fullmatch(actual) is None:
                raise ApiSmokeError("/version does not expose a full deployed Git SHA")
            if actual.lower() != expected_sha.lower():
                raise ApiSmokeError("/version source revision mismatch")
    except httpx.RequestError as error:
        # Intentionally omit request path/details, which may contain proxy tokens.
        raise ApiSmokeError(f"network request failed ({type(error).__name__})") from None

    return {
        "status": "passed",
        "environment": environment,
        "source_revision": expected_sha.lower(),
        "scope": "liveness_and_revision_only",
        "analysis_status": analysis_status,
        "release_qualified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=sorted(ORIGINS))
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--require-analysis-ready", action="store_true")
    args = parser.parse_args()
    try:
        result = check_api_deployment(
            args.environment,
            args.expected_sha,
            require_analysis_ready=args.require_analysis_ready,
        )
    except ApiSmokeError as error:
        parser.exit(1, f"Shuddho deployment smoke BLOCKED: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
