# Platform Infrastructure

An Azure foundation for the fictional **Northstar Commerce** organization. Catalog and orders declare ownership, dev/prod environments, capabilities and access intent. The platform translates those declarations into private runtimes, storage, governance and shared environment networks.

**Start with [the manual startup guide](docs/startup.md).** This repository contains code and authored acceptance procedures. Executable verification and cloud deployment are pending manual execution. No Azure identifiers or credentials are populated.

- [Architecture and ownership](docs/architecture.md)
- [External configuration and the four GitHub secrets](docs/external-configuration.md)
- [Manual startup and dev demonstration](docs/startup.md)
- [Acceptance procedures](docs/acceptance.md)
- [Historical selection and source ledger](docs/historical-audit.json)
- [Reusable onboarding template](templates/README.md) and [offline generator](docs/onboarding.md)
- [Implementation status](docs/status.md)

Quick start after preparing a subscription, groups and local tools: authenticate interactively, supply external environment variables, bootstrap from `platform/bootstrap` using retained local state, publish the demo image, then initialize/plan/apply dev network and project resource units. Apply governance, run the denied-before-grant acceptance sequence, apply `projects/orders/environments/dev/access`, and run after-grant tests. Exact commands and cleanup are in the startup guide. Nothing runs automatically on push or pull request.

The initial development calendar is reconstructed in December 2025; later onboarding and review improvements are reserved for January and February 2026. Historical dates do not prove contemporaneous work. Exact local Git hashes and actual recording times are maintained in the shared registry outside this repository.
