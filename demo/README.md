# Northstar private demonstration

This Python standard-library HTTP service demonstrates catalog's Managed Identity reading an orders-owned Blob container. The application listens on port 8080 and runs as UID/GID 10001. It has no package installation step.

Start with [the demonstration runbook](../docs/demo.md) and [manual acceptance](../docs/acceptance.md). All execution is pending. The service is an operator probe for the private dev environment; keep public ingress disabled and probes disabled in production. Azure resource RBAC does not authorize arbitrary application HTTP requests.

Routes are `GET /health`, `GET /probe/read`, `GET /probe/restricted`, and `POST /probe/write`. Probe responses contain only the operation and downstream HTTP status. The service never returns Blob contents, request URLs, access tokens or identity headers. Probe targets and write content are fixed in code. Query strings and caller-supplied bodies cannot change them.

The App Service platform supplies `IDENTITY_ENDPOINT` and `IDENTITY_HEADER`. Terraform supplies `AZURE_WORKLOAD_CLIENT_ID`, `ORDERS_STORAGE_ACCOUNT`, `WEBSITES_PORT=8080`, and `ENABLE_PROBES=true` for catalog/dev only. Other workloads and prod use `ENABLE_PROBES=false`. No account key, SAS token, developer identity or client secret is supported.
