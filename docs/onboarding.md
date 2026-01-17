# Offline project onboarding

The January 2026 improvement adds a local generator to the existing configuration-only onboarding contract. It copies the populated reusable `templates/project` example, allocates a free network slot, and checks the candidate with every existing project before installing it. The original catalog and orders declarations, shared modules, policies and organization files stay unchanged. No central project list exists.

All commands and tests here await manual execution. Generation itself needs only the audited Python 3.12.8 standard library on macOS or Linux; it does not need an Azure tenant, subscription, group IDs, credentials, GitHub account, Terraform initialization or cloud authentication. It creates configuration, not resources.

From the repository root, the complete example is:

```sh
python3 scripts/onboard.py inventory --owner-team commerce-backend --environments dev prod
```

`inventory` is already the reusable template's fictional project name. With the supplied catalog slot0 and orders slot1, the generator chooses slot2. Defaults preserve Northstar Commerce's commerce-platform cost center, existing team references, one B1 api runtime on port8080, and empty workload grants. It creates only `projects/inventory/project.yaml` and its selected environment resources/access leaves; those leaves derive the project name from their directory. Actual Azure identifiers remain external runtime configuration.

To generate only dev or reserve another unused slot explicitly:

```sh
python3 scripts/onboard.py inventory --environments dev --network-slot 7
```

Choose one invocation for a new project; a second invocation with the same name fails without updating or replacing it, including when the destination is an empty directory. `--cost-center` may override the declared default using the existing lowercase naming convention. Names require 3–10 lowercase alphanumeric characters, starting with a letter. Each project supports at most one application-runtime and one object-storage capability. The template starts with only the api runtime; add reviewed storage needs explicitly after generation rather than implicitly granting data access.

`--owner-team` must reference an existing logical team. Access follows the template's declared order: preserve platform-operator first, remap the template owner's environment-specific developer/reader entries to the selected owner, then retain other team entries where they do not duplicate an existing team/environment. Profile environment restrictions apply throughout; project-developer is dev-only. Reassigning ownership does not create Entra groups, change group membership, create workload grants or transfer real resources. Review the resulting access declarations with platform engineering and the owner before any plan.

The generator serializes cooperating local invocations with a mode600 POSIX advisory lock at `.runtime/onboarding.lock`, inside a mode700 directory. It stages only declaration and leaf files in a private temporary candidate checkout, validates the complete logical configuration, reserves the new destination exclusively, then renames the complete staged directory into place. Existing empty destinations also fail; no shared file is rewritten. Temporary candidates are removed on normal success or failure. A process killed between exclusive reservation and rename can leave an empty project directory: confirm no generator is running before removing that empty directory and retrying. Do not edit onboarding inputs or the destination concurrently outside the generator; advisory locks cannot coordinate unrelated editors. A filesystem or machine failure still requires normal local recovery.

Review `projects/inventory/project.yaml` and the generated leaves, then run the authored checks manually:

```sh
python3 scripts/check_config.py
python3 -m unittest discover -s tests -p 'test_onboarding.py'
```

The authored cases cover a complete credential-free example, automatic and explicit slots, concurrent allocation, dev/prod access restrictions, owner remapping, existing-project and empty-directory protection, invalid owners/names, collisions and invalid templates. None ran during generation; passing these offline tests later does not prove Azure behavior.

Follow [startup.md](startup.md) for external prerequisites and protected per-unit init → plan → review → apply. Review and apply the shared environment network before a new project's resources so its dedicated delegated subnet exists. Apply the new resources before access, and update governance to include its resource group once created. A project with no workload grants needs no source-project dependency. Any later destination-owned cross-project grant requires its destination owner's review, source identity existence, separate network reachability and a separate access-state apply.

Before removing a project, revoke destination grants and destroy its access/resources while its declaration still exists. Only then remove the declaration and apply shared networking/governance changes as the cleanup runbook specifies. Never reuse its network slot until old integrations, endpoints and DNS are gone. This improvement does not automate deployment, drift remediation or multi-cloud implementation.
