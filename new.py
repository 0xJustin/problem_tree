#!/usr/bin/env python3
"""Mint a node id and write a new problem or task file from a template.

usage: new.py DIR problem|task --parent ID --title "..." [--alias P-nn ...] [--discovered-from ID] [--assignee WHO]
       new.py DIR problem --root --prefix xyz --title "..."
       new.py EXPDIR experiment --id NAME --title "..." [--kind dagger|expert|grid|init-study] [--previous ID ...] [--prefix xyz]

Ids are <prefix>-<4 base36 chars of sha256(title + timestamp)>, beads style; the root is
<prefix>-root. The prefix is read from the existing root unless --prefix is given.
Prints the path written. Never overwrites.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate import load  # noqa: E402

TEMPLATES = pathlib.Path(__file__).resolve().parent / "templates"
B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def base36(n, width):
    out = ""
    while len(out) < width:
        n, r = divmod(n, 36)
        out = B36[r] + out
    return out


def mint(prefix, title, taken):
    stamp = datetime.datetime.now().isoformat()
    for salt in range(1000):
        h = hashlib.sha256(f"{title}{stamp}{salt}".encode()).digest()
        cand = f"{prefix}-{base36(int.from_bytes(h[:6], 'big'), 4)}"
        if cand not in taken:
            return cand
    sys.exit("could not mint a free id")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("type", choices=("problem", "task", "experiment"))
    ap.add_argument("--title", required=True)
    ap.add_argument("--id", help="experiment name (experiments are named, not hashed)")
    ap.add_argument("--kind", default="dagger")
    ap.add_argument("--previous", action="append", default=[])
    ap.add_argument("--parent")
    ap.add_argument("--alias", action="append", default=[])
    ap.add_argument("--discovered-from")
    ap.add_argument("--assignee", help="justin | agent | pi:<session> | claude:<session>")
    ap.add_argument("--root", action="store_true", help="create the root node (parent: null)")
    ap.add_argument("--prefix", help="project prefix, e.g. xyz; read from the root otherwise")
    args = ap.parse_args()

    root = pathlib.Path(args.dir)
    root.mkdir(parents=True, exist_ok=True)
    if args.type == "experiment":
        return new_experiment(root, args)
    nodes, errors = load(root)
    if errors:
        sys.exit("\n".join(f"{w}: {m}" for w, m in errors))
    taken = {n["id"] for n in nodes} | {a for n in nodes for a in n.get("aliases") or []}
    roots = [n for n in nodes if n.get("parent") is None]

    if args.root:
        if args.type != "problem" or not args.prefix:
            sys.exit("--root needs type problem and --prefix")
        if roots:
            sys.exit(f"root already exists: {roots[0]['id']}")
        prefix, nid, parent = args.prefix, f"{args.prefix}-root", None
    else:
        if not args.parent:
            sys.exit("--parent is required (or --root)")
        if args.parent not in taken:
            sys.exit(f"parent {args.parent} not found in {root}")
        prefix = args.prefix or (roots[0]["id"].rsplit("-", 1)[0] if roots else None)
        if not prefix:
            sys.exit("no root in DIR; pass --prefix")
        nid, parent = mint(prefix, args.title, taken), args.parent
    for a in args.alias:
        if a in taken:
            sys.exit(f"alias {a} already used")
    if args.discovered_from and args.discovered_from not in taken:
        sys.exit(f"discovered_from {args.discovered_from} not found")

    fields = {
        "{id}": nid,
        "{title}": json.dumps(args.title),  # JSON string == valid YAML double-quoted scalar
        "{title_plain}": args.title,
        "{parent}": parent or "null",
        "{aliases}": json.dumps(args.alias),
        "{discovered_from}": args.discovered_from or "null",
        "{assignee}": args.assignee or "null",
        "{date}": datetime.date.today().isoformat(),
        "{prefix}": prefix,
    }
    text = (TEMPLATES / f"{args.type}.md").read_text(encoding="utf-8")
    for k, v in fields.items():
        text = text.replace(k, v)
    out = root / f"{nid}.md"
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    out.write_text(text, encoding="utf-8")
    print(out)


def new_experiment(root, args):
    if not args.id or not re.fullmatch(r"[A-Za-z0-9][\w.-]*", args.id):
        sys.exit("--id NAME is required for experiments (letters, digits, . _ -)")
    nodes, errors = load(root)
    if errors:
        sys.exit("\n".join(f"{w}: {m}" for w, m in errors))
    ids = {n["id"] for n in nodes}
    if args.id in ids:
        sys.exit(f"experiment {args.id} already exists")
    for p in args.previous:
        if p not in ids:
            sys.exit(f"previous {p} not found in {root}")
    prefix = args.prefix or next((t for n in nodes for t in n.get("tags") or [] if t not in ("experiment", n.get("kind"))), "proj")
    fields = {"{id}": args.id, "{title}": json.dumps(args.title), "{title_plain}": args.title, "{kind}": args.kind,
              "{previous}": json.dumps(args.previous), "{prefix}": prefix}
    text = (TEMPLATES / "experiment.md").read_text(encoding="utf-8")
    for k, v in fields.items():
        text = text.replace(k, v)
    out = root / f"{args.id}.md"
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    out.write_text(text, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
