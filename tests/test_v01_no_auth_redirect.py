"""V-01 policy audit must not forward an administrator GitHub token on redirects.

urllib.request.urlopen follows 30x redirects by default, and Python's
HTTPRedirectHandler copies Authorization to the redirected request. These tests
use only loopback HTTP endpoints; no real token or external service is needed.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError

import pytest

from scripts.v01_native_protection_audit import _fetch_json


@contextmanager
def _serve(handler_type):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return


def test_live_policy_read_never_sends_bearer_to_redirect_target():
    target_requests = []

    class Recipient(_QuietHandler):
        def do_GET(self):
            target_requests.append(self.headers.get("Authorization"))
            body = b'{"redirected":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Recipient) as recipient_url:

        class Initial(_QuietHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", recipient_url + "/capture")
                self.end_headers()

        with _serve(Initial) as origin_url:
            with pytest.raises(HTTPError) as rejected:
                _fetch_json(origin_url + "/rulesets", "fake-admin-test-token")

    assert rejected.value.code == 302
    assert target_requests == []


def test_live_policy_read_rejects_same_origin_redirect_too():
    visited = []

    class Redirect(_QuietHandler):
        def do_GET(self):
            visited.append(self.path)
            if self.path == "/redirect":
                self.send_response(301)
                self.send_header("Location", "/after-redirect")
                self.end_headers()
                return
            body = b'{"redirected":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Redirect) as url:
        with pytest.raises(HTTPError) as rejected:
            _fetch_json(url + "/redirect", "fake-admin-test-token")

    assert rejected.value.code == 301
    assert visited == ["/redirect"]


def test_live_policy_read_still_parses_direct_json_response():
    received_auth = []

    class Direct(_QuietHandler):
        def do_GET(self):
            received_auth.append(self.headers.get("Authorization"))
            body = b'{"enforcement":"active"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Direct) as url:
        result = _fetch_json(url + "/rulesets", "fake-admin-test-token")

    assert result == {"enforcement": "active"}
    assert received_auth == ["Bearer fake-admin-test-token"]
