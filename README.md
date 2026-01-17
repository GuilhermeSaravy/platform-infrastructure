# Platform Infrastructure

Platform Infrastructure provides a shared starting point for setting up projects on **Microsoft Azure**. Teams describe a project's owner, environments, services and access needs in configuration files. The platform turns those declarations into Azure resources using **Terraform**, organizes their configuration with **Terragrunt**, and provides manually triggered **GitHub Actions** workflows.

As more projects are added, setting up networking, permissions and security rules separately creates repeated work and inconsistent settings. This project puts those common rules in one place. A new project can reuse them by adding its own configuration, without changing shared modules or a central project list.

The included example represents **Northstar Commerce**, a fictional company with `catalog` and `orders` projects in `dev` and `prod`. It defines:

- A shared network for each environment, with separate resource groups for each project. Dev and prod are not connected by default.
- Private applications on Azure App Service and private Azure Blob storage.
- Common naming, ownership and cost tags, allowed regions, and security policies.
- Permissions for existing team groups and Managed Identity access for applications, without storage keys or client secrets.
- Local setup for state storage and GitHub OIDC authentication, followed by manual plan and apply workflows.

One example connects these pieces: the catalog dev application receives read-only access to the orders dev `exports` container. Orders owns the grant; writing files and reading its `restricted` container remain outside that grant. Separate resource and access states make it possible to test access before and after applying the permission.

The repository separates project needs from the code that implements them:

```text
platform-infrastructure/
├── organization/       # Shared defaults, naming, access profiles and policies
├── platform/           # Initial setup, identity mapping, governance and networks
├── modules/            # Reusable Terraform code for Azure resources
├── projects/           # Catalog and orders declarations, split by environment
├── templates/          # Complete starting point for another project
├── demo/               # Small application demonstrating Managed Identity access
├── scripts/            # Configuration checks, onboarding and manual operations
├── tests/              # Authored offline tests and live acceptance procedures
├── docs/               # Architecture, setup, operation and cleanup guides
└── .github/workflows/  # Manually triggered checks, image build, plan and apply
```

**Start with the [manual startup guide](docs/startup.md).** It explains the Azure prerequisites, local authentication, initial setup, GitHub secrets, dev deployment and cleanup. Existing Entra groups are supplied externally; this repository does not create groups or manage their members. No real Azure identifiers or credentials are committed.

For more detail:

- [Architecture and ownership](docs/architecture.md)
- [External configuration and the four GitHub secrets](docs/external-configuration.md)
- [Adding a project](docs/onboarding.md) and the [reusable template](templates/README.md)
- [Acceptance tests](docs/acceptance.md)
- [Implementation status](docs/status.md), [historical sources](docs/historical-audit.json) and [chronology](docs/evolution.md)

The code and procedures have been reviewed by reading. Executable checks, builds and cloud deployment remain pending manual execution. Nothing runs automatically on push or pull request. Commit dates follow a reconstructed portfolio timeline; they do not prove work occurred on those dates.
