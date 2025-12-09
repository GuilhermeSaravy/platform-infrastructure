# Scoped Azure governance

This environment's state owns custom policy definitions at the provider subscription and deny assignments at existing `rg-platform-network-<environment>` and discovered `rg-<project>-<environment>` groups. The corresponding network and project states own those groups. Governance never owns their lifecycle.

Apply network and project resources before the first governance apply. The initial resources are authored with the required security settings; policy is an additional enforcement layer established afterward. This design intentionally leaves an initial enforcement gap. Run the acceptance procedures after policy propagation. Later onboarding requires applying the new project first, then governance again to discover its group. Existing governed groups remain enforced during onboarding.

Requirements cover approved resource locations, nonempty organization/owner/project/environment/cost-center tags, private HTTPS App Service sites, and Storage accounts with public networking, anonymous blobs and shared keys disabled. `Indexed` tag mode skips resource types without tag/location support. Global resources are exempt from regional restrictions. Resource group assignments do not prevent the creation of unrelated resource groups or enforce controls outside these scopes.

The bootstrap state resource group is excluded by scope. Its HTTPS, Azure AD authenticated state endpoint remains public so GitHub-hosted runners can reach it. This is a documented availability tradeoff, not an exemption for project storage. There is no subscription-wide assignment that could unexpectedly affect unrelated resources.

Policies deny future noncompliant changes; they do not automatically remediate existing resources. No policy identity is required because the policies have no remediation tasks. Role assignments for workloads and teams remain in their separate access states.

The JSON documents in `organization/policies/` are the policy source of truth. They are custom definition documents with `mode`, `parameters`, and `policy_rule`; the module adds metadata and environment-scoped definition names. A destination owner and platform reviewer must approve changes that widen public access or access intent.

No executable policy or infrastructure verification has been performed. Alias support, propagation and rejection behavior await manual Azure verification.
