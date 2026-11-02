#!/usr/bin/env python3
"""OpenClaw 技能入口：调用 TenderCrawler scheduled_crawl.py。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    skill_dir = Path(__file__).resolve().parent.parent
    default_home = skill_dir.parent.parent
    home = Path(os.environ.get("TENDER_CRAWLER_HOME", str(default_home))).resolve()
    script = home / "scheduled_crawl.py"

    if not script.is_file():
        print(f"未找到 {script}，请设置 TENDER_CRAWLER_HOME", file=sys.stderr)
        return 1

    max_pages = os.environ.get("TENDER_CRAWLER_MAX_PAGES", "3")
    cmd = [
        sys.executable,
        str(script),
        "--max-pages",
        max_pages,
        "--json-summary",
    ]
    env = os.environ.copy()
    env.setdefault("TENDER_CRAWLER_HOME", str(home))
    env.setdefault("TENDER_CRAWLER_OUTPUT", str(home / "output"))

    print(f">> {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd, cwd=str(home), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
