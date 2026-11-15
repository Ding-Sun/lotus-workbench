"""Dev helper: verify every source file is clean UTF-8 and Chinese literals survive."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ["工作台", "侧边栏", "速记", "热键", "数据目录", "已被其他程序或系统占用"]


def main() -> int:
    bad = 0
    haystack = ""
    for path in sorted(ROOT.glob("app/**/*.py")):
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            print(f"BOM   {path.relative_to(ROOT)}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            print(f"BAD   {path.relative_to(ROOT)}: {exc}")
            bad += 1
            continue
        haystack += text

    for token in EXPECTED:
        if token not in haystack:
            print(f"MISS  {token!r} not found in sources")
            bad += 1
    print("OK" if bad == 0 else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
