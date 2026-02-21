"""Manual dev-only live acceptance from a host with private Azure connectivity."""

import argparse
import ipaddress
import json
import re
import socket
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class Failure(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


HTTP = build_opener(ProxyHandler({}), NoRedirect())


def configured_dev_network():
    try:
        defaults = json.loads((Path(__file__).resolve().parents[1] / "organization/defaults.yaml").read_text(encoding="utf-8"))
        network = ipaddress.ip_network(defaults["azure"]["network_cidrs"]["dev"])
    except (OSError, ValueError, KeyError, TypeError):
        raise Failure("Cannot read dev network defaults; use a checkout with valid organization/defaults.yaml") from None
    if network.version != 4 or network.prefixlen != 16:
        raise Failure("The configured dev network must use the supported IPv4 /16 allocation")
    return network


def private_dns(hostname, dev_network):
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    except OSError:
        raise Failure("Private DNS lookup failed; check VPN and conditional DNS forwarding") from None
    if not addresses or any(ipaddress.ip_address(address) not in dev_network for address in addresses):
        raise Failure("DNS must resolve exclusively inside the dev VNet configured in organization/defaults.yaml")


def request_json(base, path, method="GET"):
    request = Request(base + path, method=method, data=b"" if method == "POST" else None)
    try:
        with HTTP.open(request, timeout=30) as response:
            if response.status != 200:
                raise Failure("Application returned an unexpected status")
            payload = response.read(4097)
        if len(payload) > 4096:
            raise Failure("Application response exceeded the expected contract")
        return json.loads(payload)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise Failure("Application transport or identity probe failed; inspect private connectivity and configuration") from None


def expect_probe(base, operation, expected, attempts=1):
    method = "POST" if operation == "write" else "GET"
    for attempt in range(attempts):
        payload = request_json(base, "/probe/" + operation, method)
        if (not isinstance(payload, dict) or set(payload) != {"operation", "downstream_status"}
                or payload["operation"] != operation or type(payload["downstream_status"]) is not int):
            raise Failure("Application probe returned an unexpected contract")
        status = payload["downstream_status"]
        if status == expected:
            print(f"PASS: {operation} returned expected Blob status {expected}")
            return
        if attempts > 1 and status == 403 and attempt + 1 < attempts:
            time.sleep(20)
            continue
        if status == 404:
            raise Failure("Fixture blob is missing (404); this does not prove authorization denial")
        raise Failure(f"Unexpected Blob status {status} for {operation}; expected {expected}")
    raise Failure("Read authorization did not propagate within the bounded retry window")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--catalog-url", required=True)
    parser.add_argument("--storage-account", required=True)
    arguments = parser.parse_args()
    url = urlsplit(arguments.catalog_url)
    match = re.fullmatch(r"app-ns-catalog-dev-([a-z0-9]{6,10})\.azurewebsites\.net", url.hostname or "")
    if (url.scheme != "https" or not match or url.port not in (None, 443)
            or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
        raise Failure("Use the deployed catalog/dev HTTPS hostname with no query, credentials or path")
    if arguments.storage_account != "stnsordersdev" + match.group(1):
        raise Failure("Storage account must match the orders/dev account for the catalog suffix")
    dev_network = configured_dev_network()
    private_dns(url.hostname, dev_network)
    private_dns(arguments.storage_account + ".blob.core.windows.net", dev_network)
    base = arguments.catalog_url.rstrip("/")
    if request_json(base, "/health") != {"status": "ok"}:
        raise Failure("Health endpoint did not return the expected contract")
    print("PASS: private dev DNS and HTTPS health")
    if arguments.phase == "before":
        expect_probe(base, "read", 403)
    else:
        expect_probe(base, "read", 200, attempts=12)
        expect_probe(base, "write", 403)
        expect_probe(base, "restricted", 403)


if __name__ == "__main__":
    try:
        main()
    except Failure as error:
        print("FAIL: " + str(error), file=sys.stderr)
        sys.exit(1)
    except ValueError:
        print("FAIL: malformed URL or network configuration", file=sys.stderr)
        sys.exit(1)
