# Downstream release policy

`main` is a clean mirror of Microsoft upstream. This recovery is based on
`265f4aeb3dfd69515740a847cfc7aba8dca85dfa`. Upstream updates are fetched and
fast-forwarded on `main`, then deliberately merged into `downstream` after CI.
Downstream-only changes never land directly on `main`.

Release work branches from `downstream` and opens one pull request back to
`downstream`. Preserve forensic branches and tags. Pin DTU validation to the
candidate commit, record CI and live evidence for that exact SHA, and do not
merge until credentialed DTU validation is complete.
