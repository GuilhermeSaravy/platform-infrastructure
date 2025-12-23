# Manual startup

This guide starts from **no Azure tenant or subscription**. Every command below is authored for your later manual execution. Code generation did not execute checks, tests, formatting, validation, initialization, plans, builds, authentication, workflows or deployments. Read [architecture](architecture.md), [external configuration](external-configuration.md) and [acceptance](acceptance.md) first. Shell examples use bash/zsh from the repository root unless a directory change is shown. Keep shell tracing off.

## 1. Tools and historical baseline

Use Terraform **1.10.5**, Terragrunt **0.77.22**, AzureRM **4.27.0**, Python **3.12.8**, Azure CLI **2.70.0**, and Docker Engine **27.5.1** for local demonstration image builds. Terraform/AzureRM are exact constraints; release checksum entries are committed in `.terraform.lock.hcl`. No provider initialization generated that file: its zip hashes were copied from HashiCorp's release SHA256SUMS. Manual initialization must verify the package. No external Terraform modules, pip application dependencies or package-resolution step are needed for the application/check scripts.

The dated source ledger is [historical-audit.json](historical-audit.json). These versions existed before the reconstructed December 2025 baseline; that does not establish current support, security, Azure capacity or successful deployment. The immutable base-image digest pins its Debian filesystem. Hosted Ubuntu24 images and their bundled Docker engine evolve; the image workflow uses the hosted Docker engine and does not claim byte-identical reproduction of the historical local engine. Review current security before production use; any version migration deserves a separate audit and verification.

Download the exact CLI releases from [Terraform](https://releases.hashicorp.com/terraform/1.10.5/), [Terragrunt](https://github.com/gruntwork-io/terragrunt/releases/tag/v0.77.22), [Python](https://www.python.org/downloads/release/python-3128/), [Azure CLI](https://github.com/Azure/azure-cli/releases/tag/azure-cli-2.70.0), and [Docker](https://docs.docker.com/engine/release-notes/27/#2751). Prefer the vendor's matching OS/architecture artifacts, signed checksum verification and isolated tool paths. Azure CLI's versioned installer/release package bundles its own dependencies; do not assume an unpinned pip resolution recreates that bundle. If the archived platform package is unavailable today, stop and audit an explicitly chosen replacement before using it; do not silently install latest. Docker is needed only to build the image locally; the manual image workflow is another path. GitHub setup-tools installs pinned Python/Terraform/Terragrunt without Azure CLI or Docker initialization.

For example, on Linux x86_64, install Terraform/Terragrunt into a private user tool directory after downloading and verifying vendor signatures as appropriate:

```sh
mkdir -p "$HOME/.local/bin" .runtime/downloads
chmod 700 .runtime .runtime/downloads
cd .runtime/downloads
curl -fLO https://releases.hashicorp.com/terraform/1.10.5/terraform_1.10.5_linux_amd64.zip
curl -fLO https://releases.hashicorp.com/terraform/1.10.5/terraform_1.10.5_SHA256SUMS
awk '$2 == "terraform_1.10.5_linux_amd64.zip"' terraform_1.10.5_SHA256SUMS | sha256sum -c -
unzip terraform_1.10.5_linux_amd64.zip
install -m 0755 terraform "$HOME/.local/bin/terraform"
curl -fLO https://github.com/gruntwork-io/terragrunt/releases/download/v0.77.22/terragrunt_linux_amd64
curl -fLO https://github.com/gruntwork-io/terragrunt/releases/download/v0.77.22/SHA256SUMS
awk '$2 == "terragrunt_linux_amd64"' SHA256SUMS | sha256sum -c -
install -m 0755 terragrunt_linux_amd64 "$HOME/.local/bin/terragrunt"
cd ../..
export PATH="$HOME/.local/bin:$PATH"
```

On Apple Silicon use darwin_arm64 release artifacts and `shasum -a 256 -c` instead. Install Python 3.12.8 using the matching official installer/source and ensure `python3` selects it. Install the exact Azure CLI release through its versioned platform package. Confirm tool versions privately before proceeding. These installation/version commands are also pending.

## 2. Accounts, tenant, subscription and external groups

Create or obtain an Azure account and pay-as-you-go or authorized sandbox subscription through the Azure portal. Ensure you understand billing, trial limits and the associated Microsoft Entra tenant. A dedicated demonstration subscription is strongly preferred because bootstrap grants subscription-wide management authority. Obtain subscription Owner or equivalent Contributor + User Access Administrator + Resource Policy Contributor privileges; tenant group administration is a separate permission.

Using your organization's separate identity process/repository, prepare **security groups** grp-platform-engineering, grp-commerce-backend and grp-commerce-frontend in that tenant and their intended members. Do not create per-environment groups. Obtain each existing group's object ID privately through Entra ID → Groups → group → Overview. Verify security-enabled status and tenant. This repository manages only role assignments to the supplied groups. No real values are needed to read or generate this code.

After preparing accounts, authenticate interactively and select the subscription:

```sh
set +x
umask 077
export AZURE_TENANT_ID='<real-tenant-uuid>'
export AZURE_SUBSCRIPTION_ID='<real-subscription-uuid>'
az login --tenant "$AZURE_TENANT_ID" --output none
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
export ARM_TENANT_ID="$AZURE_TENANT_ID"
export ARM_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID"
export ARM_USE_CLI=true
export ARM_USE_OIDC=false
export ARM_USE_AZUREAD=true
unset ARM_CLIENT_SECRET ARM_CLIENT_CERTIFICATE_PATH ARM_ACCESS_KEY ARM_SAS_TOKEN TF_LOG TF_LOG_PATH
```

Never run these placeholder commands until replacing values privately. `az account show` can confirm your selected tenant/subscription in a private terminal; do not paste its output into logs. Enable required resource providers later as the operator (registration is deliberately disabled inside Terraform):

```sh
for provider in Microsoft.Storage Microsoft.ManagedIdentity Microsoft.Network Microsoft.Web; do
  az provider register --namespace "$provider" --wait --output none
done
```

Microsoft.Resources and Microsoft.Authorization must also be available; inspect their registration state privately. Registration may require several minutes and subscription authority. Check West Europe Linux B1 availability/quota and subnet delegation support for Microsoft.Web/serverFarms before spending. If organizational policy prohibits the public state endpoint exception, use a private runner/backend design after deliberate adaptation and verification.

## 3. Supply local external configuration

From the checkout root:

```sh
export AZURE_TEAM_GROUP_IDS='{"platform-engineering":"<platform-group-object-id>","commerce-backend":"<backend-group-object-id>","commerce-frontend":"<frontend-group-object-id>"}'
export PLATFORM_UNIQUE_SUFFIX='<choose-your-suffix>'
export TF_VAR_unique_suffix="$PLATFORM_UNIQUE_SUFFIX"
export TF_VAR_github_repository='<your-actual-owner>/platform-infrastructure'
export TF_VAR_bootstrap_operator_object_id="$(az ad signed-in-user show --query id -o tsv)"
unset AZURE_CLIENT_ID ARM_CLIENT_ID
```

Use real UUIDs and one stable **6–10 lowercase alphanumeric** suffix, for example generated locally with `python3 -c 'import secrets; print(secrets.token_hex(4))'`. This example generation is pending too. Check Azure global storage and web-app name availability before bootstrap: backend `stnorthstartf<SUFFIX>`, orders storage `stnsordersdev<SUFFIX>` / `stnsordersprod<SUFFIX>`, and web apps `app-ns-catalog-dev-<SUFFIX>` / `app-ns-orders-dev-<SUFFIX>` (plus prod). Storage names must be 3–24 alphanumeric characters; web names are globally unique. Keep the suffix unchanged after resources/state exist. Use Azure portal/name availability interfaces privately; a naming collision requires a new suffix before the initial deployment or an explicit migration later.

Keep local values in the session or an ignored private `.env.local` written with mode600. Do not source the tracked example contract. If you need to transfer this configuration to a private operator host, use your approved secret channel. The four GitHub secrets are not created at this stage. Local normal units can use interactive user login with AZURE_CLIENT_ID omitted.

Offline declaration and runtime checks can now be run manually:

```sh
python3 scripts/check_config.py
python3 scripts/runtime_config.py
```

These commands do not authenticate, but they have **not** been run during generation. Malformed placeholders fail with instructions and no values printed.

## 4. Bootstrap from an existing authenticated local identity

The remote backend and OIDC identity must be created before workflows can use them. Bootstrap is a standalone Terraform root with local state; the normal wrapper deliberately excludes it. Use protected local files and redirect Terraform output to private logs because Azure identifiers and computed values may otherwise appear on screen:

```sh
mkdir -p .runtime
chmod 700 .runtime
terraform -chdir=platform/bootstrap init -input=false -lockfile=readonly > .runtime/bootstrap-init.log 2>&1
terraform -chdir=platform/bootstrap plan -input=false -out=../../.runtime/bootstrap.tfplan > .runtime/bootstrap-plan.log 2>&1
terraform -chdir=platform/bootstrap show ../../.runtime/bootstrap.tfplan > .runtime/bootstrap-review.txt
```

Read `.runtime/bootstrap-review.txt` privately. Ensure only the state RG/storage/container, deployment UAMI, federated credential and intended roles will be created. Then:

```sh
terraform -chdir=platform/bootstrap apply -input=false ../../.runtime/bootstrap.tfplan > .runtime/bootstrap-apply.log 2>&1
rm -f .runtime/bootstrap.tfplan .runtime/bootstrap-review.txt .runtime/bootstrap-init.log .runtime/bootstrap-plan.log .runtime/bootstrap-apply.log
```

If any command fails, stop; inspect its protected log privately and correct the cause before continuing. Do not paste raw logs into GitHub. Never use a semicolon chain that applies after a failed plan. Back up `platform/bootstrap/terraform.tfstate` encrypted outside this repository immediately. It contains sensitive information and is excluded from Git. Obtain deployment UAMI client ID privately, without printing it:

```sh
export AZURE_CLIENT_ID="$(az identity show --resource-group rg-platform-state --name id-platform-deployment --query clientId -o tsv)"
```

The local wrapper still uses your interactive user session. Do not set ARM_USE_OIDC=true locally. Before first remote initialization, wait for operator and deployment state-container roles to propagate. Attempt the normal network init below at most12 times with20-second gaps; stop and troubleshoot after four minutes. Never retry an apply blindly as an authorization-delay workaround. Group/Managed Identity token caching can take much longer; see acceptance troubleshooting.

Bootstrap uses **Contributor**, **User Access Administrator**, and **Resource Policy Contributor** at subscription scope for this demonstration. Review that privileged setup, narrow scope/role conditions before shared production, and protect GitHub environment/repository administration. Workload identities never receive those roles.

### Optional explicit bootstrap-state migration

Keeping encrypted-backed-up local bootstrap state is a supported path. To migrate later, first back it up and ensure Azure AD access to the existing container. Create the ignored generated backend file, then initialize with migration:

```sh
cat > platform/bootstrap/backend.generated.tf <<'HCL'
terraform {
  backend "azurerm" {}
}
HCL
terraform -chdir=platform/bootstrap init -migrate-state \
  -backend-config=resource_group_name=rg-platform-state \
  -backend-config="storage_account_name=stnorthstartf$PLATFORM_UNIQUE_SUFFIX" \
  -backend-config=container_name=tfstate \
  -backend-config=key=bootstrap/terraform.tfstate \
  -backend-config=use_azuread_auth=true \
  -backend-config=use_oidc=false > .runtime/bootstrap-migration.log 2>&1
```

Respond to migration confirmation privately. Confirm the remote blob and a remote `terraform state pull` into a protected file match expected resources, then encrypt that copy and remove temporary logs/files. Do not delete the local backup first. Retain the ignored backend configuration on that machine and recreate it before any bootstrap operation on a new machine; otherwise Terraform could start a different local state. Normal Terragrunt units always use different keys derived from their full repository-relative unit path. Do not migrate bootstrap into any normal unit key.

## 5. GitHub repository, OIDC and exact secrets

When you later choose to publish, create a GitHub repository named platform-infrastructure and push through your own process; generation does not publish it. Bootstrap's TF_VAR_github_repository must match that real owner/repository. Create the GitHub **environment platform**, restrict main, and configure required reviewers before enabling controlled apply. FIC trust is exactly `repo:OWNER/platform-infrastructure:environment:platform`, issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`. It does not trust arbitrary branches with a different subject. Environment protection must enforce reviewed main-only deployment; YAML main checks provide an additional boundary.

In Settings → Environments → platform → Secrets, add **AZURE_TENANT_ID**, **AZURE_SUBSCRIPTION_ID**, **AZURE_CLIENT_ID** and **AZURE_TEAM_GROUP_IDS**. Add Actions variables PLATFORM_UNIQUE_SUFFIX and DEMO_IMAGE (after image publication). [External configuration](external-configuration.md) gives the exact JSON and consumer table. No PAT or client secret is required. Do not put identity mappings in workflow inputs, tracked configuration, logs or artifacts. Replace fictional CODEOWNERS handles with actual reviewers before enforcing branch protection.

All infrastructure workflows are workflow_dispatch only and obtain Azure identifiers from those secrets. Native Terraform OIDC handles token exchange with no azure/login/CLI log output. Missing values fail preflight. The apply workflow needs confirm=apply, runs only main, waits for the platform environment's configured approval, and creates/applies one fresh saved plan in the same approved job. It never downloads a potentially stale plan artifact. The separate plan workflow reports pass/failure without exposing its plan; inspect a local protected plan for resource-level review. Workflows serialize state mutations using a shared concurrency group.

## 6. Build/publish the demo before resource initialization

Use [demo.md](demo.md). Either build locally with Docker27.5.1, or manually dispatch image.yml to build and publish the sample using GitHub's short-lived GITHUB_TOKEN. No Azure authentication is needed for image publication. Set the GHCR sample package visibility to **public**, then set `DEMO_IMAGE=ghcr.io/<lowercase-owner>/northstar-demo@sha256:<published-digest>` locally and in GitHub Actions variables. The digest must be real, not a SHA placeholder. This public sample contains no runtime configuration or secrets.

## 7. Dependency-ordered dev deployment

Run checks and privately review declarations first. Remain at the repository root. The wrapper injects runtime configuration, protects output and saves local plans in mode700 `.runtime/plans` with mode600 files. **Init → plan → private review → apply each unit in order**, stopping after any failure:

```sh
python3 scripts/infra.py init platform/networking/dev
python3 scripts/infra.py plan platform/networking/dev
```

Review this exact saved plan locally:

```sh
python3 scripts/infra.py review platform/networking/dev
```

Read `.runtime/plans/platform--networking--dev.review.txt` privately. The review command checks the saved plan's source/runtime fingerprints, uses the matching initialized unit/provider and never prints its content. It is unavailable in workflows. Repeat `review UNIT` for every unit after plan and before apply; review files are confidential and removed on plan/apply/destroy. Then:

```sh
python3 scripts/infra.py apply platform/networking/dev
python3 scripts/infra.py init projects/orders/environments/dev/resources
python3 scripts/infra.py plan projects/orders/environments/dev/resources
python3 scripts/infra.py apply projects/orders/environments/dev/resources
python3 scripts/infra.py init projects/catalog/environments/dev/resources
python3 scripts/infra.py plan projects/catalog/environments/dev/resources
python3 scripts/infra.py apply projects/catalog/environments/dev/resources
python3 scripts/infra.py init platform/governance/dev
python3 scripts/infra.py plan platform/governance/dev
python3 scripts/infra.py apply platform/governance/dev
python3 scripts/infra.py init projects/catalog/environments/dev/access
python3 scripts/infra.py plan projects/catalog/environments/dev/access
python3 scripts/infra.py apply projects/catalog/environments/dev/access
```

Apply prompts require typing apply locally. Source/runtime/plan fingerprints prevent applying a saved plan after configuration changes. Review every plan privately as above; no commands in this guide imply those reviews already occurred. Terraform's backend lease serializes same-state writes, but separate local operators must coordinate shared-network/project lifecycle changes.

**Stop before orders/dev/access.** From the private operator host, create test fixtures with its explicitly authorized interactive user and run before-grant acceptance. Then separately initialize/plan/apply `projects/orders/environments/dev/access` and run after-grant tests. See [acceptance.md](acceptance.md). This separation is essential; applying all units in one run destroys the denied-before-grant proof. There is no run-all deployment command.

For workflow execution, dispatch plan/apply once per exact unit path in the same dependency order. Workflow applies do not bypass prerequisite resource existence. GitHub-hosted runners need no private Blob/App ingress because workload management uses ARM; storage provider data-plane refresh is disabled. The state endpoint is public Azure AD only.

Prod is fully declared but **not required for the demonstration**. If deliberately deploying later, repeat network → orders/resources → catalog/resources → governance → catalog/access → orders/access using prod paths, appropriate review and cost approval. The supplied cross-project workload grant applies only in dev; no prod data grant is created. Dev/prod use separate VNet/DNS/states, with no default interconnection.

## 8. Private operator, expected results and manual checks

Provide an existing private host on snet-operators (dev10.40.2.0/24), with no public IP and approved private management (or Azure Run Command). This repository reserves the subnet but does not create a VM/VPN/Bastion or their credentials. A VPN client outside that source range additionally needs reviewed NSG/routing/DNS changes. On the host, use a local copy of this repository, Python3.12.8 and Azure CLI2.70.0, authenticate interactively, and transfer environment values privately. DNS must resolve both web app and Blob endpoints to dev VNet IPs. See acceptance for operator permissions, fixtures, bounded retries and cleanup.

Expected names are rg-catalog-dev, rg-orders-dev, vnet-dev in rg-platform-network-dev, private catalog/orders apps, private orders storage and exports/restricted containers. Tags include organization, owner, project, environment, cost_center and managed_by on taggable resources. Source APIs/containers/role assignments don't all support tags. Platform owns networking; project resource states own private endpoints; access states own assignments. Only exports should become readable by catalog's UAMI.

Offline checks/tests to run later, without Azure:

```sh
python3 scripts/check_config.py
python3 -m unittest discover -s tests -p 'test_*.py'
terraform fmt -check -recursive
```

For executable Terraform validation later, initialize and validate the exact Terragrunt unit using its configured runtime prerequisites (`terragrunt validate` from that unit, redirect output privately). This may read dependencies/backends and is not part of offline tests. Never confuse fmt/validate with actual Azure acceptance. None has run yet.

## 9. Troubleshooting and scoped cleanup

Missing/malformed external values fail before Terraform. Authentication errors: privately confirm selected tenant/subscription, group tenant, deployment client vs object ID, GitHub environment name, federated subject, main branch and id-token permission. State403: check operator/deployment Blob Data Contributor on the tfstate container and bounded propagation retries. Never enable shared keys or substitute SAS to bypass a failure. State locking: wait for the real operation; do not force-unlock until its owner confirms no active writer. Name collisions: inspect ownership, never import/delete someone else's resource. Image failures: public package visibility, linux/amd64 digest, port8080 and process health. Network failures: dedicated delegation, nonoverlapping CIDRs, endpoint policy Enabled, NSG source, private DNS VNet links and forwarding. A404 is a missing fixture, not an authorization success. Policy403: inspect scope/alias compliance and tags; don't exempt workloads just to force a pass.

RBAC assignments may take minutes; the authored read acceptance retries12 times with20-second gaps. Group/Managed Identity authorization caches can persist much longer (potentially hours). Stop after the bounded window, record the result as unresolved and investigate/retry later; do not increase privileges or call the test passed. A revoked grant may continue working with cached tokens; retain resources until revocation is proven after refresh.

B1 plans charge while present, even idle; Private Endpoints, LRS/versioned storage and transfers also cost money. Prod duplicates costs if deployed. An operator VM/VPN/Bastion supplied separately adds charges. Do not rely on trial credit as cost control. Use the portal cost view/budget controls manually and destroy dev promptly.

Clean fixtures/temporary operator assignments as acceptance describes. For complete dev teardown, keep declarations present, then run the following **locally**, reviewing each scope first:

```sh
python3 scripts/infra.py destroy projects/orders/environments/dev/access --approve
python3 scripts/infra.py destroy projects/catalog/environments/dev/access --approve
python3 scripts/infra.py destroy platform/governance/dev --approve
python3 scripts/infra.py destroy projects/catalog/environments/dev/resources --approve
python3 scripts/infra.py destroy projects/orders/environments/dev/resources --approve
```

The explicit --approve authorizes those scoped local destroys and suppresses raw logs. Wait for dependency/identity propagation as necessary. Project-only cleanup stops here and retains shared networking. Remove separately supplied operator hosts/NICs or other attachments before deliberately destroying `platform/networking/dev`; never do so while other projects still use it. Prod is untouched by dev cleanup. To remove only catalog, first revoke its destination grants (currently orders/dev/access destroy also removes orders human roles), destroy catalog/access/resources, update destination declarations to remove catalog grants, then remove catalog declaration and apply the shared network. Do not delete declarations first.

Keep bootstrap until every normal state is destroyed and encrypted backups retained. Empty/decommission remote state only after inventory/review, then deliberately remove bootstrap prevent_destroy safeguards in a reviewed change and plan its teardown from its actual retained/migrated state. This final irreversible step has no one-click script. Delete unused GHCR demo packages and separately created operator compute through their owners' processes. Remove private runtime files and revoke unused federated credentials/delegated roles when the repository is retired.
