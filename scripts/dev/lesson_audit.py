#!/usr/bin/env python3
"""Lesson Auditor — 手动触发质量审 / 月报"""

import sys
from pathlib import Path
from hagoku.agents.lesson_auditor.agent import LessonAuditor, run_monthly_audit, run_ad_hoc_audit


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--monthly":
        path = run_monthly_audit()
    else:
        path = run_ad_hoc_audit()
    print(f"Audit report: {path}")


if __name__ == "__main__":
    main()
