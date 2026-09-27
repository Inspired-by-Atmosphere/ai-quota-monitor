# Sanitize log

This repository was extracted from a private working copy. Every change made
while preparing it for publication is listed below by **category**, not by value —
original values are deliberately not recorded anywhere in this repo.

| Category | Items | Action |
|---|---|---|
| Credential file path | 3 scripts | hard-coded home-relative dotenv path replaced by `$QUOTA_ENV_FILE` → `./.env` → `~/.hermes/.env` lookup (`envutil.py`) |
| Account identity | 3 account labels | personal account descriptions replaced with `account-1/2/3` |
| Real usage data | 1 output dump | real balance / percentage values dropped; `examples/sample-quota.json` rebuilt with fabricated numbers |
| Local project paths | 4 diagnostics | messaging that pointed at a specific local install path rewritten to generic guidance |
| Personal/internal references | 4 docstrings & comments | references to an unrelated internal pipeline and its schedule removed |
| Language | all user-facing strings | console output and JSON window labels normalized to English so the tool is usable outside its original setup |

Nothing else was removed: the signing code, window parsing and CLI behaviour are
the same as the private original.
