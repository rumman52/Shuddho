"""No-network tests of the optional read-only Shuddho deployment probe."""
import unittest
from unittest.mock import patch

import httpx

from scripts.api_deployment_smoke import (
    ApiSmokeError,
    ORIGINS,
    check_api_deployment,
    main,
)

SHA = "a" * 40
STALE_SHA = "b" * 40


def response_for(request: httpx.Request, *, health=None, version=None):
    assert request.method == "GET"
    assert request.url.host in {"shuddho-api.onrender.com", "shuddho-api-staging.onrender.com"}
    assert request.url.scheme == "https"
    if request.url.path == "/health":
        return httpx.Response(200, json=health if health is not None else {
            "ok": True, "service": "shuddho-api", "status": "ok",
            "degraded_reasons": [], "analysis_profile": "full_local"
        })
    if request.url.path == "/version":
        return httpx.Response(200, json=version if version is not None else {
            "commit": SHA, "build_time": "2026-10-27T17:00:00Z", "llm_pipeline_version": "validation-fix-v1"
        })
    raise AssertionError("unapproved path requested")


class ApiDeploymentSmokeTests(unittest.TestCase):
    def test_pinned_https_origins(self):
        self.assertEqual(ORIGINS["production"], "https://shuddho-api.onrender.com")
        self.assertEqual(ORIGINS["staging"], "https://shuddho-api-staging.onrender.com")

    def test_valid_liveness_and_exact_commit_both_environments(self):
        for environment in ORIGINS:
            with self.subTest(environment=environment):
                paths = []
                def responder(request):
                    paths.append(request.url.path)
                    return response_for(request)
                result = check_api_deployment(environment, SHA, transport=httpx.MockTransport(responder))
                self.assertEqual(paths, ["/health", "/version"])
                self.assertEqual(result["status"], "passed")
                self.assertEqual(result["source_revision"], SHA)
                self.assertFalse(result["release_qualified"])
                self.assertEqual(result["scope"], "liveness_and_revision_only")
                self.assertEqual(result["analysis_status"], "ready")
                self.assertNotIn("build_time", result)

    def test_wrong_environment_and_malformed_sha_fail_without_network(self):
        for environment, sha in (("other", SHA), ([], SHA), ("production", "ab"), ("production", "z" * 40), ("production", "")):
            with self.subTest(environment=environment, sha=sha):
                with self.assertRaises(ApiSmokeError):
                    check_api_deployment(environment, sha, transport=httpx.MockTransport(lambda r: self.fail("network used")))

    def test_commit_mismatch_rejected_even_on_http_200(self):
        with self.assertRaisesRegex(ApiSmokeError, "revision mismatch"):
            check_api_deployment("production", SHA, transport=httpx.MockTransport(
                lambda r: response_for(r, version={"commit": STALE_SHA})))

    def test_unknown_and_short_revision_rejected(self):
        for revision in ("unknown", SHA[:7], None, 7):
            with self.subTest(revision=revision), self.assertRaises(ApiSmokeError):
                check_api_deployment("staging", SHA, transport=httpx.MockTransport(
                    lambda r: response_for(r, version={"commit": revision})))

    def test_degraded_analysis_is_visible_but_not_confused_with_liveness(self):
        health = {"ok": True, "service": "shuddho-api", "status": "ok", "degraded_reasons": ["detector_disabled"]}
        transport = httpx.MockTransport(lambda r: response_for(r, health=health))
        result = check_api_deployment("production", SHA, transport=transport)
        self.assertEqual(result["analysis_status"], "degraded")
        self.assertFalse(result["release_qualified"])
        with self.assertRaisesRegex(ApiSmokeError, "analysis components are degraded"):
            check_api_deployment("production", SHA, require_analysis_ready=True, transport=transport)

    def test_strict_analysis_readiness_requires_verified_full_local_profile(self):
        for profile, expected_status in (
            (None, "unverified"),
            ("unknown", "unverified"),
            ([], "unverified"),
            ({}, "unverified"),
            (42, "unverified"),
            ("backend_without_detector", "degraded"),
            ("backend_without_corrector", "degraded"),
            ("backend_rules_and_spell_only", "degraded"),
            ("frontend_local_fallback", "degraded"),
        ):
            with self.subTest(profile=profile):
                health = {
                    "ok": True,
                    "service": "shuddho-api",
                    "status": "ok",
                    "degraded_reasons": [],
                }
                if profile is not None:
                    health["analysis_profile"] = profile
                transport = httpx.MockTransport(lambda r: response_for(r, health=health))
                result = check_api_deployment("staging", SHA, transport=transport)
                self.assertEqual(result["analysis_status"], expected_status)
                self.assertFalse(result["release_qualified"])
                with self.assertRaisesRegex(ApiSmokeError, "degraded or unverified"):
                    check_api_deployment(
                        "staging", SHA, require_analysis_ready=True, transport=transport
                    )

    def test_strict_analysis_readiness_accepts_confirmed_full_local_profile(self):
        result = check_api_deployment(
            "staging",
            SHA,
            require_analysis_ready=True,
            transport=httpx.MockTransport(response_for),
        )
        self.assertEqual(result["analysis_status"], "ready")
        self.assertFalse(result["release_qualified"])

    def test_invalid_degraded_reasons_shape_is_not_accepted(self):
        for reasons in (None, "none", [None], ["", 7]):
            with self.subTest(reasons=reasons), self.assertRaises(ApiSmokeError):
                check_api_deployment("production", SHA, transport=httpx.MockTransport(
                    lambda r: response_for(r, health={"ok": True, "service": "shuddho-api", "status": "ok", "degraded_reasons": reasons})))

    def test_health_invalid_state_is_rejected(self):
        for health in (
            {"ok": False, "service": "shuddho-api", "status": "ok", "degraded_reasons": []},
            {"ok": 1, "service": "shuddho-api", "status": "ok", "degraded_reasons": []},
            {"ok": True, "service": "other", "status": "ok", "degraded_reasons": []},
            {"ok": True, "service": "shuddho-api", "status": "degraded", "degraded_reasons": []},
        ):
            with self.subTest(health=health), self.assertRaises(ApiSmokeError):
                check_api_deployment("staging", SHA, transport=httpx.MockTransport(lambda r: response_for(r, health=health)))

    def test_http_failures_and_redirects_fail_closed(self):
        for status in (301, 302, 401, 429, 500):
            with self.subTest(status=status), self.assertRaises(ApiSmokeError):
                check_api_deployment("staging", SHA, transport=httpx.MockTransport(
                    lambda r: httpx.Response(status, headers={"Location": "http://127.0.0.1/admin"})))

    def test_broken_json_or_wrong_content_type_is_rejected(self):
        for response in (httpx.Response(200, text="not json"), httpx.Response(200, json=[]), httpx.Response(200, content=b'{}', headers={"content-type": "text/plain"})):
            with self.subTest(response=response), self.assertRaises(ApiSmokeError):
                check_api_deployment("production", SHA, transport=httpx.MockTransport(lambda r: response))

    def test_network_exception_does_not_leak_payload(self):
        def responder(request):
            raise httpx.ConnectError("credential=very-secret-token", request=request)
        with self.assertRaises(ApiSmokeError) as context:
            check_api_deployment("production", SHA, transport=httpx.MockTransport(responder))
        self.assertNotIn("very-secret-token", str(context.exception))

    def test_cli_invalid_sha_does_not_make_request(self):
        with patch("sys.argv", ["smoke", "--environment", "production", "--expected-sha", "invalid"]):
            with self.assertRaises(SystemExit) as context:
                main()
            self.assertEqual(context.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
