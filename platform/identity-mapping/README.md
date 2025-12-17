# External team mapping contract

`AZURE_TEAM_GROUP_IDS` is a JSON object mapping platform-engineering, commerce-backend and commerce-frontend to existing Entra security group object IDs. The Terraform module validates ID shape and logical key completeness and returns a sensitive resolution map. The Python runtime preflight rejects absent, placeholder, zero and malformed values before invoking Terraform. Actual existence, group type and tenant association require manual Azure verification.

Entra groups `grp-platform-engineering`, `grp-commerce-backend` and `grp-commerce-frontend` and their membership belong to `organization-identity`. This repository never creates or manages them. Use one group across environments and apply environment-specific access profiles. Workload UAMIs belong to project resource state. Do not commit local maps or print map values; only use runtime environment injection. Follow docs/external-configuration.md.
