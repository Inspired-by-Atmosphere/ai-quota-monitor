#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Volcengine Ark Coding Plan — plan usage query (GetCodingPlanUsage)
==================================================================
Volcengine Signature V4 (HMAC-SHA256), Service=ark.
Note the host differs from GetAFPUsage: open.volcengineapi.com here,
ark.cn-beijing.volcengineapi.com there.

Multi-account: each account is read from a suffixed pair of variables, so you can
watch several plans at once (e.g. VOLC_ARK_AK / VOLC_ARK_AK_2 / VOLC_ARK_AK_3).
Add or remove entries in ACCOUNTS below to match your own setup.

Credentials: environment first, then a dotenv file
Dotenv lookup order: $QUOTA_ENV_FILE -> ./.env -> ~/.hermes/.env

Response (Result): Status, UpdateTimestamp, QuotaUsage[]
  QuotaUsage item: { Level: session|daily|weekly|monthly|fiveday, Percent, ResetTimestamp }

Output: per-account window usage in percent + reset time (UTC+8) + warnings.
Safe to run from cron.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from envutil import first_env, load_env

HOST = "open.volcengineapi.com"
SERVICE = "ark"
REGION = "cn-beijing"
VERSION = "2024-01-01"
ACTION = "GetCodingPlanUsage"
URL = f"https://{HOST}/"
QUERY = f"Action={ACTION}&Version={VERSION}"
BJ_TZ = timezone(timedelta(hours=8))

# One entry per Ark Coding Plan account. `suffix` is appended to the variable
# names, e.g. suffix "_2" -> VOLC_ARK_AK_2 / VOLC_ARK_SK_2.
ACCOUNTS = [
    {"label": "account-1", "suffix": ""},
    {"label": "account-2", "suffix": "_2"},
    {"label": "account-3", "suffix": "_3"},
]

LEVEL_LABELS = {
    "session": "5h window",
    "daily": "daily window",
    "weekly": "weekly window",
    "monthly": "monthly window",
    "fiveday": "5-day window",
}


def load_creds(suffix="", env_file=None):
    env, _ = load_env(env_file)
    return first_env(env, f"VOLC_ARK_AK{suffix}", "VOLC_ACCESS_KEY"), first_env(
        env, f"VOLC_ARK_SK{suffix}", "VOLC_SECRET_KEY"
    )


def hmac_sha256(key, msg):
    if isinstance(msg, str):
        msg = msg.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).digest()


def sha256_hex(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def sign_request(ak, sk, payload):
    now = datetime.now(timezone.utc)
    xdate = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = now.strftime("%Y%m%d")

    canonical_headers = f"host:{HOST}\nx-content-sha256:{sha256_hex(payload)}\nx-date:{xdate}\n"
    signed_headers = "host;x-content-sha256;x-date"
    canonical_request = "\n".join(
        ["POST", "/", QUERY, canonical_headers, signed_headers, sha256_hex(payload)]
    )
    credential_scope = f"{short_date}/{REGION}/{SERVICE}/request"
    string_to_sign = "\n".join(
        ["HMAC-SHA256", xdate, credential_scope, sha256_hex(canonical_request)]
    )
    k_date = hmac_sha256(sk.encode(), short_date)
    k_region = hmac_sha256(k_date, REGION)
    k_service = hmac_sha256(k_region, SERVICE)
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()
    authorization = (
        f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return xdate, authorization


def fetch_usage(ak, sk):
    payload = "{}"
    xdate, auth = sign_request(ak, sk, payload)
    req = urllib.request.Request(URL + "?" + QUERY, method="POST")
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    req.add_header("X-Date", xdate)
    req.add_header("X-Content-Sha256", sha256_hex(payload))
    req.add_header("Authorization", auth)
    req.data = payload.encode("utf-8")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fmt_time(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, BJ_TZ).strftime("%m-%d %H:%M")


WARN_THRESHOLD = 60.0


def query_account(ak, sk):
    """Return (status, lines, warns); status is None on failure, warns carrying the reason."""
    try:
        data = fetch_usage(ak, sk)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        extra = " (signature or permission error: check the AK/SK pair)" if e.code in (401, 403) else ""
        return None, [], [f"HTTP {e.code}: {body}{extra}"]
    except Exception as e:
        return None, [], [f"request failed: {e}"]

    result = data.get("Result", {})
    status = result.get("Status", "?")
    quota = result.get("QuotaUsage") or []
    if not quota:
        return None, [], [f"response has no QuotaUsage field (Status={status})"]

    warns = []
    lines = []
    for item in quota:
        level = item.get("Level", "?")
        pct = item.get("Percent", 0.0)
        reset = item.get("ResetTimestamp", 0)
        label = LEVEL_LABELS.get(level, level)
        flag = "⚠️" if pct >= 80 else ("▲" if pct >= 60 else "✓")
        lines.append(f"  {label}: {pct:.1f}% used {flag} | resets {fmt_time(reset)}")
        if pct >= 80:
            warns.append(f"{label} at {pct:.1f}%")
        elif pct >= WARN_THRESHOLD:
            warns.append(f"{label} at {pct:.1f}% (over warning line)")
    return status, lines, warns


def main(argv=None):
    parser = argparse.ArgumentParser(description="Volcengine Ark Coding Plan usage (multi-account)")
    parser.add_argument("--env", metavar="FILE", help="dotenv file with the AK/SK pairs")
    parser.add_argument("--warn-only", action="store_true",
                        help="print one warning line only when a window crosses the threshold (cron friendly)")
    args = parser.parse_args(argv)

    warn_only = args.warn_only or os.environ.get("CODINGPLAN_WARN_ONLY") == "1"
    all_warns = []
    out_lines = []

    for acc in ACCOUNTS:
        ak, sk = load_creds(acc["suffix"], args.env)
        if not (ak and sk):
            out_lines.append(
                f"[skip] {acc['label']}: no AK/SK (VOLC_ARK_AK{acc['suffix']} / VOLC_ARK_SK{acc['suffix']})"
            )
            continue
        status, lines, warns = query_account(ak, sk)
        if status is None:
            out_lines.append(f"[error] {acc['label']}: " + "; ".join(warns))
            continue
        out_lines.append(f"[{acc['label']}] Status={status}")
        out_lines.extend(lines)
        all_warns.extend(warns)

    if warn_only:
        if all_warns:
            print("⚠️ Coding Plan quota warning: " + "; ".join(all_warns))
        return 0

    print("📊 Volcengine Ark Coding Plan usage (multi-account)")
    for line in out_lines:
        print(line)
    if all_warns:
        print("⚠️ warning: " + "; ".join(all_warns))
    else:
        print("✅ all accounts within budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
