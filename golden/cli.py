"""python -m golden validate|render params/dev.yaml [--out build]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from golden.params import ParamsError, load, render


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Golden path parameter tools.")
    sub = p.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="check a parameter file")
    v.add_argument("params", type=Path)
    r = sub.add_parser("render", help="validate, then write tfvars and Ansible vars")
    r.add_argument("params", type=Path)
    r.add_argument("--out", type=Path, default=Path("build"))
    args = p.parse_args(argv)

    try:
        data = load(args.params)
        if args.command == "validate":
            print(f"{args.params}: valid")
        else:
            print(f"rendered {render(data, args.out)}")
        return 0
    except ParamsError as exc:
        print(f"{args.params}: invalid", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
