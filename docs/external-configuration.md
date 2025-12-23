# External configuration

Fictional names, teams, access declarations and tags are tracked. Real Azure deployment identifiers and group mappings are supplied only at execution time. The [example contract](external-configuration.example.env) contains placeholders, is documentation rather than a loadable configuration, and deliberately fails preflight. Never populate that tracked file. Local `.env*`, `local/`, `.runtime/`, tfvars, state and generated mappings are ignored.

| Value | GitHub source | Consumer | Local equivalent |
| --- | --- | --- | --- |
| AZURE_TENANT_ID | Secret with this exact name | runtime_config → ARM_TENANT_ID → provider and backend native OIDC | Environment; same name, local Azure CLI login |
| AZURE_SUBSCRIPTION_ID | Secret with this exact name | runtime_config → ARM_SUBSCRIPTION_ID → provider and backend | Environment; same name, selected subscription |
| AZURE_CLIENT_ID | Secret with this exact name | runtime_config → ARM_CLIENT_ID → deployment UAMI OIDC | Optional with interactive user login; required for workflow |
| AZURE_TEAM_GROUP_IDS | Secret with this exact name | root.hcl and runtime_config → project-access → platform/identity-mapping | Environment JSON object; existing Entra groups |
| PLATFORM_UNIQUE_SUFFIX | Actions variable | root.hcl, bootstrap and Azure global names | Environment; choose once, keep stable |
| DEMO_IMAGE | Actions variable | project-resources container image | Environment; public GHCR digest reference |
| TF_VAR_github_repository | Local environment during bootstrap | Federated credential subject repo:owner/repository:environment:platform | Real owner/repository, not a URL |
| TF_VAR_bootstrap_operator_object_id | Local sensitive environment | Operator state-container data role | Signed-in user's real Entra object ID |
| TF_VAR_unique_suffix | Local bootstrap environment | State account naming | Same value as PLATFORM_UNIQUE_SUFFIX |

The secret `AZURE_TEAM_GROUP_IDS` must contain this JSON shape, with real UUIDs substituted privately:

```json
{
  "platform-engineering": "<platform-group-object-id>",
  "commerce-backend": "<backend-group-object-id>",
  "commerce-frontend": "<frontend-group-object-id>"
}
```

These IDs refer to existing security groups named grp-platform-engineering, grp-commerce-backend and grp-commerce-frontend. Their lifecycle and membership belong to organization-identity. They are reused across dev and prod. AZURE_CLIENT_ID is the **client ID**, not the principal/object ID, of id-platform-deployment created by local bootstrap. No client secret is created or accepted as a substitute.

After bootstrap, open the actual GitHub repository → Settings → Environments → create `platform`. Restrict deployment branches to main and configure required reviewers (availability depends on repository visibility/plan). In the environment's Secrets section, add the four exact secret names above. Use the UI privately; do not paste values into issues, commits or workflow inputs. Add PLATFORM_UNIQUE_SUFFIX and DEMO_IMAGE as repository or environment Actions variables. Every infrastructure workflow uses environment platform, matching the federated credential exactly. Environment protection is a manual prerequisite; YAML alone cannot create it.

`runtime_config.py` rejects missing, malformed, zero/common placeholder UUIDs, incorrect/duplicate team mappings, placeholder suffixes/images and missing GitHub OIDC permission variables. It never logs values or authenticates. It cannot prove a UUID belongs to the correct tenant or group: verify that manually using your account. `infra.py` also checks project declarations, allowlisted state paths, global-name lengths and saved-plan/source consistency before invoking Terragrunt. Raw command output is captured to a mode-600 temporary file, used only for categorical errors and deleted. Identity mappings pass in subprocess environments; no mapping file or plan artifact is uploaded.

Do not use shell tracing, printenv, echo of these variables, Terraform debug logs or GitHub step debugging. State and plans necessarily contain resource identifiers: retain them privately, never upload them as ordinary workflow artifacts. The wrapper clears common alternate credentials and tracing options so OIDC/interactive CLI paths are deliberate. A privileged operator can inspect a saved local plan privately; never paste its contents into public logs.

Workflow authentication uses Terraform's native GitHub OIDC support (`id-token: write`, ARM_USE_OIDC=true, ARM_USE_AZUREAD=true). Terraform exchanges GitHub's short-lived assertion for the deployment UAMI. No Azure CLI login step is needed in workflows. The local wrapper instead uses an existing interactive Azure CLI user login. AZURE_CLIENT_ID may be omitted locally before the deployment UAMI exists; the other values and real team mappings remain required for normal units. Bootstrap is a separate local root and does not require the UAMI or team map to exist first.

AzureRM 4.27.0 performs ARM ListKeys reads for storage account resources when the deployment principal can read keys, even with shared-key authorization disabled. Computed disabled keys/connection strings may therefore exist in confidential resource state; no project uses them. The access module derives the destination account ARM path and reads only its container, avoiding another storage-account data-source key snapshot. Never export state or plans into logs/artifacts.
