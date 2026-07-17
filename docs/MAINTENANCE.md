# Upstream synchronization and branch strategy

This repository is maintained so that upstream provenance remains visible and
custom provider work can absorb future streaming, OAuth, and provider changes
without rebuilding Git history.

## Branch and tag roles

- **`main` is a clean mirror of Microsoft upstream.** Do not commit custom code,
  merge feature branches, or squash downstream work onto `main`. A commit on
  `main` must be reachable from `upstream/main`.
- **Feature branches contain custom work.** Use a descriptive branch such as
  `feature/gpt-5-provider` and open PRs from it. Rebase it onto the mirrored
  `main` for a linear history, or cherry-pick selected upstream commits when a
  complete rebase is inappropriate.
- **Forensic branches preserve a movable investigation snapshot.** Name them
  `forensics/<reason>-YYYY-MM-DD`; never use them as PR bases.
- **Preservation tags are immutable evidence.** Use annotated tags named
  `archive/<reason>-YYYY-MM-DD` before rewriting or deleting a branch. Never
  move or reuse an archive tag; create a new dated tag instead.

In the commands below, `origin` is the custom fork and `upstream` is
`microsoft/amplifier-module-provider-openai-chatgpt`. Replace `<fork-url>` with
the writable fork URL.

## One-time remote setup

```bash
git remote add origin <fork-url>
git remote add upstream https://github.com/microsoft/amplifier-module-provider-openai-chatgpt.git
git remote -v
git fetch --prune origin
git fetch --prune --tags upstream
```

If a remote already exists, inspect it before changing it and use
`git remote set-url <name> <url>`. Do not guess which remote is authoritative.

## Refresh the mirror

Start with a clean worktree. The ancestry check prevents an unrelated history
from being installed as `main`.

```bash
git status --short
git fetch --prune --tags upstream
git switch main
git merge-base --is-ancestor main upstream/main
git merge --ff-only upstream/main
git push origin main
```

If the ancestry check or fast-forward fails, stop. Do **not** use
`--allow-unrelated-histories`, a merge commit, or a force push to make it pass.
Archive the unexpected history as described below, then determine which ref has
the Microsoft lineage. Repository administrators may reset the mirror only
after preservation and review:

```bash
git branch forensics/main-before-reset-YYYY-MM-DD main
git tag -a archive/main-before-reset-YYYY-MM-DD main -m "Preserve main before upstream reset"
git push origin forensics/main-before-reset-YYYY-MM-DD archive/main-before-reset-YYYY-MM-DD
git switch main
git reset --hard upstream/main
git push --force-with-lease origin main
```

`--force-with-lease` is intentionally required: it refuses to overwrite remote
work that was not fetched and reviewed.

## Update a feature branch

Preserve a rollback point, rebase, validate, and push with a lease:

```bash
git fetch --prune --tags upstream
git switch feature/gpt-5-provider
git status --short
git tag -a archive/gpt-5-provider-before-rebase-YYYY-MM-DD HEAD -m "Before upstream rebase"
git push origin archive/gpt-5-provider-before-rebase-YYYY-MM-DD
git rebase upstream/main
uv sync
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format --check .
git push --force-with-lease origin feature/gpt-5-provider
```

During a conflict, inspect `git status` and each conflict, preserve the intent
of both the upstream change and the provider customization, stage resolved
files, and continue:

```bash
git diff --name-only --diff-filter=U
git add <resolved-files>
git rebase --continue
```

Use `git rebase --abort` to return to the exact pre-rebase state. If a completed
rebase is wrong, recover from the archive tag with a new repair branch rather
than moving the tag:

```bash
git switch -c repair/gpt-5-provider archive/gpt-5-provider-before-rebase-YYYY-MM-DD
```

When only specific upstream changes are safe to adopt, start from the feature
branch, record the rollback tag as above, then use
`git cherry-pick -x <upstream-commit>`. The `-x` trailer records provenance.
Resolve with `git cherry-pick --continue`, or roll back with
`git cherry-pick --abort`.

## Validate and open the PR

Before opening a PR, verify that the feature branch descends from upstream and
that the PR contains only its custom delta:

```bash
git merge-base --is-ancestor upstream/main HEAD
git log --oneline --decorate upstream/main..HEAD
git diff --check upstream/main...HEAD
git diff --stat upstream/main...HEAD
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format --check .
```

Push the feature branch and open a PR **into `main`**. Include the upstream base
commit, validation results, conflicts resolved, and archive tag in the PR body.
Never open a PR between unrelated roots and never use an archive or forensic
branch as the PR head or base.

## Archive accidental or unrelated history

Preserve first; delete only after the remote branch and tag are visible and
reviewed:

```bash
git fetch --all --prune --tags
git branch forensics/unrelated-history-YYYY-MM-DD <accidental-ref>
git tag -a archive/unrelated-history-YYYY-MM-DD <accidental-ref> -m "Preserve unrelated history"
git push origin forensics/unrelated-history-YYYY-MM-DD archive/unrelated-history-YYYY-MM-DD
git ls-remote --heads --tags origin '*unrelated-history-YYYY-MM-DD*'
```

After review, a repository administrator can delete the accidental ordinary
branch with `git push origin --delete <accidental-branch>`. Retain the forensic
branch and archive tag according to the project's retention policy.

## Never edit Amplifier caches

Do not develop inside or edit generated files under `~/.amplifier/cache/` (or
another configured Amplifier cache). Cache contents are disposable installed
artifacts: direct edits are unreviewable and disappear on reinstall. Make every
change in this Git checkout, commit it on a feature branch, then reinstall the
provider through Amplifier's module/provider workflow. If behavior appears
stale, reinstall with `amplifier provider install openai-chatgpt --force`
instead of patching cached files.
