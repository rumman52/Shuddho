import re

from services.api.shuddho_api.app import ALLOWED_ORIGIN_REGEX, ALLOWED_ORIGINS, detector_service, health


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


def test_cors_keeps_production_frontend_origin() -> None:
    assert "https://shuddho-web-editor.vercel.app" in ALLOWED_ORIGINS
