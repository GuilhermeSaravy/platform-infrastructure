# Authored tests: execution pending

No test or check in this directory was run during generation. Offline tests use the Python standard library and mocks; live acceptance requires an authenticated human operator, private DNS/connectivity, deployed dev resources and explicit test data. Start with docs/startup.md and docs/acceptance.md.

Offline: `python3 -m unittest discover -s tests -p 'test_*.py'` from the repository root. Configuration tests cover logical references, supported capability/name/slot rules, template onboarding, missing/malformed/placeholder external values and protected error output. Demo tests cover fixed probe routes, bearer identity behavior and error redaction. These are authored expectations, not passed results.

Live: `python3 tests/acceptance.py before ...` then separately apply the orders/dev/access state and run `after`. The script checks private DNS/HTTPS, denial-before, allowed read, denied write and denied restricted-container access. Policy denial, inventory/tags/ownership, logical group assignments, fixture identity, bounded retries and cleanup have detailed manual procedures. Never treat a network error or missing fixture404 as an RBAC proof.
