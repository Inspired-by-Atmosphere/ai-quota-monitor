#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Threshold-only runner (cron friendly)
=====================================
Reuses codingplan_usage.py with CODINGPLAN_WARN_ONLY=1:
  - every window below the warning line -> prints nothing (silent cron job)
  - any window above it                 -> one warning line, so the scheduler can
                                           forward it to mail / IM / a phone
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["CODINGPLAN_WARN_ONLY"] = "1"

import codingplan_usage  # noqa: E402

sys.exit(codingplan_usage.main())
