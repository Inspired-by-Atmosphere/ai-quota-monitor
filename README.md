# ai-quota-monitor

One place to see how much of every AI subscription you have left.

It pulls balance / quota / usage from each provider you use and writes a single
normalized JSON file — so any dashboard (a small screen, a terminal script, a cron
job that pings you) can render it. Standard library only, no dependencies.

| Channel | What you get | Auth |
|---|---|---|
| Volcengine Ark Coding Plan | used % per 5h / daily / weekly / monthly window + reset time | AK/SK (Signature V4) |
| Volcengine Ark Agent Plan (AFP) | quota / used / remaining per window | AK/SK (Signature V4) |
| DeepSeek platform | account balance | `DEEPSEEK_API_KEY` |
| OpenCode Go | 5h / weekly / monthly spend against $12 / $30 / $60 | `OPENCODE_GO_API_KEY` |
| GitHub Copilot | reserved slot (needs a PAT with the `copilot` scope) | `GITHUB_TOKEN` |

## Why

Subscriptions cap you per window now (5 hours / day / week / month). Hitting the
wall in the middle of a task is annoying; a one-line warning beforehand is not.
This started as "tell me before I run out" and grew into a small always-on screen.

## Quickstart

```bash
git clone https://github.com/Inspired-by-Atmosphere/ai-quota-monitor.git
cd ai-quota-monitor
python quota_panel.py --out data/quota.json
```

Requires Python 3.8+. No third-party packages.

Credentials — put them in a dotenv file (lookup order: `$QUOTA_ENV_FILE`, `./.env`,
`~/.hermes/.env`), or export them:

```dotenv
# Volcengine Ark (one pair per plan; _2 / _3 suffix = additional accounts)
VOLC_ARK_AK=your-ak
VOLC_ARK_SK=your-sk
VOLC_ARK_AK_2=your-ak-2
VOLC_ARK_SK_2=your-sk-2

DEEPSEEK_API_KEY=your-key
OPENCODE_GO_API_KEY=your-key
GITHUB_TOKEN=your-pat          # optional, Copilot channel
```

Environment variables win over the dotenv file. Channels without credentials are
reported as `no_cred` instead of failing the run.

## Standalone tools

```bash
python codingplan_usage.py                # all Coding Plan accounts, human readable
python codingplan_usage.py --warn-only    # one line only when a window crosses 60%
python afp_usage.py                       # Agent Plan (AFP) windows
python codingplan_warn.py                 # same as --warn-only, for cron
```

All of them accept `--env FILE` to point at a specific dotenv file.

## Output format

```json
{
  "generated_at": "2026-01-01 12:00:00",
  "channels": [
    {
      "id": "volc-codingplan",
      "name": "Volcengine Ark Coding Plan",
      "state": "ok",
      "status": "Running",
      "windows": [
        { "label": "5h window", "used_pct": 17.1, "reset": "01-01 21:27" }
      ]
    },
    { "id": "deepseek", "state": "ok", "is_available": true,
      "balances": [{ "currency": "CNY", "total_balance": "10.00", "topped_up": "10.00" }] }
  ]
}
```

See `examples/sample-quota.json` for a complete (fabricated) example.

## Wire it to a scheduler

```cron
# warn me only when something crosses the line
*/30 * * * * cd /opt/ai-quota-monitor && python codingplan_warn.py

# refresh the JSON that the screen / dashboard reads
0 */2 * * * cd /opt/ai-quota-monitor && python quota_panel.py --out /var/www/quota.json
```

## Limitations

- The Volcengine quota endpoints used here are management-plane APIs. They are not
  advertised as a stable public interface for this purpose; if the response shape
  changes, the parsers must be updated. The fields each channel relies on are
  documented in `docs/CHANNELS.md`.
- Numbers are reported exactly as the provider returns them — nothing is estimated.
- The Copilot channel needs a PAT with the `copilot` scope; otherwise it reports
  `unavailable` (a `ghu_` GitHub App token cannot read that endpoint).
- No front end in this repository on purpose: it emits JSON. Bring your own screen.

## License

MIT — see [LICENSE](LICENSE).
