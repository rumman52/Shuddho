"""V-01: remaining credentialed GitHub audits must reject all HTTP redirects.

Exercise the real urllib transport with loopback origins only, no real credentials.
An untrusted GitHub API redirect must never receive an Actions bearer token.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from scripts.independent_review_gate import ReviewGateError, _get_json as read_review
from scripts.main_protection_audit import GovernanceAuditError, _get_json as read_policy


@contextmanager
def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _Quiet(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass


READERS = [
    pytest.param(read_policy, GovernanceAuditError, id="main-push-governance-audit"),
    pytest.param(read_review, ReviewGateError, id="independent-review-merge-gate"),
]


@pytest.mark.parametrize("reader,error_type", READERS)
def test_credential_is_not_replayed_on_cross_origin_302(reader, error_type):
    recipient_auth = []

    class Recipient(_Quiet):
        def do_GET(self):
            recipient_auth.append(self.headers.get("Authorization"))
            body = b'{"accepted":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Recipient) as recipient:
        class Origin(_Quiet):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", recipient + "/collect")
                self.end_headers()

        with _serve(Origin) as origin:
            with pytest.raises(error_type, match="unavailable"):
                reader(origin + "/repos/owner/repo", "fake-read-token")

    assert recipient_auth == []


@pytest.mark.parametrize("reader,error_type", READERS)
def test_even_same_origin_307_is_not_followed(reader, error_type):
    paths = []

    class Origin(_Quiet):
        def do_GET(self):
            paths.append(self.path)
            if self.path == "/initial":
                self.send_response(307)
                self.send_header("Location", "/target")
                self.end_headers()
                return
            body = b'{"accepted":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Origin) as origin:
        with pytest.raises(error_type, match="unavailable"):
            reader(origin + "/initial", "fake-read-token")

    assert paths == ["/initial"]


@pytest.mark.parametrize("reader,error_type", READERS)
def test_direct_read_preserves_authenticated_json_response(reader, error_type):
    auth_seen = []

    class Direct(_Quiet):
        def do_GET(self):
            auth_seen.append(self.headers.get("Authorization"))
            body = b'{"status":"direct","protected":false}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Direct) as origin:
        response = reader(origin + "/direct", "fake-read-token")

    assert response == {"status": "direct", "protected": False}
    assert auth_seen == ["Bearer fake-read-token"]
