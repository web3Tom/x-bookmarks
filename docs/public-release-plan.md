# Public Release Plan

## Priorities

### P0: Release Blockers

- Review token-storage security before or soon after public release.
- Confirm the current docs remain aligned with implementation.

### P1: Public Usability

- Keep the README focused on prerequisites, setup, output expectations, and migration.
- Add a short security note covering `.env`, OAuth tokens, and Anthropic credentials.
- Add a contribution guide if outside contributions are welcome.

### P2: Presentation And Maintenance

- Create GitHub issues from the roadmap and track work publicly.
- Review `docs/architecture.excalidraw` for accuracy or mark it as a draft.
- Add examples or screenshots once the release surface is stable.

## File And Area Recommendations

### Root Files

- [`README.md`](x-bookmarks/README.md): keep as the primary onboarding path.
- [`.gitignore`](x-bookmarks/.gitignore): keep strict around local state and generated artifacts.
- [`.env.example`](x-bookmarks/.env.example): keep minimal and safe.
- [`LICENSE`](x-bookmarks/LICENSE): keep visible before public push.

### Docs

- [`docs/public-release-audit.md`](x-bookmarks/docs/public-release-audit.md): use as the publication review record.
- [`docs/public-release-plan.md`](x-bookmarks/docs/public-release-plan.md): use as the cleanup checklist.
- [`docs/github-issues.md`](x-bookmarks/docs/github-issues.md): use to seed the repo issue tracker.
- [`docs/overview.md`](x-bookmarks/docs/overview.md): keep aligned with current implementation.

### Code

- [`src/config.py`](x-bookmarks/src/config.py:43): keep the default output root portable.
- [`src/auth_helper.py`](x-bookmarks/src/auth_helper.py:100): document plaintext token persistence clearly.
- [`src/categorizer.py`](x-bookmarks/src/categorizer.py:10): ensure public docs match the dynamic taxonomy behavior.

## Step-By-Step Workflow

1. Confirm ignore coverage and tracked-file hygiene.
2. Keep the README, overview, and release docs aligned with actual behavior.
3. Maintain the license and contribution docs.
4. Convert roadmap work into GitHub issues with scoped acceptance criteria.
5. Run tests and confirm the repo is clean.
6. Review `git diff` for secrets, local paths, and accidental machine-specific content.
7. Push to a new public GitHub repository.

## Final Pre-Push Checklist

- [ ] No secrets, tokens, or local-only files are tracked.
- [ ] `.gitignore` covers coverage, caches, logs, and local agent state.
- [ ] `README.md` explains prerequisites and quick start clearly.
- [ ] License file is present.
- [ ] Stale docs are updated or clearly labeled.
- [ ] Roadmap issues are created or ready to create from [`docs/github-issues.md`](x-bookmarks/docs/github-issues.md).
- [ ] Test suite passes locally.
- [ ] `git status` is clean except for intentional release changes.

## GitHub Push Workflow

Repository URL:

- `https://github.com/web3Tom/x-bookmarks`

1. Create the target GitHub repository.
2. Set the remote:

```bash
git remote add origin <your-github-repo-url>
```

3. Review the staged release diff:

```bash
git status
git diff --staged
```

4. Commit the cleanup:

```bash
git add .
git commit -m "Prepare x-bookmarks for public release"
```

5. Push the initial public branch:

```bash
git push -u origin main
```

## GitHub Issue Workflow

Push issue-planning changes like any other doc update:

```bash
git add docs/roadmap.md docs/github-issues.md
git commit -m "Update roadmap and issue planning"
git push origin main
```

If working from GitHub Issues back into docs:

1. Review open and closed issues in the GitHub UI.
2. Reconcile any major scope changes into `docs/roadmap.md`.
3. Update `docs/github-issues.md` if new roadmap items should be seeded later.
4. Commit and push the doc updates.

## Assumptions

- `docs/roadmap.md` is the intended source for issue extraction.
- The project is being published as a developer tool rather than as an end-user consumer app.
- Keeping the current output-directory default is a product decision, not an implementation accident, unless changed later.
