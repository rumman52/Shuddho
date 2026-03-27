import re

from services.api.shuddho_api.app import (
    ALLOWED_ORIGIN_REGEX,
    ALLOWED_ORIGINS,
    _parse_allowed_origins,
    detector_service,
    health,
)


def test_health_reports_detector_status() -> None:
    response = health()

    assert response.status == "ok"
    assert response.detector_loaded is detector_service.is_loaded()
    assert response.detector_checkpoint == detector_service.checkpoint_path
    assert response.allowed_origins == ALLOWED_ORIGINS


def test_cors_allows_extension_origin() -> None:
    origin = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    assert re.fullmatch(ALLOWED_ORIGIN_REGEX, origin)


def test_cors_allows_localhost_dev_origin() -> None:
    origin = "http://localhost:5173"

    assert re.fullmatch(ALLOWED_ORIGIN_REGEX, origin)


def test_default_allowed_origins_include_local_dev_hosts() -> None:
    assert "http://127.0.0.1:5173" in ALLOWED_ORIGINS
    assert "http://localhost:5173" in ALLOWED_ORIGINS


def test_cors_keeps_production_frontend_origin() -> None:
    assert "https://shuddho-web-editor.vercel.app" in ALLOWED_ORIGINS


def test_parse_allowed_origins_supports_trycloudflare_origin() -> None:
    allowed_origins = _parse_allowed_origins(
        "https://random-name.trycloudflare.com, https://shuddho-web-editor.vercel.app"
    )

    assert allowed_origins == [
        "https://random-name.trycloudflare.com",
        "https://shuddho-web-editor.vercel.app",
    ]
