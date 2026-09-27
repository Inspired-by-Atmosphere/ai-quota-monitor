#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Volcengine Ark Agent Plan — AFP usage query (GetAFPUsage)
=========================================================
Management-plane API, requires an Access Key (AK/SK) signed with the
Volcengine Signature V4 (HMAC-SHA256) scheme.
Docs: https://docs.volcengine.com/docs/82379/2479847

Credentials: environment first, then a dotenv file
  VOLC_ARK_AK / VOLC_ARK_SK   (or VOLC_ACCESS_KEY / VOLC_SECRET_KEY)
Dotenv lookup order: $QUOTA_ENV_FILE -> ./.env -> ~/.hermes/.env

Output: quota / used / remaining / reset time for the 5-hour, daily, weekly and
monthly windows, plus warning flags. Safe to run from cron.
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

HOST = "ark.cn-beijing.volcengineapi.com"
SERVICE = "ark"
REGION = "cn-beijing"
VERSION = "2024-01-01"
ACTION = "GetAFPUsage"
URL = f"https://{HOST}/"
QUERY = f"Action={ACTION}&Version={VERSION}"
BJ_TZ = timezone(timedelta(hours=8))


def load_creds(env_file=None):
    env, _ = load_env(env_file)
    return first_env(env, "VOLC_ARK_AK", "VOLC_ACCESS_KEY"), first_env(
        env, "VOLC_ARK_SK", "VOLC_SECRET_KEY"
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


def fmt_time(ms):
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000, BJ_TZ).strftime("%m-%d %H:%M")


def fmt_window(name, w):
    quota = w.get("Quota", 0)
    used = w.get("Used", 0)
    remain = quota - used
    pct = used / quota * 100 if quota else 0
    flag = ("⚠️" if remain / quota < 0.2 else ("▲" if pct > 60 else "✓")) if quota else "?"
    return (
        f"{name}: used {used:.0f} / {quota:.0f} AFP ({pct:.0f}%)"
        f" | remaining {remain:.0f} {flag} | reset {fmt_time(w.get('ResetTime'))}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Volcengine Ark Agent Plan (AFP) usage")
    parser.add_argument("--env", metavar="FILE", help="dotenv file with VOLC_ARK_AK / VOLC_ARK_SK")
    args = parser.parse_args(argv)

    ak, sk = load_creds(args.env)
    if not (ak and sk):
        print("❌ no AK/SK found: export VOLC_ARK_AK / VOLC_ARK_SK, or put them in a dotenv file")
        return 2
    try:
        data = fetch_usage(ak, sk)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        print(f"❌ HTTP {e.code}: {body}")
        if e.code in (401, 403):
            print("(signature or permission error: check the AK/SK pair and IAM policy)")
        return 1
    except Exception as e:
        print(f"❌ request failed: {e}")
        return 1

    result = data.get("Result", {})
    print(f"📊 Volcengine Ark Agent Plan — {result.get('PlanType', '?')} tier")
    print(fmt_window("5h window     ", result.get("AFPFiveHour", {})))
    print(fmt_window("daily window  ", result.get("AFPDaily", {})))
    print(fmt_window("weekly window ", result.get("AFPWeekly", {})))
    print(fmt_window("monthly window", result.get("AFPMonthly", {})))
    # warning roll-up
    warns = []
    for name, w in [("weekly", result.get("AFPWeekly", {})), ("monthly", result.get("AFPMonthly", {})),
                    ("5h", result.get("AFPFiveHour", {}))]:
        quota, used = w.get("Quota", 0), w.get("Used", 0)
        if quota and used / quota > 0.8:
            warns.append(f"{name} window at {used/quota*100:.0f}%")
    if warns:
        print("⚠️ warning: " + "; ".join(warns))
    else:
        print("✅ all windows within budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
