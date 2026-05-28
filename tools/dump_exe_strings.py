from __future__ import annotations

from pathlib import Path
import re
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python tools/dump_exe_strings.py game_data/RIPTIDE.EXE")
        return 2
    data = Path(sys.argv[1]).read_bytes()
    strings = sorted(set(m.group(0).decode('ascii', errors='replace') for m in re.finditer(rb'[ -~]{4,}', data)))
    for s in strings:
        print(s)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
