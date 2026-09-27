# Changelog

## 0.1.0 — 2026-01-01

First public release.

- `quota_panel.py`: aggregates Volcengine Ark Coding Plan, Volcengine Ark Agent
  Plan, DeepSeek, OpenCode Go and (reserved) GitHub Copilot into one normalized
  `quota.json`.
- `codingplan_usage.py`: standalone multi-account Coding Plan report with
  `--warn-only` for schedulers.
- `afp_usage.py`: standalone Agent Plan (AFP) report.
- `codingplan_warn.py`: threshold-only wrapper.
- `envutil.py`: stdlib dotenv resolver (`$QUOTA_ENV_FILE` → `./.env` → `~/.hermes/.env`).
- `scripts/check_secrets.py`: dependency-free secret / private-data scanner used as
  the pre-push gate.
- Zero third-party dependencies (Python 3.8+).
