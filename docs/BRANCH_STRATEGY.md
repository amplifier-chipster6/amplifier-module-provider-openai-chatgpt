# Upstream synchronization and downstream branch strategy

## Invariants and topology

This repository separates an exact Microsoft mirror from custom development:

```text
microsoft/main -> origin/main -> origin/downstream -> feature or release branch
                                      ^                       |
                                      +-------- pull request--+
```

- `main` is the clean mirror of `microsoft/main`. It accepts **only** verified,
  fast-forward upstream commits; never target a custom feature, fix, or release
  pull request at `main`.
- `downstream` is the integration and release base for all custom work. Target
  every custom pull request at `downstream`.
- Feature and release branches start from `downstream`. The current recovery
  branch is `release/gpt-5.6-provider-recovery` and its PR base is `downstream`.
- Forensic branches and immutable `archive/*` tags preserve evidence before a
  rewrite. They are never development branches or pull-request bases.
- Work only in a deliberate repository checkout. Never edit or develop inside
  Amplifier cache directories (for example `~/.cache/amplifier`); cache content
  is disposable and cannot provide trustworthy Git provenance.

The verified recovery base is
`265f4aeb3dfd69515740a847cfc7aba8dca85dfa`. Substitute a newer SHA below only
when it has been fetched from Microsoft and independently reviewed.


## Current recovery inventory

The only active recovery candidate is PR #8 from
`release/gpt-5.6-provider-recovery` into `downstream`. PRs #1 through #7 are
historical inputs or superseded experiments; they remain visible for review and
incident evidence, but they must not be merged or used to assemble a release.

The following refs have special non-release roles:

- `archive/original-unrelated-main` preserves the accidental unrelated GitHub
  history. It has no common ancestor with the Microsoft lineage and is never a
  development or pull-request base.
- `feat/chatgpt-5-6-routing-implemented` and the `pre-clean-reinstall` tag
  preserve the original in-place GPT-5.6 incident state. They are forensic
  evidence, not release candidates.
- `fix/oauth-device-code-polling` is an empty branch at the verified base and
  contains no OAuth repair. The historical repair source was
  `codex/fix-oauth-device-code-polling-behavior`; its required behavior is
  consolidated into PR #8.
- `feat/chatgpt-5-6-routing-clean` and the `codex/linear-mention-*` branches are
  superseded parallel work. Preserve them until the recovery is accepted, but
  do not retarget, merge, or continue them.

Do not delete these refs as part of the recovery. Any later cleanup requires a
separate preservation review after PR #8 has passed its release gates.

## One-time remote setup and topology check

Run these commands from the repository root:

```bash
git remote add origin https://github.com/chipster6/amplifier-module-provider-openai-chatgpt.git
git remote add microsoft https://github.com/microsoft/amplifier-module-provider-openai-chatgpt.git
git remote -v
git fetch --prune origin
git fetch --prune microsoft main

test "$(git rev-parse origin/main)" = "$(git rev-parse microsoft/main)"
test "$(git merge-base origin/main origin/downstream)" = "$(git rev-parse origin/main)"
```

If a remote already exists, inspect it and use `git remote set-url` only after
confirming its intended owner. A failed check is a stop condition: preserve the
current refs and investigate rather than resetting or force-pushing.

## Advance the clean mirror

First preserve the old mirror tip, verify that the update is a fast-forward,
and then update `main` without creating a merge commit:

```bash
git fetch --prune microsoft main
git fetch --prune origin main downstream
OLD_MAIN=$(git rev-parse origin/main)
NEW_UPSTREAM=$(git rev-parse microsoft/main)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
git tag -a "archive/main-$stamp" "$OLD_MAIN" -m "main before Microsoft sync to $NEW_UPSTREAM"
git push origin "archive/main-$stamp"

git merge-base --is-ancestor "$OLD_MAIN" "$NEW_UPSTREAM"
git switch main
git reset --hard "$NEW_UPSTREAM"
test "$(git rev-parse HEAD)" = "$NEW_UPSTREAM"
git push --ff-only origin main
```

Never use a normal merge, cherry-pick, or custom commit on `main`. If Microsoft
rewrites history, stop and review it as an exceptional migration; do not use the
routine above to hide the divergence.

## Workflow A: full rebase onto verified upstream

Use this when all downstream history should move to the new verified upstream
commit. Preserve every rewritten tip first:

```bash
git fetch --prune origin downstream
git fetch --prune microsoft main
UPSTREAM_SHA=$(git rev-parse microsoft/main)
stamp=$(date -u +%Y%m%dT%H%M%SZ)

git branch "forensic/downstream-before-$stamp" origin/downstream
git tag -a "archive/downstream-before-$stamp" origin/downstream \
  -m "downstream before rebase onto $UPSTREAM_SHA"
git push origin "forensic/downstream-before-$stamp" "archive/downstream-before-$stamp"

git switch downstream
git reset --hard origin/downstream
git rebase --onto "$UPSTREAM_SHA" "$(git merge-base HEAD "$UPSTREAM_SHA")"
```

For a conflict, inspect `git status`, resolve only understood files, stage them,
and run `git rebase --continue`. Use `git rebase --abort` to return to the
pre-rebase checkout. Run the project checks before publishing. The distinct
ancestry gate for a **full rebase** is:

```bash
test "$(git merge-base downstream "$UPSTREAM_SHA")" = "$UPSTREAM_SHA"
git merge-base --is-ancestor "$UPSTREAM_SHA" downstream
git diff --check "$UPSTREAM_SHA"...downstream
```

After review, publish a rewritten branch only with an explicit lease tied to the
previously fetched value (never plain `--force`):

```bash
OLD_DOWNSTREAM=$(git rev-parse origin/downstream)
git push --force-with-lease=refs/heads/downstream:"$OLD_DOWNSTREAM" origin downstream
```

Rebase each open feature/release branch onto the rewritten `downstream`, after
creating and pushing its own forensic branch and archive tag. PRs remain based
on `downstream`.

## Workflow B: intentional partial upstream adoption

Use this when adopting selected upstream commits without claiming that the
latest upstream tip is an ancestor. This workflow deliberately does **not** use
the full-rebase ancestry gate.

Record the actual upstream base and the selected source commits before applying
anything:

```bash
git fetch --prune origin downstream
git fetch --prune microsoft main
UPSTREAM_BASE=$(git merge-base origin/downstream microsoft/main)
SELECTED_UPSTREAM_COMMITS="<oldest-sha> <newer-sha>"
stamp=$(date -u +%Y%m%dT%H%M%SZ)

git tag -a "archive/partial-base-$stamp" "$UPSTREAM_BASE" \
  -m "Upstream base for partial adoption: $UPSTREAM_BASE"
git branch "forensic/downstream-before-partial-$stamp" origin/downstream
git push origin "archive/partial-base-$stamp" \
  "forensic/downstream-before-partial-$stamp"

git switch -c "feature/partial-upstream-$stamp" origin/downstream
git cherry-pick -x $SELECTED_UPSTREAM_COMMITS
```

Resolve cherry-pick conflicts only after reviewing both sides; use
`git cherry-pick --continue` after staging or `git cherry-pick --abort` to roll
back the entire in-progress pick. The `-x` provenance trailer must remain in
each resulting commit.

The distinct validation path for **partial adoption** verifies the recorded
base, source-object existence, and cherry-pick provenance without incorrectly
requiring `microsoft/main` to be an ancestor:

```bash
RECORDED_BASE=$(git rev-parse "archive/partial-base-$stamp^{commit}")
test "$RECORDED_BASE" = "$UPSTREAM_BASE"
git merge-base --is-ancestor "$RECORDED_BASE" HEAD
for sha in $SELECTED_UPSTREAM_COMMITS; do
  git cat-file -e "$sha^{commit}"
  git log --format=%B origin/downstream..HEAD | grep -F "cherry picked from commit $sha"
done
git diff --check origin/downstream...HEAD
```

Run all project checks, review the resulting diff against `origin/downstream`,
and open the feature branch's PR into `downstream`. Record `UPSTREAM_BASE`, the
archive tag, selected SHAs, validation results, and conflicts in the PR body.
Do not update `main` through this workflow.

## Rollback and preservation

Preservation refs are append-only: never delete or retarget forensic branches,
and never move or replace an `archive/*` tag. If validation fails before push,
abort the rebase/cherry-pick or reset the work branch to its archive tag. If a
reviewed rewrite was already pushed, restore into a new recovery branch first:

```bash
git switch -c "recovery/downstream-$stamp" "archive/downstream-before-$stamp^{commit}"
git diff origin/downstream...HEAD
git push origin "recovery/downstream-$stamp"
```

Review that recovery diff and use a controlled, leased update only after team
approval. Do not make forensic or recovery refs the base of normal PRs. Keeping
the original refs visible makes conflict decisions, abort behavior, and rollback
independently reviewable.

## Pull-request and release gate

Before approval, reviewers verify that the base is `downstream`, the head is a
feature/release branch, the appropriate full-rebase or partial-adoption checks
passed, preservation refs exist remotely, conflicts and rollback decisions are
recorded, and CI is green for the exact head SHA. Pin DTU validation to that
same SHA. Keep a recovery PR draft and unmerged until credentialed validation is
attached.
