"""Post-merge V-01 evidence collection must never replay bearer auth on 30x.

The audit is read-only but can receive a privileged GitHub read credential.
Loopback servers provide real HTTP redirect behavior without external traffic.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from scripts.v01_merge_evidence import EvidenceError, _get_json


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


def test_postmerge_credential_never_reaches_cross_origin_redirect_destination():
    destination_requests = []

    class Destination(_Quiet):
        def do_GET(self):
            destination_requests.append(self.headers.get("Authorization"))
            body = b'{"unsafe_redirect":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Destination) as destination:

        class Origin(_Quiet):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", destination + "/collect")
                self.end_headers()

        with _serve(Origin) as origin:
            with pytest.raises(EvidenceError, match="GitHub evidence read failed"):
                _get_json(origin + "/actions/runs/42", "fake-read-token")

    assert destination_requests == []


def test_postmerge_audit_does_not_follow_same_origin_redirect():
    paths_seen = []

    class Origin(_Quiet):
        def do_GET(self):
            paths_seen.append(self.path)
            if self.path == "/redirect":
                self.send_response(307)
                self.send_header("Location", "/second-request")
                self.end_headers()
                return
            body = b'{"unsafe_redirect":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Origin) as origin:
        with pytest.raises(EvidenceError, match="GitHub evidence read failed"):
            _get_json(origin + "/redirect", "fake-read-token")

    assert paths_seen == ["/redirect"]


@pytest.mark.parametrize("token,expected_auth", [
    ("fake-read-token", "Bearer fake-read-token"),
    ("", None),
])
def test_postmerge_audit_preserves_direct_json_reads(token, expected_auth):
    received_auth = []

    class Direct(_Quiet):
        def do_GET(self):
            received_auth.append(self.headers.get("Authorization"))
            body = b'{"run_id":42,"success":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Direct) as origin:
        result = _get_json(origin + "/pulls/42", token)

    assert result == {"run_id": 42, "success": True}
    assert received_auth == [expected_auth]
