# Channels — endpoints, auth, and the fields we depend on

Everything here is read-only: this project never changes anything on the provider
side, it only asks "how much is left".

## 1. Volcengine Ark Coding Plan

- Action: `GetCodingPlanUsage`, `Version=2024-01-01`, `Service=ark`, region `cn-beijing`
- Host: `open.volcengineapi.com` (POST, `?Action=...&Version=...`)
- Auth: Volcengine Signature V4, HMAC-SHA256 over `host;x-content-sha256;x-date`,
  signed with an Access Key pair (`VOLC_ARK_AK` / `VOLC_ARK_SK`)
- Fields used: `Result.Status`, `Result.QuotaUsage[].Level` (`session` / `daily` /
  `weekly` / `monthly` / `fiveday`), `.Percent`, `.ResetTimestamp` (unix seconds)
- Multiple plans: each account reads its own suffixed pair of variables
  (`VOLC_ARK_AK_2` / `VOLC_ARK_SK_2`, `_3`, ...)

## 2. Volcengine Ark Agent Plan (AFP)

- Action: `GetAFPUsage`, same version / service / region
- Host: `ark.cn-beijing.volcengineapi.com` — note this differs from the Coding Plan
  host above
- Auth: same Signature V4 scheme
- Fields used: `Result.Status`, `Result.PlanType`,
  `Result.AFP{FiveHour,Daily,Weekly,Monthly}.{Quota,Used,ResetTime}`
  (`ResetTime` is in milliseconds)
- Docs: <https://docs.volcengine.com/docs/82379/2479847>

> Both Ark endpoints are management-plane APIs rather than a documented billing
> interface; treat the shape as "may change without notice" and open an issue when
> a field moves.

## 3. DeepSeek platform

- `GET https://api.deepseek.com/user/balance`
- Auth: `Authorization: Bearer $DEEPSEEK_API_KEY`
- Fields used: `is_available`, `balance_infos[].{currency,total_balance,topped_up_balance}`

## 4. OpenCode Go

- `GET https://opencode.ai/zen/go/v1/usage`
- Auth: `Authorization: Bearer $OPENCODE_GO_API_KEY`
- Fields used: `usage.{rolling,weekly,monthly}.{percent,resetsAt}`; the dollar
  limits ($12 / $30 / $60) are hard-coded in `quota_panel.py` and may need updating
  if the plan changes.

## 5. GitHub Copilot

- `GET https://api.github.com/user/copilot/usage`
- Auth: `Authorization: Bearer $GITHUB_TOKEN` where the token is a PAT carrying the
  `copilot` scope. A `ghu_` GitHub App token returns 403 on this endpoint — the
  channel then reports `unavailable` instead of failing the whole run.
- Fields used: `usage[].total_credits_used` (summed)

## Adding a channel

1. Write a `collect_<name>(env, ...)` function returning a dict with at least
   `state` plus either `windows` or channel-specific fields.
2. Append it in `main()` following the same `ok` / `no_cred` / `error` convention.
3. Document the endpoint, auth and the exact fields you rely on here.
