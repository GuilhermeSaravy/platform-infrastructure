# Manual acceptance

All procedures here are authored for later execution. No check, test, application, authentication, plan, build, workflow or deployment was executed during generation. Run these steps after [startup](startup.md), using its exact pinned tools and external values. Executable configuration tests, Terraform checks and workflow plans remain pending too.

Use dev only. The private operator host must already have HTTPS access to the dev VNet, routing to its Private Endpoints and conditional DNS forwarding for `privatelink.azurewebsites.net` and `privatelink.blob.core.windows.net`. Use an existing host in `snet-operators` (`10.40.2.0/24`). A VPN alone is insufficient: the Private Endpoint NSG accepts the operator subnet and application integration subnets only. A different VPN source range requires a separate reviewed platform networking change and working DNS. This repository does not provision a VM, VPN or a public ingress exception. An ordinary Internet-connected laptop or GitHub-hosted runner cannot run these private data-plane tests.

If you have no private operator host later, use the Azure portal to create a temporary Ubuntu 24.04 Linux VM in `vnet-dev` / `snet-operators`, in `westeurope`, with no public IP, no public inbound rule, appropriate organization tags and a cost-conscious size available in your subscription. Use Azure VM Run Command or your existing approved private management route to access it; interactive device-code Azure CLI login can be completed in a browser on your workstation. Install the pinned Python and Azure CLI tools from startup, copy this repository's reviewed source to the host, supply its local external environment privately, and run commands from its checkout root. Azure-provided DNS on that subnet can resolve the VNet-linked private zones. Any custom DNS must forward those zones correctly. A VM is an external prerequisite, incurs compute/disk costs and must be deleted with its disks when finished; do not place that external VM in a project resource group you plan to destroy. Do not open App Service or Blob public access to avoid this prerequisite.

Run from the repository root. Use a protected shell with tracing disabled; do not upload `.runtime`, state, plans, environment dumps or identity mappings as artifacts. Local operator login is interactive and independent of GitHub's deployment UAMI. The application itself always executes Blob requests as catalog/dev's UAMI.

## Inventory, names, tags and boundaries

After startup deploys the dev foundation and both dev project **resources** states, inspect the source declarations and Azure inventory. Fill `PLATFORM_UNIQUE_SUFFIX` from your chosen startup value; it must match the deployed immutable names.

```sh
set +x
export CATALOG_URL="https://app-ns-catalog-dev-${PLATFORM_UNIQUE_SUFFIX}.azurewebsites.net"
export ORDERS_STORAGE_ACCOUNT="stnsordersdev${PLATFORM_UNIQUE_SUFFIX}"
az group show --name rg-catalog-dev --query '{name:name,tags:tags}' --output json
az group show --name rg-orders-dev --query '{name:name,tags:tags}' --output json
az network vnet show --resource-group rg-platform-network-dev --name vnet-dev \
  --query '{name:name,addressSpace:addressSpace.addressPrefixes,subnets:subnets[].{name:name,prefix:addressPrefix,prefixes:addressPrefixes,delegations:delegations[].serviceName}}' --output json
az network vnet peering list --resource-group rg-platform-network-dev --vnet-name vnet-dev \
  --query '[].name' --output json
az storage account show --name "$ORDERS_STORAGE_ACCOUNT" --resource-group rg-orders-dev \
  --query '{publicNetworkAccess:publicNetworkAccess,allowSharedKeyAccess:allowSharedKeyAccess,httpsOnly:enableHttpsTrafficOnly}' --output json
az webapp show --resource-group rg-catalog-dev --name "app-ns-catalog-dev-${PLATFORM_UNIQUE_SUFFIX}" \
  --query '{publicNetworkAccess:publicNetworkAccess,httpsOnly:httpsOnly,identityType:identity.type}' --output json
```

Expected: `rg-catalog-dev` and `rg-orders-dev` are separate; required ownership, project, environment and cost tags match their declarations; `vnet-dev` lives in `rg-platform-network-dev`; no default dev/prod peering exists. Check the platform network state source owns VNet/subnets/NSGs/routes/Private DNS, while project state owns only its Private Endpoints and workload. Removing a project must retain the network state. Application egress delegation is `Microsoft.Web/serverFarms`; ingress Private Endpoints use a separate nondelegated subnet. Public network access is disabled and shared-key authentication is false.

Review `organization/access-profiles.yaml`, each project's `access` and `workload_grants`, and the injected logical map. Compare role assignments with intended scope using the Azure portal or protected CLI output locally. `commerce-backend` reuses the same existing Entra group in dev and prod; its dev management permissions do not imply Blob data access. `commerce-frontend` receives only explicitly declared access. Do not print or commit the external group map. Run the authored declaration/external-configuration tests from startup later; they must reject unknown teams/profiles/capabilities, malformed IDs, missing values and placeholder IDs. Review [architecture](architecture.md) for the exact state ownership contracts.

## Create fixtures as the operator

The fixtures must exist before the denied-before-grant test; otherwise a 404 is ambiguous. The logged-in human operator needs a temporary `Storage Blob Data Contributor` assignment on **orders/dev only**. Capture sensitive IDs and assignment IDs in shell variables; do not echo them or put them in project configuration. Your existing administrator must be allowed to assign this role. Existing broad operator rights can make this temporary assignment redundant; record the executing identity in your private execution notes.

```sh
umask 077
mkdir -p .runtime
printf '%s\n' 'Northstar acceptance fixture' > .runtime/acceptance.txt
ORDERS_STORAGE_ID=$(az storage account show --name "$ORDERS_STORAGE_ACCOUNT" \
  --resource-group rg-orders-dev --query id --output tsv 2>.runtime/fixture-storage.log)
OPERATOR_OBJECT_ID=$(az ad signed-in-user show --query id --output tsv 2>.runtime/fixture-operator.log)
FIXTURE_ROLE_ID=$(az role assignment create --assignee-object-id "$OPERATOR_OBJECT_ID" \
  --assignee-principal-type User --role 'Storage Blob Data Contributor' \
  --scope "$ORDERS_STORAGE_ID" --query id --output tsv 2>.runtime/fixture-role.log)
```

Stop immediately if a command fails or leaves an empty variable; inspect its protected `.runtime/fixture-*.log` file privately, then delete it. Do not proceed to uploads with an unrecorded assignment. Use Entra authentication for both uploads. The loop suppresses Azure CLI error text, which may contain URLs or identifiers. It retries at most 12 times, sleeping 20 seconds between attempts; a final nonzero result fails setup. Repeat only after investigating DNS, firewall and RBAC if the bound expires. Do not switch to keys or SAS.

```sh
upload_fixture() {
  fixture_attempt=1
  while [ "$fixture_attempt" -le 12 ]; do
    if az storage blob upload --auth-mode login --account-name "$ORDERS_STORAGE_ACCOUNT" \
      --container-name "$1" --name acceptance.txt --file .runtime/acceptance.txt \
      --overwrite true --only-show-errors --output none >/dev/null 2>&1; then
      return 0
    fi
    if [ "$fixture_attempt" -eq 12 ]; then
      printf '%s\n' 'Fixture setup failed; investigate private connectivity and operator RBAC.' >&2
      return 1
    fi
    sleep 20
    fixture_attempt=$((fixture_attempt + 1))
  done
}
upload_fixture exports && upload_fixture restricted
```

Stop if either upload fails. Successful writes establish that both fixture paths exist through the private endpoint; catalog's later denial must use a separate workload identity. The `restricted` container is created by orders resources and deliberately has no catalog grant.

## Denied before the destination grant

Deploy catalog/dev and orders/dev resources, with networking already present, but **do not apply orders/dev access yet**. Human/group assignments and workload grants share that access state, so omit it as a complete unit. There is no `-target` workaround. Ensure no earlier grant or inherited broad Blob data role applies to catalog's UAMI. A previously deployed environment must first remove its orders/dev access state as described below and wait for revocation.

```sh
python3 tests/acceptance.py before --catalog-url "$CATALOG_URL" \
  --storage-account "$ORDERS_STORAGE_ACCOUNT"
```

Expected: both application and Blob DNS resolve exclusively inside the configured dev network (default `10.40.0.0/16`), HTTPS health succeeds, and catalog's read probe obtains Blob 403. This proves observed denial only when fixtures and network preconditions succeeded. A 404, outer HTTP 503, timeout, public DNS result or redirect is failure. The read identity is the app UAMI, independent of the operator's fixture-upload role.

## Apply the read-only destination grant

The orders owner must review the source project/environment/identity, target capability/container, read-only profile and network reachability before this apply. This authorization does not grant access to arbitrary orders HTTP endpoints. Run the complete access unit:

```sh
python3 scripts/infra.py init projects/orders/environments/dev/access
python3 scripts/infra.py plan projects/orders/environments/dev/access
python3 scripts/infra.py review projects/orders/environments/dev/access
python3 scripts/infra.py apply projects/orders/environments/dev/access
python3 tests/acceptance.py after --catalog-url "$CATALOG_URL" \
  --storage-account "$ORDERS_STORAGE_ACCOUNT"
```

These commands stay at the repository root and resolve local Azure CLI authentication through the wrapper. Its saved plan remains protected under `.runtime/plans`; it may contain identifiers and must not be uploaded. The local apply asks you to approve the saved plan. Expected downstream results are read 200, attempted write 403, restricted-container read 403. Only the newly allowed read retries 403, at most 12 attempts with 20-second gaps (11 sleeps plus request latency); writes and restricted reads must deny immediately. The script never retries or accepts 404 as authorization success. A failure after the retry bound requires investigation; it is not waived as eventual consistency. Azure Managed Identity caches can outlast this short demonstration window, so record the delay, stop and retry the whole acceptance later after inspection.

The source UAMI principal ID resolves from the named catalog identity, the destination scope is orders' `exports` container ARM resource ID and the role is `Storage Blob Data Reader`. No source state or Blob content is returned to the operator.

To repeat the denial sequence in an existing dev environment, review and destroy only the destination access unit; this revokes its team assignments too and leaves resources intact:

```sh
python3 scripts/infra.py destroy projects/orders/environments/dev/access --approve
```

Then run the before test. A residual 200 means revocation is not established; stop, inspect inherited assignments and cached credentials, and retry later. After proof of denial, reapply orders/dev access and repeat the after test. Do not destroy shared networking for this exercise.

## Policy denial

After governance assignment propagation, try a temporary storage account in prohibited `northeurope` inside **existing `rg-orders-dev`**. Governance is scoped to platform and project RGs, so a new unrelated RG would not exercise this policy. Use a globally unique lower-case name derived from your selected suffix. This is a later manual negative test, not Terraform state ownership. Capture CLI output in an ignored, protected temporary file because service errors can contain subscription identifiers.

```sh
POLICY_TEST_STORAGE="stnspolicy${PLATFORM_UNIQUE_SUFFIX}"
POLICY_TEST_CREATED=false
if az storage account create --name "$POLICY_TEST_STORAGE" --resource-group rg-orders-dev \
  --location northeurope --sku Standard_LRS --kind StorageV2 \
  --allow-shared-key-access false --allow-blob-public-access false --public-network-access Disabled \
  --min-tls-version TLS1_2 --https-only true \
  --tags organization=northstar owner=commerce-backend project=orders environment=dev cost_center=commerce-platform \
  --only-show-errors --output none >.runtime/policy-probe.log 2>&1; then
  POLICY_TEST_CREATED=true
  printf '%s\n' 'FAIL: prohibited resource was allowed; clean up immediately.'
elif grep -q 'RequestDisallowedByPolicy' .runtime/policy-probe.log && \
  grep -Eq 'northstar-dev-allowed-locations|northstar-allowed-locations' .runtime/policy-probe.log; then
  printf '%s\n' 'PASS: allowed-region policy rejected the prohibited resource.'
else
  printf '%s\n' 'FAIL: denial did not establish the expected region-policy rejection.'
fi
```

Expected: the storage create exits nonzero with `RequestDisallowedByPolicy` naming the allowed-region policy. Inspect the protected service error locally if necessary; do not paste it into CI logs or commit it. A syntax, name collision, subscription, permission or quota error does **not** prove policy rejection. If the resource is unexpectedly allowed, mark acceptance failed, inspect policy scope/exemptions/propagation, and delete only that temporary account immediately. If it was denied, there is no account to delete. Never delete `rg-orders-dev` for this negative test:

```sh
if [ "$POLICY_TEST_CREATED" = true ]; then
  if az storage account delete --name "$POLICY_TEST_STORAGE" --resource-group rg-orders-dev \
    --yes --only-show-errors --output none >.runtime/policy-cleanup.log 2>&1; then
    rm -f .runtime/policy-probe.log .runtime/policy-cleanup.log
    unset POLICY_TEST_STORAGE POLICY_TEST_CREATED
  else
    printf '%s\n' 'Cleanup failed; retain the private diagnostics and remove only the temporary policy-test account.' >&2
  fi
else
  rm -f .runtime/policy-probe.log
  unset POLICY_TEST_STORAGE POLICY_TEST_CREATED
fi
```

## Fixture cleanup and results

Retain the temporary operator role until cleanup completes. Use its Entra identity through the private network to remove both fixtures. An unexpectedly successful negative write is a security failure; remove that blob too after recording the failure without its content. A 404 for an absent negative-write blob can be ignored only during cleanup.

```sh
az storage blob delete --auth-mode login --account-name "$ORDERS_STORAGE_ACCOUNT" \
  --container-name exports --name acceptance.txt --only-show-errors --output none >.runtime/fixture-cleanup.log 2>&1
az storage blob delete --auth-mode login --account-name "$ORDERS_STORAGE_ACCOUNT" \
  --container-name restricted --name acceptance.txt --only-show-errors --output none >>.runtime/fixture-cleanup.log 2>&1
az storage blob delete --auth-mode login --account-name "$ORDERS_STORAGE_ACCOUNT" \
  --container-name exports --name should-not-write.txt --only-show-errors --output none >>.runtime/fixture-cleanup.log 2>&1
if az role assignment delete --ids "$FIXTURE_ROLE_ID" --output none >>.runtime/fixture-cleanup.log 2>&1; then
  unset FIXTURE_ROLE_ID OPERATOR_OBJECT_ID ORDERS_STORAGE_ID
else
  printf '%s\n' 'Temporary role cleanup failed; retain the protected assignment ID and investigate.' >&2
fi
rm -f .runtime/acceptance.txt .runtime/fixture-storage.log .runtime/fixture-operator.log .runtime/fixture-role.log
```

Inspect cleanup return statuses and `.runtime/fixture-cleanup.log` privately, then remove that file after resolving failures. Delete only the temporary assignment created in this procedure; do not remove an existing operator role by role name. Remove the temporary role even after a test fails, once any created blobs are cleaned up. Record outcomes, tool versions, commit SHA, timestamps and safe status codes in private execution notes, without tokens, actual identity mappings, state or downstream content. Use startup's scoped destruction order for cost cleanup; removing one project retains shared networking. No result in this document is a claim that acceptance has run or passed.
