#!/usr/bin/env python3
"""Validate a problem tree and print it.

usage: validate.py DIR [--tree]

DIR holds one markdown file per node (<id>.md) with the frontmatter described in
SPEC.md §5–6.
Exit 1 on any error. Warnings are reported, never fixed.
"""
import argparse
import pathlib
import re
import sys
from collections import Counter, defaultdict

try:
    import yaml
except ImportError:
    sys.exit("validate.py needs PyYAML (python3 -m pip install pyyaml)")

PROBLEM_STATUS = ("open", "fix-proposed", "fix-landed", "verified", "closed")
TASK_STATUS = ("open", "done", "dropped")
OBSERVATION_STATUS = ("noted", "promoted", "dismissed")
VOCAB = {"problem": PROBLEM_STATUS, "task": TASK_STATUS, "observation": OBSERVATION_STATUS}
UNRESOLVED = {"open", "fix-proposed", "fix-landed"}
PAST_OPEN = {"fix-proposed", "fix-landed", "verified"}
# Tasks closed before this date predate the evidence standard and are not held to it.
STANDARD_SINCE = "2026-09-24"
ASSIGNEE = re.compile(r"justin|agent|(pi|claude):\S+")
PRIORITY = ("P1", "P2", "P3")
CHECKBOX = re.compile(r"^\s*[-*] \[[ xX~]\]|#task\b")


def load(root):
    """Return (nodes, errors). Each node is its frontmatter dict plus _path and _body."""
    nodes, errors = [], []
    for path in sorted(pathlib.Path(root).glob("*.md")):
        if path.name.startswith("_") or path.stem.endswith("-template"):
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---", 4)
        if end < 0:
            errors.append((path.name, "unterminated frontmatter"))
            continue
        try:
            fm = yaml.safe_load(text[4:end]) or {}
        except yaml.YAMLError as exc:
            errors.append((path.name, f"yaml: {exc}"))
            continue
        if not isinstance(fm, dict) or "id" not in fm:
            continue
        fm["_path"] = path
        fm["_body"] = text[end + 4:]
        nodes.append(fm)
    return nodes, errors


def _artifacts(node):
    for key in ("before", "after"):
        for entry in node.get(key) or []:
            art = entry.get("artifact") if isinstance(entry, dict) else entry
            if art:
                yield key, art
    if node.get("artifact"):
        yield "artifact", node["artifact"]


def check(nodes):
    E, W = [], []
    byid = {}
    for n in nodes:
        if n["id"] in byid:
            E.append((n["id"], f"duplicate id, also {byid[n['id']]['_path'].name}"))
        byid[n["id"]] = n
    aliases = {}
    for n in nodes:
        for a in n.get("aliases") or []:
            if a in byid:
                E.append((n["id"], f"alias {a} collides with an id"))
            if a in aliases:
                E.append((n["id"], f"alias {a} also on {aliases[a]}"))
            aliases[a] = n["id"]

    roots = [n["id"] for n in nodes if n.get("parent") is None]
    if len(roots) != 1:
        E.append(("tree", f"expected one root (parent: null), found {len(roots)}: {roots}"))
    children = defaultdict(list)
    for n in nodes:
        children[n.get("parent")].append(n["id"])

    for n in nodes:
        i, t, s = n["id"], n.get("type"), n.get("status")
        if n["_path"].stem != i:
            E.append((i, f"filename {n['_path'].name} != id"))
        if not n.get("title"):
            E.append((i, "title empty"))
        if t not in VOCAB:
            E.append((i, f"type {t!r} not {'|'.join(VOCAB)}"))
            continue
        for key in ("parent", "discovered_from"):
            ref = n.get(key)
            if ref is not None and ref not in byid:
                E.append((i, f"{key} {ref} not found"))
        seen, cur = {i}, n.get("parent")
        while cur in byid:
            if cur in seen:
                E.append((i, "parent cycle"))
                break
            seen.add(cur)
            cur = byid[cur].get("parent")
        vocab = VOCAB[t]
        if s not in vocab:
            E.append((i, f"status {s!r} not in {'|'.join(vocab)}"))
        for key, art in _artifacts(n):
            if not (n["_path"].parent / art).exists():
                E.append((i, f"{key} artifact missing: {art}"))
        if t == "problem":
            sub = any(byid[c].get("type") == "problem" for c in children[i])
            _check_problem(n, sub, E, W)
        elif t == "observation":
            _check_observation(n, byid, E)
        elif s in ("done", "dropped") and not n.get("closed"):
            E.append((i, f"{s} without a closed date"))
        elif s == "done" and not n.get("after") and not pre_standard(n):
            E.append((i, "done needs after evidence (commit, test, job or artifact)"))
        who = n.get("assignee")
        if who is not None and not ASSIGNEE.fullmatch(str(who)):
            W.append((i, f"assignee {who!r} not justin|agent|pi:<session>|claude:<session>"))
    _check_members(nodes, byid, aliases, E, W)
    _check_rollup(byid, children, W)
    return E, W


def _check_members(nodes, byid, aliases, E, W):
    """Sprints (SPEC §19): `members:` lists nodes anywhere in the tree, in rank order. The sprint's one `sprint-*`
    tag is mirrored on every member so Obsidian can filter by it; the list stays the source of truth."""
    owner_of, listed = {}, defaultdict(set)
    for n in nodes:
        if not n.get("members"):
            continue
        i = n["id"]
        tags = [str(t) for t in n.get("tags") or [] if str(t).startswith("sprint-")]
        if len(tags) != 1:
            W.append((i, f"a sprint needs exactly one sprint-* tag, has {tags or 'none'}"))
        for t in tags:
            owner_of[t] = i
        for m in n["members"]:
            mid = m.get("id") if isinstance(m, dict) else None
            if mid is None:
                E.append((i, f"member entry {m!r} is not {{id: …}}"))
                continue
            ref = aliases.get(mid, mid)
            if ref not in byid:
                E.append((i, f"member {mid} not found"))
                continue
            if ref == i:
                E.append((i, "lists itself as a member"))
            elif ref in listed[i]:
                E.append((i, f"member {ref} listed twice"))
            listed[i].add(ref)
            if m.get("priority") is not None and m["priority"] not in PRIORITY:
                W.append((i, f"member {ref}: priority {m['priority']!r} not {'|'.join(PRIORITY)}"))
            for t in tags:
                if t not in map(str, byid[ref].get("tags") or []):
                    W.append((ref, f"member of {i} without its tag {t}"))
    for n in nodes:
        for t in map(str, n.get("tags") or []):
            if not t.startswith("sprint-"):
                continue
            s = owner_of.get(t)
            if s is None:
                W.append((n["id"], f"tag {t}: no sprint (a node with members:) carries it"))
            elif s != n["id"] and n["id"] not in listed[s]:
                W.append((n["id"], f"tag {t} but {s} does not list it"))


def _check_problem(n, has_children, E, W):
    i, s = n["id"], n.get("status")
    before, after, fix = n.get("before") or [], n.get("after") or [], n.get("fix") or []
    res, todo = n.get("resolution"), n.get("todo")
    if res not in (None, "soft", "hard"):
        E.append((i, f"resolution {res!r} not null|soft|hard"))
    if s in PAST_OPEN and not before:
        E.append((i, f"{s} needs before evidence"))
    if s in PAST_OPEN and not fix:
        E.append((i, f"{s} needs a fix entry"))
    if s == "verified" and not after:
        E.append((i, "verified needs after evidence"))
    if s == "verified" and not n.get("instrument"):
        E.append((i, "verified needs an instrument"))
    if s in ("verified", "closed") and not n.get("closed"):
        E.append((i, f"{s} without a closed date"))
    if res and s in ("open", "fix-proposed"):
        E.append((i, f"resolution {res} set while status is {s}"))
    if res == "hard" and s != "verified":
        E.append((i, "resolution hard requires status verified"))
    if res == "soft" and not todo:
        E.append((i, "resolution soft requires a todo"))
    if s == "verified" and not res:
        W.append((i, "verified without a resolution (hard|soft)"))
    if todo and res != "soft":
        W.append((i, "todo set but resolution is not soft"))
    if s == "open" and not before and not has_children:
        W.append((i, "problem without before evidence or sub-problems: a candidate, not a row"))


def _check_observation(n, byid, E):
    """SPEC §4: an outstanding issue parked on purpose. It needs the figure that shows it; once promoted it names
    the problem or task that took it on."""
    i, s = n["id"], n.get("status")
    if not n.get("before"):
        E.append((i, "observation needs before evidence (the figure that shows it)"))
    if s in ("promoted", "dismissed") and not n.get("closed"):
        E.append((i, f"{s} without a closed date"))
    if s == "promoted" and n.get("promoted_to") not in byid:
        E.append((i, f"promoted needs promoted_to naming an existing node, has {n.get('promoted_to')!r}"))


def pre_standard(n):
    return n.get("type") == "task" and bool(n.get("closed")) and str(n["closed"]) < STANDARD_SINCE


def stray_checkboxes(root):
    """Checkbox or #task lines in notes beside the tree: the tree is the only task list."""
    base = pathlib.Path(root).resolve().parent
    for path in sorted(base.rglob("*.md")):
        rel = path.relative_to(base)
        if rel.parts[0] in ("problems", "media"):
            continue
        hits = [k for k, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1) if CHECKBOX.search(ln)]
        if hits:
            yield str(rel), hits


def rollup(byid, children):
    """Counts over descendants: open leaf problems, soft problems, open tasks, and interior
    problems whose subtree is clear but which are still unresolved (await the user's collapse)."""
    memo = {}

    def agg(i):
        if i in memo:
            return memo[i]
        c = Counter()
        for ch in children.get(i, []):
            n = byid[ch]
            sub = agg(ch)
            if n.get("type") == "problem":
                # interior = has sub-problems; tasks under a problem do not make it interior
                if any(byid[g].get("type") == "problem" for g in children.get(ch, [])):
                    c["collapse"] += n.get("status") in UNRESOLVED and label(sub) == "clear"
                else:
                    c["open"] += n.get("status") in UNRESOLVED
                c["soft"] += n.get("resolution") == "soft"
            elif n.get("type") == "observation":
                c["noted"] += n.get("status") == "noted"   # shown, never counted as open work (label ignores it)
            else:
                c["tasks"] += n.get("status") == "open"
            c.update(sub)
        memo[i] = c
        return c

    for i in byid:
        agg(i)
    return memo


def label(c):
    if c["open"]:
        return "open"
    if c["soft"] or c["tasks"]:
        return "soft"
    if c["collapse"]:
        return "collapse"
    return "clear"


def _check_rollup(byid, children, W):
    for i, c in rollup(byid, children).items():
        if byid[i].get("status") == "verified" and c["open"]:
            W.append((i, f"verified with {c['open']} unresolved descendant problem(s)"))


def print_tree(nodes):
    byid = {n["id"]: n for n in nodes}
    children = defaultdict(list)
    for n in nodes:
        children[n.get("parent")].append(n["id"])
    for lst in children.values():
        lst.sort(key=lambda i: (byid[i].get("type") != "problem", str(byid[i].get("opened") or ""), i))
    memo = rollup(byid, children)

    def line(i):
        n = byid[i]
        tag = n.get("status", "?")
        if n.get("resolution"):
            tag += f"·{n['resolution']}"
        title = str(n.get("title", ""))
        title = title if len(title) <= 72 else title[:69] + "…"
        parts = [f"{i}  [{tag}]  {title}"]
        if n.get("aliases"):
            parts.append("(" + ", ".join(map(str, n["aliases"])) + ")")
        c = memo[i]
        if children.get(i):
            parts.append(("↓ " + label(c) + " " + " ".join(f"{k}:{v}" for k, v in c.items() if v)).rstrip())
        if n.get("members"):
            parts.append(f"⧉ members:{len(n['members'])}")
        return "  ".join(parts)

    def walk(i, prefix, last):
        print(prefix + ("└─ " if last else "├─ ") + line(i))
        kids = children.get(i, [])
        for k, ch in enumerate(kids):
            walk(ch, prefix + ("   " if last else "│  "), k == len(kids) - 1)

    for r in children.get(None, []):
        print(line(r))
        kids = children[r]
        for k, ch in enumerate(kids):
            walk(ch, "", k == len(kids) - 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir", help="folder of <id>.md nodes")
    ap.add_argument("--tree", action="store_true", help="print the tree with rollups")
    args = ap.parse_args()
    nodes, errors = load(args.dir)
    E, W = check(nodes)
    E = errors + E
    for rel, hits in stray_checkboxes(args.dir):
        W.append((rel, f"{len(hits)} checkbox/#task line(s) outside the tree (lines {', '.join(map(str, hits[:5]))})"))
    for who, msg in E:
        print(f"ERROR  {who}: {msg}")
    for who, msg in W:
        print(f"WARN   {who}: {msg}")
    if args.tree:
        if E or W:
            print()
        print_tree(nodes)
    print(f"\n{len(nodes)} nodes, {len(E)} errors, {len(W)} warnings")
    sys.exit(1 if E else 0)


if __name__ == "__main__":
    main()
