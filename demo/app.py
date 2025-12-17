"""Private development probe using the App Service user-assigned identity."""

import json
import os
import re
import uuid
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


HTTP = build_opener(ProxyHandler({}), NoRedirect())
OPERATIONS = {
    "read": ("GET", "exports/acceptance.txt"),
    "restricted": ("GET", "restricted/acceptance.txt"),
    "write": ("PUT", "exports/should-not-write.txt"),
}


def identity_token():
    endpoint = os.environ["IDENTITY_ENDPOINT"]
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Invalid identity endpoint")
    client_id = str(uuid.UUID(os.environ["AZURE_WORKLOAD_CLIENT_ID"]))
    query = urlencode({"api-version": "2019-08-01", "resource": "https://storage.azure.com/",
                       "client_id": client_id})
    request = Request(endpoint + "?" + query,
                      headers={"X-IDENTITY-HEADER": os.environ["IDENTITY_HEADER"]})
    with HTTP.open(request, timeout=10) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError("Identity response too large")
    token = json.loads(payload)["access_token"]
    if not isinstance(token, str) or not token or any(c.isspace() for c in token):
        raise ValueError("Invalid identity response")
    return token


def probe(operation):
    method, path = OPERATIONS[operation]
    account = os.environ["ORDERS_STORAGE_ACCOUNT"]
    if not re.fullmatch(r"[a-z0-9]{3,24}", account):
        raise ValueError("Invalid storage account")
    headers = {"Authorization": "Bearer " + identity_token(),
               "x-ms-version": "2023-11-03", "x-ms-date": formatdate(usegmt=True)}
    body = None
    if method == "PUT":
        headers["x-ms-blob-type"] = "BlockBlob"
        headers["Content-Type"] = "text/plain"
        body = b"This write must be denied.\n"
    request = Request(f"https://{account}.blob.core.windows.net/{path}",
                      data=body, headers=headers, method=method)
    try:
        with HTTP.open(request, timeout=10) as response:
            return response.status
    except HTTPError as error:
        status = error.code
        error.close()
        return status


class Handler(BaseHTTPRequestHandler):
    server_version = "NorthstarDemo"
    sys_version = ""

    def log_message(self, format_string, *arguments):
        pass

    def _json(self, status, payload):
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _probe(self, operation):
        if os.environ.get("ENABLE_PROBES") != "true":
            self._json(404, {"error": "not_found"})
            return
        try:
            downstream = probe(operation)
        except Exception:
            self._json(503, {"error": "probe_unavailable"})
            return
        self._json(200, {"operation": operation, "downstream_status": downstream})

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/probe/read":
            self._probe("read")
        elif self.path == "/probe/restricted":
            self._probe("restricted")
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
            self.close_connection = True
            self._json(400, {"error": "request_body_not_supported"})
        elif self.path == "/probe/write":
            self._probe("write")
        else:
            self._json(404, {"error": "not_found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
