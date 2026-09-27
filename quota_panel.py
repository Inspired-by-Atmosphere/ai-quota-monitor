#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI quota panel — multi-channel usage collector (quota_panel.py)
===============================================================
Gathers balance / quota / usage from every configured LLM channel and writes one
normalized JSON file that any dashboard (web screen, terminal, cron) can render.

Channels:
  1. Volcengine Ark Coding Plan   GetCodingPlanUsage
  2. Volcengine Ark Agent Plan    GetAFPUsage
  3. DeepSeek platform            GET /user/balance
  4. OpenCode Go                  GET https://opencode.ai/zen/go/v1/usage
  5. GitHub Copilot               reserved slot; needs a PAT with copilot scope

Credentials (environment first, then a dotenv file):
  VOLC_ARK_AK / VOLC_ARK_SK, DEEPSEEK_API_KEY, OPENCODE_GO_API_KEY, GITHUB_TOKEN
Dotenv lookup order: $QUOTA_ENV_FILE -> ./.env -> ~/.hermes/.env

Output (default data/quota.json):
  {"generated_at": "...", "channels": [{"id", "name", "state", "windows": [...]}]}

Usage: python quota_panel.py [--out PATH] [--env FILE]
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

OUT_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "quota.json")
BJ_TZ = timezone(timedelta(hours=8))


def now_str():
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


# ---------- 火山方舟签名 (复用 codingplan_usage.py / afp_usage.py) ----------
def hmac_sha256(key, msg):
    if isinstance(msg, str):
        msg = msg.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).digest()


def sha256_hex(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def volc_sign(ak, sk, host, service, region, version, action):
    payload = "{}"
    xdate = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_date = xdate[:8]
    query = f"Action={action}&Version={version}"
    canonical_headers = f"host:{host}\nx-content-sha256:{sha256_hex(payload)}\nx-date:{xdate}\n"
    signed_headers = "host;x-content-sha256;x-date"
    canonical_request = "\n".join(
        ["POST", "/", query, canonical_headers, signed_headers, sha256_hex(payload)]
    )
    credential_scope = f"{short_date}/{region}/{service}/request"
    string_to_sign = "\n".join(["HMAC-SHA256", xdate, credential_scope, sha256_hex(canonical_request)])
    k_date = hmac_sha256(sk.encode(), short_date)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()
    authorization = (
        f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return query, xdate, authorization, payload


def volc_get(ak, sk, host, service, region, version, action, timeout=30):
    query, xdate, auth, payload = volc_sign(ak, sk, host, service, region, version, action)
    req = urllib.request.Request(f"https://{host}/?{query}", method="POST")
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    req.add_header("X-Date", xdate)
    req.add_header("X-Content-Sha256", sha256_hex(payload))
    req.add_header("Authorization", auth)
    req.data = payload.encode("utf-8")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    req.add_header("User-Agent", "Mozilla/5.0 (quota-panel)")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def fmt_time(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, BJ_TZ).strftime("%m-%d %H:%M")


# ---------- channel collectors ----------
def collect_volc_codingplan(env, ak, sk):
    """Volcengine Ark Coding Plan: used percent per window."""
    data = volc_get(ak, sk, "open.volcengineapi.com", "ark", "cn-beijing", "2024-01-01", "GetCodingPlanUsage")
    result = data.get("Result", {})
    status = result.get("Status", "?")
    quota = result.get("QuotaUsage") or []
    labels = {
        "session": "5h window",
        "daily": "daily window",
        "weekly": "weekly window",
        "monthly": "monthly window",
        "fiveday": "5-day window",
    }
    windows = []
    for item in quota:
        level = item.get("Level", "?")
        pct = item.get("Percent", 0.0)
        reset = item.get("ResetTimestamp", 0)
        windows.append({
            "label": labels.get(level, level),
            "used_pct": round(pct, 1),
            "reset": fmt_time(reset),
        })
    if not windows:
        return {"state": "unavailable", "status": status, "windows": [],
                "note": "response carries no QuotaUsage (inactive or reclaimed plan?)"}
    return {"state": "ok", "status": status, "windows": windows}


def collect_volc_afp(env, ak, sk):
    """Volcengine Ark Agent Plan: quota / used / remaining per window."""
    data = volc_get(ak, sk, "ark.cn-beijing.volcengineapi.com", "ark", "cn-beijing", "2024-01-01", "GetAFPUsage")
    result = data.get("Result", {})
    status = result.get("Status", "?")
    plan_type = result.get("PlanType", "?")
    field_map = [
        ("5h window", "AFPFiveHour"),
        ("daily window", "AFPDaily"),
        ("weekly window", "AFPWeekly"),
        ("monthly window", "AFPMonthly"),
    ]
    windows = []
    for label, field in field_map:
        w = result.get(field) or {}
        quota = w.get("Quota", 0)
        used = w.get("Used", 0)
        pct = used / quota * 100 if quota else 0
        windows.append({
            "label": label,
            "used": used,
            "quota": quota,
            "used_pct": round(pct, 1),
            "reset": fmt_time(w.get("ResetTime", 0) / 1000 if w.get("ResetTime") else 0),  # ms -> s
        })
    return {"state": "ok", "status": status, "plan_type": plan_type, "windows": windows}


def collect_deepseek(env, api_key):
    """DeepSeek platform balance."""
    url = "https://api.deepseek.com/user/balance"
    body = http_get(url, {"Authorization": f"Bearer {api_key}"})
    data = json.loads(body)
    is_avail = data.get("is_available")
    infos = data.get("balance_infos") or []
    rows = []
    for i in infos:
        rows.append({
            "currency": i.get("currency"),
            "total_balance": i.get("total_balance"),
            "topped_up": i.get("topped_up_balance"),
        })
    return {"state": "ok", "is_available": is_avail, "balances": rows}


def collect_opencode_go(env, api_key):
    """OpenCode Go subscription quota: 5h / weekly / monthly usage (limits $12 / $30 / $60)."""
    url = "https://opencode.ai/zen/go/v1/usage"
    body = http_get(url, {"Authorization": f"Bearer {api_key}"}, timeout=20)
    data = json.loads(body)
    usage = data.get("usage", {})
    limits = {"rolling": "$12", "weekly": "$30", "monthly": "$60"}
    labels = {"rolling": "5h window", "weekly": "weekly window", "monthly": "monthly window"}
    windows = []
    for key in ("rolling", "weekly", "monthly"):
        w = usage.get(key) or {}
        windows.append({
            "label": labels.get(key, key),
            "used_pct": w.get("percent"),
            "limit": limits.get(key),
            "reset": (w.get("resetsAt") or "")[:16].replace("T", " "),
        })
    return {"state": "ok", "windows": windows}


def collect_copilot(env, token):
    """GitHub Copilot: reserved slot. Reads /user/copilot/usage when GITHUB_TOKEN
    is a PAT that carries the `copilot` scope, otherwise reports `unavailable`."""
    pat = env.get("GITHUB_TOKEN") or ""
    if not pat:
        return {
            "state": "unavailable",
            "note": "reserved channel: set GITHUB_TOKEN to a PAT with the copilot scope to read usage",
        }
    try:
        body = http_get("https://api.github.com/user/copilot/usage",
                        {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"})
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"state": "unavailable",
                    "note": f"token rejected (HTTP {e.code}): needs a PAT with the copilot scope"}
        return {"state": "error", "note": f"read failed: HTTP {e.code}"}
    except Exception as e:
        return {"state": "error", "note": f"read failed: {e}"}
    data = json.loads(body)
    usage = data.get("usage") or []
    total = sum(u.get("total_credits_used") or 0 for u in usage)
    return {"state": "ok", "total_credits_used": total}


# ---------- main ----------
# (suffix, label) for each Ark Coding Plan account you want the panel to watch.
# suffix "" -> VOLC_ARK_AK / VOLC_ARK_SK, "_2" -> VOLC_ARK_AK_2 / VOLC_ARK_SK_2, ...
ACCOUNT_SUFFIXES = (("", ""), ("_2", "account-2"), ("_3", "account-3"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Aggregate LLM channel quota into a single JSON file")
    parser.add_argument("--out", default=OUT_DEFAULT, metavar="PATH", help="output JSON path")
    parser.add_argument("--env", metavar="FILE", help="dotenv file holding the credentials")
    args = parser.parse_args(argv)

    env, _ = load_env(args.env)
    ak = first_env(env, "VOLC_ARK_AK", "VOLC_ACCESS_KEY")
    sk = first_env(env, "VOLC_ARK_SK", "VOLC_SECRET_KEY")
    ds_key = first_env(env, "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    go_key = first_env(env, "OPENCODE_GO_API_KEY")

    channels = []

    # 1. Volcengine Ark Coding Plan — one entry per configured account
    for suffix, label in ACCOUNT_SUFFIXES:
        cred_names = (f"VOLC_ARK_AK{suffix}",) + (("VOLC_ACCESS_KEY",) if not suffix else ())
        secret_names = (f"VOLC_ARK_SK{suffix}",) + (("VOLC_SECRET_KEY",) if not suffix else ())
        acc_ak = first_env(env, *cred_names)
        acc_sk = first_env(env, *secret_names)
        chan_id = "volc-codingplan" + (f"-{label}" if label else "")
        chan_name = "Volcengine Ark Coding Plan" + (f" ({label})" if label else "")
        if not (acc_ak and acc_sk):
            if not suffix:  # only complain when the primary pair is missing
                channels.append({"id": chan_id, "name": chan_name, "state": "no_cred",
                                 "note": "missing VOLC_ARK_AK / VOLC_ARK_SK"})
            continue
        try:
            channels.append({"id": chan_id, "name": chan_name,
                             **collect_volc_codingplan(env, acc_ak, acc_sk)})
        except Exception as e:
            channels.append({"id": chan_id, "name": chan_name, "state": "error", "note": str(e)})

    # 2. Volcengine Ark Agent Plan
    if ak and sk:
        try:
            channels.append({"id": "volc-agentplan", "name": "Volcengine Ark Agent Plan",
                             **collect_volc_afp(env, ak, sk)})
        except Exception as e:
            channels.append({"id": "volc-agentplan", "name": "Volcengine Ark Agent Plan",
                             "state": "error", "note": str(e)})
    else:
        channels.append({"id": "volc-agentplan", "name": "Volcengine Ark Agent Plan",
                         "state": "no_cred", "note": "missing VOLC_ARK_AK / VOLC_ARK_SK"})

    # 3. DeepSeek
    if ds_key:
        try:
            channels.append({"id": "deepseek", "name": "DeepSeek",
                             **collect_deepseek(env, ds_key)})
        except Exception as e:
            channels.append({"id": "deepseek", "name": "DeepSeek",
                             "state": "error", "note": str(e)})
    else:
        channels.append({"id": "deepseek", "name": "DeepSeek",
                         "state": "no_cred", "note": "missing DEEPSEEK_API_KEY"})

    # 4. OpenCode Go
    if go_key:
        try:
            channels.append({"id": "opencode-go", "name": "OpenCode Go",
                             **collect_opencode_go(env, go_key)})
        except Exception as e:
            channels.append({"id": "opencode-go", "name": "OpenCode Go",
                             "state": "error", "note": str(e)})
    else:
        channels.append({"id": "opencode-go", "name": "OpenCode Go",
                         "state": "no_cred", "note": "missing OPENCODE_GO_API_KEY"})

    # 5. GitHub Copilot
    channels.append({"id": "copilot", "name": "GitHub Copilot",
                     **collect_copilot(env, env.get("COPILOT_GITHUB_TOKEN") or "")})

    payload = {"generated_at": now_str(), "channels": channels}

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ aggregated {now_str()} -> {args.out}")
    for c in channels:
        print(f"  - {c['name']}: state={c['state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
