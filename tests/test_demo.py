"""Authored offline behavior tests. Run manually; no Azure or sockets required."""

import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError


SPEC = importlib.util.spec_from_file_location("northstar_demo", Path(__file__).parents[1] / "demo/app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class DemoTests(unittest.TestCase):
    def handler(self, path, headers=None):
        handler = app.Handler.__new__(app.Handler)
        handler.path = path
        handler.headers = headers or {}
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        return handler

    def result(self, handler):
        return json.loads(handler.wfile.getvalue())

    def test_health_does_not_request_identity(self):
        handler = self.handler("/health")
        with patch.object(app, "probe") as probe:
            handler.do_GET()
        probe.assert_not_called()
        self.assertEqual(self.result(handler), {"status": "ok"})

    def test_probes_require_explicit_enable(self):
        handler = self.handler("/probe/read")
        with patch.dict(os.environ, {"ENABLE_PROBES": "false"}), patch.object(app, "probe") as probe:
            handler.do_GET()
        handler.send_response.assert_called_once_with(404)
        probe.assert_not_called()

    def test_query_cannot_override_target(self):
        handler = self.handler("/probe/read?url=https://attacker.invalid&container=restricted")
        with patch.object(app, "probe") as probe:
            handler.do_GET()
        handler.send_response.assert_called_once_with(404)
        probe.assert_not_called()

    def test_post_body_cannot_override_write(self):
        handler = self.handler("/probe/write", {"Content-Length": "12"})
        with patch.object(app, "probe") as probe:
            handler.do_POST()
        handler.send_response.assert_called_once_with(400)
        probe.assert_not_called()

    def test_fixed_write_destination_and_content(self):
        response = MagicMock()
        response.__enter__.return_value.status = 403
        with patch.dict(os.environ, {"ORDERS_STORAGE_ACCOUNT": "stnsordersdevabcdef"}), \
                patch.object(app, "identity_token", return_value="secret-token"), \
                patch.object(app.HTTP, "open", return_value=response) as opened:
            self.assertEqual(app.probe("write"), 403)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url,
                         "https://stnsordersdevabcdef.blob.core.windows.net/exports/should-not-write.txt")
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.data, b"This write must be denied.\n")

    def test_invalid_account_cannot_inject_host(self):
        with patch.dict(os.environ, {"ORDERS_STORAGE_ACCOUNT": "account.attacker.invalid"}), \
                patch.object(app, "identity_token") as token:
            with self.assertRaises(ValueError):
                app.probe("read")
        token.assert_not_called()

    def test_http_denial_excludes_response_body(self):
        body = io.BytesIO(b"sensitive-downstream-body")
        error = HTTPError("https://private.invalid", 403, "private-detail", {}, body)
        with patch.dict(os.environ, {"ORDERS_STORAGE_ACCOUNT": "stnsordersdevabcdef"}), \
                patch.object(app, "identity_token", return_value="secret-token"), \
                patch.object(app.HTTP, "open", side_effect=error):
            self.assertEqual(app.probe("read"), 403)
        self.assertTrue(body.closed)

    def test_token_failure_never_leaks_exception(self):
        handler = self.handler("/probe/read")
        with patch.dict(os.environ, {"ENABLE_PROBES": "true"}), \
                patch.object(app, "probe", side_effect=RuntimeError("token-and-private-url")):
            handler.do_GET()
        handler.send_response.assert_called_once_with(503)
        self.assertEqual(self.result(handler), {"error": "probe_unavailable"})

    def test_success_contract_exposes_only_status(self):
        handler = self.handler("/probe/read")
        with patch.dict(os.environ, {"ENABLE_PROBES": "true"}), \
                patch.object(app, "probe", return_value=403):
            handler.do_GET()
        self.assertEqual(self.result(handler), {"operation": "read", "downstream_status": 403})

    def test_redirects_cannot_forward_credentials(self):
        self.assertIsNone(app.NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "https://attacker.invalid"))

    def test_identity_uses_selected_uami_and_storage_audience(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"access_token":"secret-token"}'
        identity = {"IDENTITY_ENDPOINT": "http://169.254.130.5:8081/msi/token",
                    "IDENTITY_HEADER": "secret-header",
                    "AZURE_WORKLOAD_CLIENT_ID": "11111111-2222-3333-4444-555555555555"}
        with patch.dict(os.environ, identity), patch.object(app.HTTP, "open", return_value=response) as opened:
            self.assertEqual(app.identity_token(), "secret-token")
        request = opened.call_args.args[0]
        self.assertIn("api-version=2019-08-01", request.full_url)
        self.assertIn("client_id=11111111-2222-3333-4444-555555555555", request.full_url)
        self.assertIn("resource=https%3A%2F%2Fstorage.azure.com%2F", request.full_url)
        self.assertEqual(request.get_header("X-identity-header"), "secret-header")


if __name__ == "__main__":
    unittest.main()
