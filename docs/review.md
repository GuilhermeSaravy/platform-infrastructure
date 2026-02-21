# Manual drift, governance and access review

This later improvement adds a dispatch-only review of already deployed infrastructure. It uses the same Terraform 1.10.5, Terragrunt 0.77.22, AzureRM 4.27.0 and Python 3.12.8 baseline. Every executable review, check and live exercise remains pending manual execution. No schedule, remediation or additional cloud integration is enabled.

Complete [startup](startup.md), configure the four Azure secrets and the existing `platform` GitHub environment, and deploy the environment you intend to review. Supply the same stable `PLATFORM_UNIQUE_SUFFIX` and immutable `DEMO_IMAGE` used to deploy it. A full environment review includes resources states and therefore requires `DEMO_IMAGE` even when you expect no image change. The deployment identity and remote state must already exist; this review cannot bootstrap them.

From a later local authenticated shell at the repository root:

```sh
python3 scripts/review.py --environment dev
```

To review one declared state while preserving the explicit environment boundary:

```sh
python3 scripts/review.py --environment dev --unit projects/orders/environments/dev/access
```

The script validates committed declarations and external configuration before invoking tools. It discovers project units automatically. Whole-environment order is networking, all project resources, governance, then all project access states, with deterministic project ordering. It initializes each unit and requests a speculative plan with normal refresh, state locking and `-detailed-exitcode`. An initialization failure skips that unit's plan while allowing other units to finish. It never applies, destroys, saves an executable plan or emits plan JSON.

| Exit | Meaning | Required response |
| --- | --- | --- |
| `0` | All selected units reported no proposed changes | Review the coverage limits below; this is not an effective-access certification |
| `2` | At least one unit reported proposed changes and no unit errored | Inspect a fresh local protected plan before approving any restoration |
| `1` | At least one unit failed, or preflight rejected configuration | Resolve the safe reported category and rerun; coverage is incomplete |

The summary reports counts and logical state paths only. It does not print identifiers, resource addresses, role principals, URLs, tokens or raw provider errors. Terraform/Terragrunt output is captured in mode-600 temporary files under ignored `.runtime` and deleted on ordinary completion, errors and exceptions. Each command has a 15-minute timeout. Debug variables and injected CLI flags are removed before execution. A hard process termination may interrupt cleanup; remove `.runtime` privately after inspecting the interruption. Keep Terraform caches and state private too.

For GitHub execution, manually dispatch `.github/workflows/review.yml` from reviewed `main`, choose `dev` or `prod`, and optionally select an exact unit. The job uses the protected `platform` environment, existing serialization group, the exact four named Azure secrets, repository variables and native Terraform OIDC. It installs pinned tools through the shared action. It does not invoke Azure CLI or Docker and uploads no artifacts. Exit `2` deliberately makes the job fail to flag changes; exit `1` flags an incomplete review. Neither status starts remediation. The final cleanup step removes `.runtime` even when a preceding step fails.

## What the review establishes

Configuration checks resolve supported capabilities, logical teams, central profiles, environment boundaries and destination-owned grants. AzureRM refresh plus planning can detect configuration differences for **tracked** resources, policy definitions/assignments and role assignments. Examples include a tracked role assignment deleted outside Terraform, a tracked policy changed, a required managed tag changed or an application setting changed. A new declared project or unapplied declaration also produces proposed changes; the script does not label every nonempty plan as an incident. An undeployed or partially deployed environment can report creations or failed dependencies and must not be treated as a clean audit.

This is not enumeration of all permissions or a compliance scan. It cannot establish the absence of unmanaged or inherited extra roles, permission granted through group membership, privileged administrators, conditions outside these states, Azure Policy's complete compliance evaluation, actual image trust or arbitrary application authorization. Provider-computed changes and Azure eventual consistency also require operator interpretation. Existing group lifecycle remains outside this repository. Use [manual acceptance](acceptance.md) to verify observed private DNS/network behavior and workload read-versus-write denial. Those live probes are deliberately absent from a GitHub-hosted runner with no private data-plane route.

## Optional controlled dev exercise

After a normal dev deployment and a clean baseline review, a future operator may change one tracked nonsecurity tag on `rg-catalog-dev`. Keep required ownership/cost tags intact so this exercise does not require bypassing policy. This command changes Azure and is for deliberate later manual execution only:

```sh
set +x
umask 077
mkdir -p .runtime
chmod 700 .runtime
az group update --name rg-catalog-dev --set tags.managed_by=manual-review-probe \
  --only-show-errors --output none >.runtime/manual-drift-probe.log 2>&1
python3 scripts/review.py --environment dev --unit projects/catalog/environments/dev/resources
```

Expected: review exits `2` and reports that this unit has changes. Inspect and restore through the existing controlled local flow, never through an automatic review apply:

```sh
python3 scripts/infra.py init projects/catalog/environments/dev/resources
python3 scripts/infra.py plan projects/catalog/environments/dev/resources
python3 scripts/infra.py review projects/catalog/environments/dev/resources
```

Open the protected review path returned by the last command in a local editor; confirm the expected tag restoration and inspect any additional changes privately. Do not paste that file into CI logs or upload it. After approving the concrete plan:

```sh
python3 scripts/infra.py apply projects/catalog/environments/dev/resources
python3 scripts/review.py --environment dev --unit projects/catalog/environments/dev/resources
```

Expected: the tag returns to `terraform` and the repeated selected-unit review exits `0`. If the first review is already nonzero, investigate that baseline before changing anything. Do not delete security policies or access assignments merely to exercise the script. The missing tracked-role/policy scenarios are authored as future manual review cases; their interpretation must account for propagation and the broader access limitations above.

Offline orchestration cases are authored for later execution and mock every external command:

```sh
python3 -m unittest discover -s tests -p 'test_review.py'
```

They cover discovery, environment selection, aggregate statuses, skipped plans after init errors, continued review, suppressed raw output, cleanup, rejected preflight and injected debug/CLI variables. They do not prove actual cloud drift detection. The detailed plan exit codes are documented in [Terraform's pinned 1.10.5 source](https://github.com/hashicorp/terraform/blob/v1.10.5/website/docs/cli/commands/plan.mdx#other-options). No commands in this document have been executed by the code-generation task.
