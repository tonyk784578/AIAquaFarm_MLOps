<!--
Fill in each section. Leave a heading in place even if you write "n/a" — it
keeps reviewers oriented. See CONTRIBUTING.md for the full checklist.
-->

## Summary

<!-- One paragraph: what changes and why. Link the driving issue / ticket. -->

## Type of change

- [ ] Bug fix (no behaviour change beyond the fix)
- [ ] New feature (user-visible behaviour)
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Infrastructure / CI / build

## Test plan

<!--
Concrete commands the reviewer can run, in the order you ran them. Paste the
relevant excerpt of output if helpful.

  make test
  cd frontend && npm test
  curl ... | jq ...
-->

- [ ] Unit tests added or updated
- [ ] Manually verified locally (`make up` + flow exercised)
- [ ] CI green

## Risk / rollout

<!--
Will this require a migration, secret rotation, env-var bump, or coordinated
deploy? Mention here so the deployer knows the order of operations.
-->

- [ ] Requires DB migration (`make migrate`)
- [ ] Requires new env var or secret
- [ ] Requires frontend rebuild (`docker compose build frontend`)
- [ ] Changes a public HTTP contract — frontend types regenerated (`make codegen`)

## Screenshots / output

<!-- Optional. UI changes → before/after screenshots. CLI/log changes → paste. -->

## Checklist

- [ ] Followed branching + commit conventions (CONTRIBUTING.md)
- [ ] No secrets / keys committed (gitleaks ran clean)
- [ ] Logs are still informative when this change fails at runtime
- [ ] Docs updated if behaviour changed (`CLAUDE.md`, `docs/`, runbook)
