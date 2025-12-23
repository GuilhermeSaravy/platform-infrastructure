# Private demonstration workload

All commands in this runbook are for later manual execution. No image, application or cloud command was run during code generation. Begin with [startup](startup.md) to prepare the tenant, subscription, external groups, bootstrap, policies and dev network.

The fictional catalog and orders projects each have an `api` application runtime. Catalog/dev can read `orders/dev`'s `exports` container only after orders' separate access state grants `Storage Blob Data Reader` at container scope. The `restricted` container remains inaccessible. A workload UAMI belongs to its project resources state; access state reads its explicit Azure identity contract by name and never consumes the source project's Terraform state.

App Service Linux Basic B1 provides private ingress through an App Service Private Endpoint and outbound integration through a separate delegated subnet. Blob uses its own Private Endpoint. Public ingress and storage public network access stay disabled. Networking allows the route; RBAC permits the individual data operation. Neither private networking nor Azure resource RBAC implements application HTTP authorization.

The probe endpoints are a private development operator tool, enabled only on catalog/dev. Any operator with network access to this tool can invoke its fixed operations. Do not expose the tool to the Internet, put secrets in URLs, or use it as an application authorization example. Keep `ENABLE_PROBES=false` on orders and all prod applications. `/health` is available without a token and verifies process health only.

| Route | Workload operation | Expected after grant |
| --- | --- | --- |
| `GET /health` | No Azure request | HTTP 200, `{"status":"ok"}` |
| `GET /probe/read` | Bearer GET `exports/acceptance.txt` | HTTP 200, downstream 200 |
| `GET /probe/restricted` | Bearer GET `restricted/acceptance.txt` | HTTP 200, downstream 403 |
| `POST /probe/write` with empty body | Bearer PUT fixed text to `exports/should-not-write.txt` | HTTP 200, downstream 403 |

The outer probe status is 200 when a Blob HTTP response was obtained, including denials. Its JSON contains only `operation` and `downstream_status`. Missing identity settings, token failures and transport failures return outer HTTP 503 and `{"error":"probe_unavailable"}`. A Blob 404 means missing fixture data and cannot establish authorization denial. The application suppresses access logs, exception details and downstream bodies. Redirects are rejected so a downstream redirect cannot forward credentials to another host.

The App Service local identity protocol uses `api-version=2019-08-01`, the `https://storage.azure.com/` audience and `client_id` to select the UAMI. Blob REST uses `x-ms-version=2023-11-03`. The app obtains a fresh platform token for each operation, but Azure may still cache authorization; the test retry window is bounded and never reports an unresolved delay as success. No storage key, SAS token, client secret or operator credential reaches the app.

| Setting | Supplied by | Meaning |
| --- | --- | --- |
| `IDENTITY_ENDPOINT`, `IDENTITY_HEADER` | App Service runtime | Local token endpoint and confidential request header; never set from a public client |
| `AZURE_WORKLOAD_CLIENT_ID` | Project resources module | Selected API UAMI client ID |
| `ORDERS_STORAGE_ACCOUNT` | Project resources module | `stnsordersdev<SUFFIX>` in the demonstration |
| `ENABLE_PROBES` | Project resources module | Exact `true` only for catalog/dev |
| `WEBSITES_PORT` | Project resources module | `8080` |

## Build and publish later

The historical baseline pins Python `3.12.8-slim-bookworm` by manifest digest and Docker Engine `27.5.1` (Buildx `0.20.0`, BuildKit `0.18.2`). There are no pip or apt dependencies. See the historical ledger for dated evidence and the distinction between availability then and current security/support. Reassess this old runtime baseline before production use.

From the repository root, a later local build is:

```sh
docker build --platform linux/amd64 -t northstar-demo:dev demo
```

Use the manually dispatched `.github/workflows/image.yml` workflow to build and publish the same Dockerfile to GHCR with `image_name` set to `northstar-demo`. Its permission-scoped `GITHUB_TOKEN` is supplied by GitHub; no personal access token or Azure login is required for publishing through that workflow. It publishes a commit-SHA tag and reports a digest reference. Package publication is an external action you initiate later. In the GHCR package settings, explicitly change the demonstration package visibility to **public** so App Service can pull without registry credentials. This image contains public sample code only.

Set local `DEMO_IMAGE` and the GitHub Actions variable of the same name to the reported immutable reference, replacing the placeholders:

```sh
export DEMO_IMAGE='ghcr.io/<lowercase-owner>/northstar-demo@sha256:<published-digest>'
```

Use a real published digest; the configuration checks reject placeholders. The four Azure secrets are documented separately in startup. Registry publication credentials are not substituted for Azure OIDC. App Service fetches this public image over its platform image-pull path; private application ingress and private Blob access remain separate.

Apply only dev resources using startup's dependency order, omitting `projects/orders/environments/dev/access` until the [before-grant test](acceptance.md) passes. Do not deploy prod merely to demonstrate this project. App Service startup, image availability, platform quota and RBAC propagation require manual verification.

## Local source checks later

The offline tests use mocks and do not contact Azure or start a server:

```sh
python3 -m unittest discover -s tests -p 'test_demo.py'
```

For a local process demonstration, `python3 demo/app.py` exposes `/health` on port 8080 and leaves probes disabled by default. This local health exercise does not emulate App Service Managed Identity or prove private networking. The complete deployed acceptance sequence is in [acceptance](acceptance.md).
