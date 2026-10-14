# RELEASE_TOKEN Rotation Procedure

## Purpose
`RELEASE_TOKEN` is a fine-grained GitHub PAT used by `.github/workflows/release.yml` for the
release tag push, the bump PR `gh pr create`/`gh pr merge` step, and package publish dispatch.
`.github/workflows/bench.yml` uses it to update the `benchmarks/master-baseline` branch and to
create or edit the benchmark baseline PR.

Events created with a PAT trigger matching workflows automatically, including required CI on the
bump and baseline PRs. With `GITHUB_TOKEN`, pushes do not trigger `push` workflows, and PRs it
creates or updates start `pull_request` runs only after a user with write access approves them.

## Historical Token Record (do not commit value here)
Recorded when the token was created. The recorded expiry has passed, and this document does not
reflect an inspection of the live secret; check the PAT settings for the current owner, expiry, and
permissions.

- Owner: ardzz (personal account)
- Created: 2026-05-27 (approx)
- Expires: 2026-08-25 (90 days from creation)
- Repository access: Only ardzz/RouteMQ
- Permissions:
  - Contents: Read and write
  - Pull requests: Read and write
  - Workflows: Read and write

## Rotation Schedule
- **Calendar reminder:** 7 days before expiration
- **Hard deadline:** Day of expiration
- **GitHub auto-emails the owner** ~7 days before; do not ignore

## Rotation Steps
1. Open https://github.com/settings/personal-access-tokens/new
2. Generate new fine-grained PAT with identical scopes (see above)
3. Open https://github.com/ardzz/RouteMQ/settings/secrets/actions
4. Click `RELEASE_TOKEN` → Update → paste new value → Update secret
5. Go back to https://github.com/settings/personal-access-tokens
6. Find the previous token → Revoke
7. Verify by triggering a small `fix:` commit and confirming the bump PR has CI checks

## Security Reminders
- **NEVER paste this token into chat, screenshots, commits, or external tools.**
- GitGuardian (CI check) will catch accidental commit-time exposure.
- If you suspect leakage: revoke immediately, generate new, update secret.
- This token grants write access to RouteMQ only (fine-grained), but a compromise 
  could push commits, create PRs, and modify workflows. Treat as production credential.

## Why PAT and Not GitHub App
PAT was chosen for setup simplicity (Sprint 18). A GitHub App would be more secure 
(short-lived tokens, no user dependency). Migration to App is a future micro-sprint 
(`SPRINT-18b` candidate) when warranted.
