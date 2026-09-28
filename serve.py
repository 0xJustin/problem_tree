#!/usr/bin/env python3
"""Problem-tree cockpit: a read-only FastAPI server over the vault's problem trees.

  .venv/bin/python serve.py [--port 8891] [--host 127.0.0.1] [--config config.yaml]

Run it where the vault is on local disk (the cluster); open it in a browser through the
same tunnel you use for code-server. Everything is read from disk per request except the
session index (background scan, cached). Writes: POST /api/promote -> new.py; POST
/api/node/{id}/categorize -> `claude -p` one-shot classification, written back as frontmatter `category:`.
Spec: agent_project_information/artifacts/2026-09-21_problem-tree-spec/SPEC.md §10.
"""
import argparse
import datetime as dt
import fnmatch
import json
import pathlib
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import defaultdict

import markdown
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from validate import STANDARD_SINCE, check, label, load, rollup  # noqa: E402

IMAGE_EXT = {".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp"}
VIDEO_EXT = {".mp4", ".webm", ".mov"}  # rollout videos under media/single/<run_id>/video/
SKIP_DIRS = {".obsidian", ".git", ".venv", "node_modules", ".smart-env", ".trash", "__pycache__"}
# node ids, legacy P-nn aliases, run ids (dd-mm-yyyy_hh-mm_xxxxxxxx) and experiment folders (yyyy-mm-dd_name)
ID_TOKEN = re.compile(r"\b[a-z]{2,8}-[0-9a-z]{4}\b|\bP-\d{2}\b|\b\d\d-\d\d-\d{4}_\d\d-\d\d_[a-z0-9]{8}\b|\b\d{4}-\d\d-\d\d_[A-Za-z][\w.-]*\b")
CACHE_VERSION = 3
RUN_ID = re.compile(r"\b\d\d-\d\d-\d{4}_\d\d-\d\d_[a-z0-9]{8}\b")
WIKI_EMBED = re.compile(r"!\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
WIKI_LINK = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
REL_IMG = re.compile(r"!\[([^\]]*)\]\((?!https?://|/|#)([^)\s]+)\)")


def expand(p):
    return pathlib.Path(p).expanduser().resolve()


# --------------------------------------------------------------------------- config
class Config:
    def __init__(self, path):
        c = yaml.safe_load(pathlib.Path(path).read_text()) or {}
        self.vault = expand(c.get("vault", "~/brain"))
        self.tree_globs = c.get("tree_globs", ["02-Projects/*/problems"])
        self.session_roots = [expand(p) for p in c.get("session_roots", [])]
        self.session_cache = expand(c.get("session_cache", "~/.cache/problem-tree/sessions.json"))
        self.repos = c.get("repos", {})
        self.default_repo = c.get("default_repo")
        # local prefix -> prefix as the cluster sees it; applied to copyable paths/commands
        self.path_map = {str(pathlib.Path(k).expanduser()): v for k, v in (c.get("path_map") or {}).items()}
        self.figure_tiers = c.get("figure_tiers", [])
        self.stage_order = c.get("stage_order", ["init", "checkpoint", "final", "health", "health_nokill", "nokill", "run"])
        self.experiment_globs = c.get("experiment_globs", ["02-Projects/*/*/experiments"])
        self.run_media = c.get("run_media", "../media/single/{run_id}")   # relative to the experiment note
        self.tree_ttl = float(c.get("tree_ttl", 2))          # seconds; collapses re-reads within a request
        self.note_index_ttl = float(c.get("note_index_ttl", 30))
        self.note_index_skip = set(c.get("note_index_skip", ["media"]))

        s = c.get("services") or {}
        self.ssh_host = s.get("ssh_host") or None
        self.port_pool = tuple(s.get("port_pool", [8892, 8899]))
        self.repo_roots = s.get("repo_roots", {})
        self.tensorboard = s.get("tensorboard", "tensorboard")
        self.observatory = s.get("observatory", {})

    def remote(self, p):
        s = str(p)
        for a, b in self.path_map.items():
            if s == a or s.startswith(a + "/"):
                return b + s[len(a):]
        return s

    def local(self, p):
        """Inverse of remote(): a cluster path as reachable from here (through the mount on the Mac)."""
        s = str(p)
        for a, b in self.path_map.items():
            if s == b or s.startswith(b + "/"):
                return a + s[len(b):]
        return s


# --------------------------------------------------------------------------- caching
class Stale:
    """Stale-while-revalidate. `get()` returns the last value at once; when it is older than
    `ttl` a background thread recomputes it. Only the very first call blocks. Over a network
    mount this is what keeps every request answering in milliseconds."""

    def __init__(self, fn, ttl):
        self.fn, self.ttl, self.val, self.at, self.busy, self.lock = fn, ttl, None, 0.0, False, threading.Lock()

    def get(self):
        if self.at == 0.0:
            with self.lock:
                if self.at == 0.0:
                    self.val, self.at = self.fn(), time.time()
            return self.val
        if time.time() - self.at > self.ttl and not self.busy:
            self.busy = True
            threading.Thread(target=self._refresh, daemon=True).start()
        return self.val

    def _refresh(self):
        try:
            v = self.fn()
            self.val, self.at = v, time.time()
        except Exception:
            self.at = time.time()
        finally:
            self.busy = False

    def invalidate(self):
        self.at = 0.0


# --------------------------------------------------------------------------- trees
class Trees:
    """All problem trees under the vault; re-read in the background after `tree_ttl`."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._dirs = Stale(self._scan_dirs, cfg.tree_ttl)
        self._trees = {}

    def invalidate(self):
        self._dirs.invalidate()
        for s in self._trees.values():
            s.invalidate()

    def _scan_dirs(self):
        out = {}
        for g in self.cfg.tree_globs:
            for d in sorted(self.cfg.vault.glob(g)):
                nodes, _ = load(d)
                roots = [n for n in nodes if n.get("parent") is None]
                if roots:
                    out[roots[0]["id"].rsplit("-", 1)[0]] = d
        return out

    def dirs(self):
        return self._dirs.get()

    def tree(self, prefix):
        d = self.dirs().get(prefix)
        if d is None:
            raise HTTPException(404, f"no tree with prefix {prefix}")
        if prefix not in self._trees:
            self._trees[prefix] = Stale(lambda: self._build(prefix, d), self.cfg.tree_ttl)
        return self._trees[prefix].get()

    def _build(self, prefix, d):
        nodes, load_errors = load(d)
        E, W = check(nodes)
        byid = {n["id"]: n for n in nodes}
        children = defaultdict(list)
        for n in nodes:
            children[n.get("parent")].append(n["id"])
        for lst in children.values():
            lst.sort(key=lambda i: (byid[i].get("type") != "problem", str(byid[i].get("opened") or ""), i))
        memo = rollup(byid, children)
        return {
            "prefix": prefix, "dir": str(d.relative_to(self.cfg.vault)),
            "root": children[None][0] if children[None] else None,
            "standard_since": STANDARD_SINCE,
            "nodes": {i: public(n) | {"children": children.get(i, []), "rollup": dict(memo[i]),
                                      "label": label(memo[i]) if children.get(i) else None}
                      for i, n in byid.items()},
            "errors": [list(e) for e in load_errors + E], "warnings": [list(w) for w in W],
        }

    def find(self, ident):
        """(prefix, tree, node) for an id or alias, across trees."""
        for prefix in self.dirs():
            t = self.tree(prefix)
            if ident in t["nodes"]:
                return prefix, t, t["nodes"][ident]
            for n in t["nodes"].values():
                if ident in (n.get("aliases") or []):
                    return prefix, t, n
        return None

    def all_ids(self):
        ids = {}
        for prefix in self.dirs():
            for i, n in self.tree(prefix)["nodes"].items():
                ids[i] = i
                for a in n.get("aliases") or []:
                    ids[a] = i
        return ids


# --------------------------------------------------------------------------- experiments (runs)
class Experiments:
    """type: experiment notes (one per experiment/sweep) with arms -> run_ids -> media galleries."""

    def __init__(self, cfg, trees):
        self.cfg, self.trees = cfg, trees
        self._all = Stale(self._scan, cfg.tree_ttl)
        self._galleries, self._stage_idx, self._obs_jobs = {}, {}, {}

    def invalidate(self):
        self._all.invalidate()

    def _scan(self):
        out = []
        for g in self.cfg.experiment_globs:
            for d in sorted(self.cfg.vault.glob(g)):
                nodes, _ = load(d)
                for n in nodes:
                    if n.get("type") == "experiment":
                        n["_project"] = str(d.parent.parent.relative_to(self.cfg.vault))
                        out.append(n)
        return out

    def all(self):
        return self._all.get()

    def ids(self):
        return {e["id"] for e in self.all()}

    def get(self, ident):
        for e in self.all():
            if e["id"] == ident or ident in (e.get("aliases") or []):
                return e
        return None

    def by_run_id(self):
        return {a["run_id"]: e for e in self.all() for a in e.get("arms") or [] if a.get("run_id")}

    def for_node(self, node):
        """Experiments linked to a tree node: declared in the note's nodes:, or derived from the
        node's before/after entries (run ids, jobs, copied_from paths) and its runs: field."""
        hits, byrun = {}, self.by_run_id()
        byjob = {a["job"]: e for e in self.all() for a in e.get("arms") or [] if a.get("job")}
        for e in self.all():
            for l in e.get("nodes") or []:
                if isinstance(l, dict) and l.get("id") == node["id"]:
                    hits.setdefault(e["id"], {"experiment": e, "roles": set()})["roles"].add(l.get("role") or "linked")
        for role in ("before", "after"):
            for ent in node.get(role) or []:
                if not isinstance(ent, dict):
                    continue
                hay = " ".join(str(v) for v in ent.values())
                e = byjob.get(ent.get("job")) or next((byrun[m] for m in RUN_ID.findall(hay) if m in byrun), None)
                if e:
                    hits.setdefault(e["id"], {"experiment": e, "roles": set()})["roles"].add(role)
        for r in node.get("runs") or []:
            e = self.get(r)
            if e:
                hits.setdefault(e["id"], {"experiment": e, "roles": set()})["roles"].add("linked")
        return [{"id": k, "title": v["experiment"]["title"], "kind": v["experiment"].get("kind"), "status": v["experiment"].get("status"),
                 "launched": str(v["experiment"].get("launched") or ""), "roles": sorted(v["roles"])} for k, v in hits.items()]

    def media_dir(self, e, run_id):
        return (e["_path"].parent / self.cfg.run_media.format(run_id=run_id)).resolve()

    def gallery(self, e):
        """[{arm, run_id, stage, card, pillar, url, vault, verdict, value, soft, n_pass, n_fail}] for every PNG;
        walked in the background after 20 s, so the run page never waits on the media folder."""
        if e["id"] not in self._galleries:
            self._galleries[e["id"]] = Stale(lambda: self._gallery(self.get(e["id"]) or e), 20)
        return self._galleries[e["id"]].get()

    def _gallery(self, e):
        """Per-arm figures come from media/single/<run_id>/ (level "run"). In `figures:` folders, a
        file at the top level is an aggregation across arms (level "experiment", shown above the
        tiers); a subfolder is treated as an arm (its own name, or the matching arm's run id)."""
        figs = []
        for a in e.get("arms") or []:
            d = self.media_dir(e, a["run_id"])
            if d.is_dir():
                figs += self._walk(d, a.get("name") or "main", a["run_id"], "run")
        arm_by_name = {a.get("name"): a for a in e.get("arms") or []}
        for extra in e.get("figures") or []:
            d = (e["_path"].parent / extra).resolve()
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.is_file() and (p.suffix.lower() in IMAGE_EXT or p.suffix.lower() in VIDEO_EXT):
                    figs += self._walk_files(d, [p], None, None, "experiment")
                elif p.is_dir():
                    a = arm_by_name.get(p.name)
                    figs += self._walk(p, p.name, a["run_id"] if a else None, "run")
        return figs

    def _walk(self, d, arm, run_id, level="run"):
        files = [p for p in sorted(d.rglob("*")) if p.suffix.lower() in IMAGE_EXT or p.suffix.lower() in VIDEO_EXT]
        return self._walk_files(d, files, arm, run_id, level)

    def _walk_files(self, d, files, arm, run_id, level):
        out = []
        for p in files:
            suf = p.suffix.lower()
            rel = p.relative_to(d)
            verdicts = self._verdicts(p.parent)
            v = verdicts.get(p.name, {})
            try:
                vault = str(p.relative_to(self.cfg.vault))
            except ValueError:
                continue
            out.append({"arm": arm, "run_id": run_id, "level": level, **classify(self.cfg, rel), "video": suf in VIDEO_EXT, "file": str(rel), "url": f"/file/{vault}", "vault": vault, **v})
        out.sort(key=lambda f: f["order"])
        return out

    _vcache = {}

    def _verdicts(self, stage_dir):
        """plot filename -> {verdict, value, soft, n_pass, n_fail} from results.jsonl in that folder."""
        f = stage_dir / "results.jsonl"
        if not f.exists():
            return {}
        key = (str(f), f.stat().st_mtime)
        if key in self._vcache:
            return self._vcache[key]
        out = {}
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            name = pathlib.Path(r.get("plot_path") or "").name or (re.sub(r"\[.*", "", r.get("name", "")) + ".png")
            o = out.setdefault(name, {"n_pass": 0, "n_fail": 0, "n": 0, "soft": bool(r.get("soft")), "names": []})
            o["n"] += 1
            o["n_pass"] += r.get("verdict") == "PASS"
            o["n_fail"] += r.get("verdict") == "FAIL"
            o["names"].append(r.get("name"))
            if o["n"] == 1:
                v = r.get("value")
                o["value"] = v if isinstance(v, (int, str, type(None))) or (isinstance(v, float) and v == v and abs(v) != float("inf")) else str(v)
        for o in out.values():
            o["verdict"] = "PASS" if o["n_fail"] == 0 and o["n_pass"] else ("FAIL" if o["n_pass"] == 0 and o["n_fail"] else ("MIXED" if o["n_pass"] and o["n_fail"] else "INCONCLUSIVE"))
            o["names"] = o["names"][:12]
        self._vcache[key] = out
        return out

    _rf = {}

    def run_files(self, e, run_id):
        key = (e["id"], run_id)
        if key not in self._rf:
            self._rf[key] = Stale(lambda: self._run_files(e, run_id), 60)
        return self._rf[key].get()

    def _run_files(self, e, run_id):
        d = self.media_dir(e, run_id)
        out = {}
        for name in ("config.yaml", "provenance.yaml"):
            if (d / name).exists():
                try:
                    out[name.split(".")[0]] = yaml.safe_load((d / name).read_text(encoding="utf-8")) or {}
                except yaml.YAMLError:
                    out[name.split(".")[0]] = {"_error": "unparseable"}
        return out

    def stage_notes(self, e):
        """Exporter notes in ../runs/ whose run_id matches one of the arms (index cached per folder)."""
        runs_dir = e["_path"].parent.parent / "runs"
        key = str(runs_dir)
        if key not in self._stage_idx:
            self._stage_idx[key] = Stale(lambda: self._index_stage_notes(runs_dir), 60)
        idx = self._stage_idx[key].get()
        rids = {a["run_id"] for a in e.get("arms") or [] if a.get("run_id")}
        return [n for rid in rids for n in idx.get(rid, [])]

    def _index_stage_notes(self, runs_dir):
        idx = defaultdict(list)
        for p in sorted(runs_dir.glob("*.md")):
            with open(p, encoding="utf-8", errors="replace") as fh:
                head = fh.read(1500)
            m = re.search(r"^run_id:\s*(\S+)", head, re.M)
            if not m:
                continue
            st = re.search(r"^stage:\s*(\S+)", head, re.M)
            np_ = re.search(r"^n_pass:\s*(\d+)", head, re.M)
            nf = re.search(r"^n_fail:\s*(\d+)", head, re.M)
            idx[m.group(1)].append({"run_id": m.group(1), "stage": st.group(1) if st else "", "note": str(p.relative_to(self.cfg.vault)),
                                    "n_pass": int(np_.group(1)) if np_ else None, "n_fail": int(nf.group(1)) if nf else None})
        return idx


STAGE_RE = re.compile(r"^(init|final|health_nokill|health|nokill|checkpoint\w*|ckpt\d+)$")
INSTANCE_RE = re.compile(r"^(.*?)\[(.+)\]$")


def classify(cfg, rel):
    """Place one figure in the user's tier scheme (config.yaml › figure_tiers).

    Returns tier (1-based, None if unassigned), tier_name, family (pattern index inside the tier),
    stage, card (aggregate name, `[instance]` stripped), instance, example (bool) and a sort key
    `order` = (tier, family, stage, checkpoint step, card, instance). Stage comes from the folder
    (`init/`, `final_examples/` -> final + example) or, for `activity/`, from the filename prefix."""
    parts, stem = rel.parts, rel.stem
    folder = parts[0] if len(parts) > 1 else ""
    stage, example, ckpt = "run", False, 0
    if folder.endswith("_examples"):
        stage, example = folder[: -len("_examples")], True
    elif STAGE_RE.match(folder):
        stage = folder
    elif folder:
        stage = folder                       # training/, activity/, video/ ... pseudo-stages
    m = INSTANCE_RE.match(stem)
    card, instance = (m.group(1), m.group(2)) if m else (stem, None)
    # a bracketed figure inside the stage folder is a per-instance *card* figure (e.g. the DNg100 rhythm
    # card per DN); only files under <stage>_examples/ are examples of an aggregate
    pm = re.match(r"^(init|ckpt(\d+)|checkpoint(\d*)|final)_(.+)$", stem)   # init_activity.png, ckpt6000_posterior_activity.png
    if pm and folder in ("activity", ""):
        stage, card = pm.group(1), pm.group(4)
    cm = re.match(r"^(?:ckpt|checkpoint)(\d+)$", stage)
    if cm:
        ckpt, stage_key = int(cm.group(1)), "checkpoint"
    else:
        stage_key = stage
    sub = str(rel) if not example else f"{folder}/{rel.name}"
    tier = tier_name = None
    family = 99
    for ti, t in enumerate(cfg.figure_tiers):
        for fi, pat in enumerate(t.get("match") or []):
            hit = (fnmatch.fnmatch(str(rel), pat) or fnmatch.fnmatch(sub, pat)) if "/" in pat else (fnmatch.fnmatch(card, pat) or fnmatch.fnmatch(stem, pat))
            if hit:
                tier, tier_name, family = ti + 1, t.get("name", str(ti + 1)), fi
                break
        if tier:
            break
    so = cfg.stage_order
    stage_idx = so.index(stage_key) if stage_key in so else len(so) + (0 if stage_key == "training" else 1)
    return {"tier": tier, "tier_name": tier_name, "family": family, "stage": stage, "card": card, "instance": instance,
            "example": example, "pillar": card.split(".")[0] if "." in card else "",
            "order": [tier or 99, family, stage_idx, ckpt, stage, card, instance or ""]}


# --------------------------------------------------------------------------- services (TensorBoard, observatory)
class Services:
    """Long-running helpers per experiment. A service is started where the cluster filesystem is
    native: locally when the cockpit runs on the cluster, over `ssh ssh_host` (with a matching
    `ssh -N -L` forward) when it runs on the Mac. Each takes a port from the pool and is opened in
    a new tab; status = the port answers."""

    def __init__(self, cfg):
        self.cfg, self.items, self.lock = cfg, {}, threading.Lock()

    @staticmethod
    def _listening(port):
        with socket.socket() as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def free_port(self):
        lo, hi = self.cfg.port_pool
        used = {it["port"] for it in self.items.values()}
        for p in range(lo, hi + 1):
            if p not in used and not self._listening(p):
                return p
        raise HTTPException(409, f"no free port in {lo}-{hi}")

    def start(self, key, cmd, cwd, port=None, env=None, daemonizes=False):
        """cmd is a shell string with {port} available; env a dict of extra variables."""
        with self.lock:
            cur = self.items.get(key)
            if cur and self.alive(key):
                return self.status(key)
            port = port or self.free_port()
            shell = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in (env or {}).items()) + " " + cmd.format(port=port)
            log = f"/tmp/problem-tree-{key}.log"
            item = {"key": key, "port": port, "url": f"http://localhost:{port}/", "cmd": shell.strip(), "cwd": cwd, "log": log,
                    "started": dt.datetime.now().isoformat(timespec="seconds"), "remote": bool(self.cfg.ssh_host), "proc": None, "fwd": None, "pid": None, "output": ""}
            if self.cfg.ssh_host:
                if daemonizes:
                    r = subprocess.run(["ssh", "-o", "BatchMode=yes", self.cfg.ssh_host, f"cd {shlex.quote(cwd)} && {shell}"], capture_output=True, text=True, timeout=180)
                    item["output"] = (r.stdout + r.stderr)[-4000:]
                else:
                    r = subprocess.run(["ssh", "-o", "BatchMode=yes", self.cfg.ssh_host, f"cd {shlex.quote(cwd)} && nohup {shell} > {log} 2>&1 & echo $!"], capture_output=True, text=True, timeout=60)
                    item["pid"] = (r.stdout.strip().splitlines() or [""])[-1]
                    item["output"] = r.stderr[-2000:]
                item["fwd"] = subprocess.Popen(["ssh", "-N", "-L", f"{port}:127.0.0.1:{port}", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30", self.cfg.ssh_host])
            else:
                if daemonizes:
                    r = subprocess.run(["bash", "-c", shell], cwd=cwd, capture_output=True, text=True, timeout=180)
                    item["output"] = (r.stdout + r.stderr)[-4000:]
                else:
                    item["proc"] = subprocess.Popen(["bash", "-c", shell], cwd=cwd, stdout=open(log, "w"), stderr=subprocess.STDOUT)
            self.items[key] = item
        return self.status(key)

    def alive(self, key):
        it = self.items.get(key)
        if not it:
            return False
        if it["proc"] is not None and it["proc"].poll() is not None:
            return False
        return self._listening(it["port"])

    def status(self, key):
        it = self.items.get(key)
        if not it:
            return {"key": key, "running": False}
        return {k: v for k, v in it.items() if k not in ("proc", "fwd")} | {"running": self.alive(key)}

    def stop(self, key):
        with self.lock:
            it = self.items.pop(key, None)
        if not it:
            return {"key": key, "running": False}
        if it["proc"] is not None:
            it["proc"].terminate()
        elif self.cfg.ssh_host and it["pid"]:
            subprocess.run(["ssh", "-o", "BatchMode=yes", self.cfg.ssh_host, f"kill {it['pid']}"], capture_output=True, timeout=30)
        if it["fwd"] is not None:
            it["fwd"].terminate()
        return {"key": key, "running": False}

    def run_once(self, cmd, cwd, env=None, timeout=240):
        """Foreground command (e.g. an LSF submission); returns its combined output."""
        shell = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in (env or {}).items()) + " " + cmd
        if self.cfg.ssh_host:
            r = subprocess.run(["ssh", "-o", "BatchMode=yes", self.cfg.ssh_host, f"cd {shlex.quote(cwd)} && {shell}"], capture_output=True, text=True, timeout=timeout)
        else:
            r = subprocess.run(["bash", "-c", shell], cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr)[-6000:], "cmd": shell.strip(), "cwd": cwd}

    def all(self):
        return [self.status(k) for k in list(self.items)]


def flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(d, list) and d and all(isinstance(x, (dict, list)) for x in d):
        for i, v in enumerate(d):
            out.update(flatten(v, f"{prefix}{i}."))
    else:
        out[prefix[:-1]] = d
    return out


def config_diff(a, b):
    fa, fb = flatten(a), flatten(b)
    keys = sorted(set(fa) | set(fb))
    return [{"key": k, "from": fa.get(k, "∅"), "to": fb.get(k, "∅")} for k in keys if fa.get(k, "∅") != fb.get(k, "∅")]


# Optional, best-effort categorical tag for color-coding the tree — not enforced by validate.py.
# A node's `category` isn't restricted to this list (a custom recategorize prompt may return
# something else); this is the starting taxonomy + the colors the UI knows how to render.
TAXONOMY = [
    {"name": "Sensory rigging", "description": "organ/sensor transduction, campaniform, FeCO, tactile bristles, sensory bounds/units", "color": "#3f6d99"},
    {"name": "Motor decoding", "description": "MN/muscle decoder, expert gait, body springs/biomechanical asymmetry", "color": "#7a5ea8"},
    {"name": "Biophysics & init calibration", "description": "conductance/tau/voltage calibration, init-state health", "color": "#8a7a2e"},
    {"name": "Training & evaluation", "description": "DAgger/LatentODE training dynamics, eval methodology, survival metric", "color": "#a8527a"},
    {"name": "Pipeline & repo infra", "description": "cross-repo sync, full-pipeline audits, upstream bug reports, worktree/branch admin", "color": "#9c7050"},
    {"name": "Cockpit/dashboard tooling", "description": "the problem-tree/cockpit UI itself", "color": "#4a8a7a"},
    {"name": "Literature & recordings", "description": "recorded expert data, literature-card grounding", "color": "#b0762e"},
]


def set_frontmatter_field(path, key, value):
    """Set (or insert) one scalar frontmatter key in place, touching nothing else in the file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError(f"{path}: unterminated frontmatter")
    fm_text, rest = text[4:end], text[end:]
    line = f"{key}: {json.dumps(value)}"
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    fm_text = pattern.sub(line, fm_text, count=1) if pattern.search(fm_text) else fm_text.rstrip("\n") + "\n" + line
    path.write_text("---\n" + fm_text + rest, encoding="utf-8")


def public(n):
    out = {k: v for k, v in n.items() if not k.startswith("_")}
    out["path"] = str(n["_path"])
    for k in ("opened", "closed"):
        if out.get(k) is not None:
            out[k] = str(out[k])
    return out


# --------------------------------------------------------------------------- notes + markdown
class NoteIndex:
    """stem -> vault path for wikilink resolution. Built in the background: a quick pass over
    02-Projects first, then the whole vault; refreshed after `note_index_ttl`. Never blocks a request."""

    def __init__(self, cfg):
        self.cfg, self.built, self.by_stem, self.paths, self.busy = cfg, 0.0, {}, set(), False

    def start(self):
        def initial():
            self._build([self.cfg.vault / "02-Projects"])
            self._build([self.cfg.vault])
        threading.Thread(target=initial, daemon=True).start()

    def _build(self, roots):
        by_stem, paths = defaultdict(list), set()
        skip = SKIP_DIRS | self.cfg.note_index_skip
        for root in roots:
            if not root.is_dir():
                continue
            for p in root.rglob("*.md"):
                rel = p.relative_to(self.cfg.vault)
                if any(part in skip for part in rel.parts):
                    continue
                paths.add(str(rel))
                by_stem[p.stem.lower()].append(rel)
        self.by_stem, self.paths, self.built = by_stem, paths, time.time()

    def refresh(self):
        if time.time() - self.built < self.cfg.note_index_ttl or self.busy:
            return
        self.busy = True

        def run():
            try:
                self._build([self.cfg.vault])
            finally:
                self.busy = False
        threading.Thread(target=run, daemon=True).start()

    def resolve(self, target):
        """Obsidian-style: full vault path (with/without .md) or unique-ish stem."""
        self.refresh()
        t = target.strip().strip("/")
        for cand in (t, t + ".md"):
            if cand in self.paths:
                return pathlib.Path(cand)
        hits = self.by_stem.get(pathlib.Path(t).stem.lower(), [])
        if hits:
            return sorted(hits, key=lambda r: len(str(r)))[0]
        if (self.cfg.vault / t).exists():  # non-md attachment given by path
            return pathlib.Path(t)
        return None


class Renderer:
    def __init__(self, cfg, notes, trees, experiments=None):
        self.cfg, self.notes, self.trees, self.experiments = cfg, notes, trees, experiments

    def html(self, text, note_path):
        ids = self.trees.all_ids()
        note_dir = note_path.parent

        def embed(m):
            target, alt = m.group(1).strip(), m.group(2)
            rel = self.notes.resolve(target)
            if rel is None:
                return f'<span class="broken">![[{target}]]</span>'
            if rel.suffix.lower() in IMAGE_EXT:
                return f'<img class="embed" src="/file/{rel}" alt="{alt or rel.name}" data-vault="{rel}">'
            return f'<a class="wiki" href="#/note/{rel}">📄 {alt or rel.stem}</a>'

        exp_ids = self.experiments.ids() if self.experiments else set()

        def link(m):
            target, alt = m.group(1).strip(), m.group(2)
            if target in ids:
                return f'<a class="wiki node" href="#/node/{ids[target]}">{alt or target}</a>'
            if target in exp_ids:
                return f'<a class="wiki exp" href="#/run/{target}">{alt or target}</a>'
            rel = self.notes.resolve(target)
            if rel is None:
                return f'<span class="broken">[[{alt or target}]]</span>'
            return f'<a class="wiki" href="#/note/{rel}">{alt or target}</a>'

        def relimg(m):
            alt, src = m.group(1), m.group(2)
            try:
                abs_ = (self.cfg.vault / note_dir / src).resolve().relative_to(self.cfg.vault)
            except ValueError:
                return m.group(0)
            return f'<img class="embed" src="/file/{abs_}" alt="{alt}" data-vault="{abs_}">'

        text = WIKI_EMBED.sub(embed, text)
        text = WIKI_LINK.sub(link, text)
        text = REL_IMG.sub(relimg, text)
        return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])


# --------------------------------------------------------------------------- sessions
class SessionIndex:
    """Which agent sessions mention which node ids. Scans pi + Claude JSONL logs in the
    background; per-file results cached by (mtime, size) in a JSON file."""

    def __init__(self, cfg):
        self.cfg, self.lock, self.files, self.scanning, self.last = cfg, threading.Lock(), {}, False, None
        try:
            data = json.loads(cfg.session_cache.read_text())
            if data.get("_version") == CACHE_VERSION:
                self.files = {k: v for k, v in data.items() if k != "_version"}
        except (OSError, ValueError, AttributeError):
            pass

    def start(self, every=300):
        def loop():
            while True:
                self.scan()
                time.sleep(every)
        threading.Thread(target=loop, daemon=True).start()

    def scan(self):
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
        try:
            seen = set()
            for root in self.cfg.session_roots:
                if not root.is_dir():
                    continue
                for p in root.rglob("*.jsonl"):
                    key = str(p)
                    seen.add(key)
                    st = p.stat()
                    old = self.files.get(key)
                    if old and old["mtime"] == st.st_mtime and old["size"] == st.st_size:
                        continue
                    rec = parse_session(p, self.cfg.session_roots)
                    if rec:
                        rec.update(mtime=st.st_mtime, size=st.st_size)
                        with self.lock:
                            self.files[key] = rec
            with self.lock:
                for k in list(self.files):
                    if k not in seen:
                        del self.files[k]
                self.cfg.session_cache.parent.mkdir(parents=True, exist_ok=True)
                self.cfg.session_cache.write_text(json.dumps(self.files | {"_version": CACHE_VERSION}))
                self.last = time.time()
        finally:
            self.scanning = False

    def query(self, ids):
        ids = set(ids)
        with self.lock:
            hits = [r | {"hits": sorted(ids & set(r["ids"]))} for r in self.files.values() if ids & set(r["ids"])]
        for r in hits:
            r.pop("ids", None)
            r.update(commands(self.cfg, r))
        return sorted(hits, key=lambda r: r.get("started") or "", reverse=True)

    def status(self):
        return {"files": len(self.files), "scanning": self.scanning, "last": self.last}


_LIVE = {"t": 0.0, "v": {}}


def herdr_live(ttl=5):
    """session path or id -> herdr pane state; empty where herdr is absent (the Mac app)."""
    if time.time() - _LIVE["t"] > ttl:
        v = {}
        try:
            out = subprocess.run(["herdr", "agent", "list"], capture_output=True, text=True, timeout=2).stdout
            for a in json.loads(out)["result"]["agents"]:
                v[(a.get("agent_session") or {}).get("value")] = {k: a.get(k) for k in ("agent_status", "tab_id", "pane_id")}
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            pass
        _LIVE.update(t=time.time(), v=v)
    return _LIVE["v"]


def node_sessions(cfg, sessions, n):
    """Grep hits, with the node's `sessions:` refs flagged `working` (listed first, stubbed if not yet indexed)."""
    refs = {str(s["ref"]): s.get("harness", "pi") for s in n.get("sessions") or [] if isinstance(s, dict) and s.get("ref")}
    hits, live = sessions.query([n["id"], *(n.get("aliases") or [])]), herdr_live()
    for r in hits:
        r["working"] = bool(refs.keys() & {r["session_id"], r["path"]})
        refs.pop(r["session_id"], None), refs.pop(r["path"], None)
    hits += [{"harness": h, "session_id": ref, "path": ref, "working": True, "hits": [], "n_user": 0,
              "resume": f'pi --session {ref}' if h == "pi" else f"claude --resume {ref}", "fork": None}
             for ref, h in refs.items()]
    for r in hits:
        r["live"] = live.get(r["path"]) or live.get(r["session_id"])
    return sorted(hits, key=lambda r: not r["working"])


def commands(cfg, rec):
    """Resume/fork commands as typed on the cluster (path_map applied)."""
    if rec["harness"] == "pi":
        p = cfg.remote(rec["path"])
        return {"resume": f'pi --session "{p}"', "fork": f'pi --fork "{p}"'}
    cd = f'cd "{cfg.remote(rec["cwd"])}" && ' if rec.get("cwd") else ""
    return {"resume": f"{cd}claude --resume {rec['session_id']}", "fork": None}


def _text_blocks(content):
    if isinstance(content, str):
        return [content]
    return [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]


TS_RE = re.compile(r'"timestamp":\s*"([^"]+)"')
CWD_RE = re.compile(r'"cwd":\s*"([^"]+)"')
SID_RE = re.compile(r'"sessionId":\s*"([^"]+)"')
USER_HINT = ('"role":"user"', '"role": "user"', '"type":"user"', '"type": "user"')
SKIP_HINT = ('"tool_result"', '"toolResult"', '"isMeta":true', '"isMeta": true')


def parse_session(path, roots):
    """Cheap pass over a JSONL transcript: regex for ids, timestamps, cwd and session id; JSON-parse
    only lines that can carry user text. Yields the GIL every few thousand lines so requests stay
    responsive while a first scan runs."""
    harness = "pi" if "/.pi/" in str(path) else "claude"
    rec = {"harness": harness, "path": str(path), "session_id": path.stem.split("_")[-1] if harness == "pi" else path.stem,
           "cwd": None, "started": None, "ended": None, "first_user": None, "n_user": 0, "ids": []}
    ids = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i % 2000 == 1999:
                    time.sleep(0)
                ids.update(ID_TOKEN.findall(line))
                m = TS_RE.search(line)
                if m:
                    rec["started"] = rec["started"] or m.group(1)
                    rec["ended"] = m.group(1)
                if rec["cwd"] is None:
                    m = CWD_RE.search(line)
                    if m:
                        rec["cwd"] = m.group(1)
                if harness == "pi" and i == 0:
                    try:
                        d = json.loads(line)
                        if d.get("type") == "session":
                            rec["session_id"] = d.get("id", rec["session_id"])
                    except ValueError:
                        pass
                elif harness == "claude" and rec["session_id"] == path.stem:
                    m = SID_RE.search(line)
                    if m:
                        rec["session_id"] = m.group(1)
                if not any(h in line for h in USER_HINT) or any(h in line for h in SKIP_HINT):
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if harness == "pi":
                    msg = d.get("message") if d.get("type") == "message" else None
                else:
                    msg = d.get("message") if d.get("type") == "user" and not d.get("isMeta") else None
                if msg and msg.get("role") == "user":
                    texts = [x for x in _text_blocks(msg.get("content")) if x.strip() and not x.lstrip().startswith("<")]
                    if texts:
                        rec["n_user"] += 1
                        if rec["first_user"] is None:
                            rec["first_user"] = texts[0].strip()[:240]
    except OSError:
        return None
    rec["ids"] = sorted(ids)
    return rec


def transcript(path, limit=4000):
    harness = "pi" if "/.pi/" in str(path) else "claude"
    turns = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            ts = d.get("timestamp")
            if harness == "pi":
                if d.get("type") != "message":
                    continue
                msg = d["message"]
                role = msg.get("role")
                for b in msg.get("content") or []:
                    if b.get("type") == "text":
                        turns.append({"role": role, "kind": "text", "ts": ts, "text": b["text"]})
                    elif b.get("type") == "toolCall":
                        turns.append({"role": "assistant", "kind": "tool_call", "ts": ts, "name": b.get("name"),
                                      "text": json.dumps(b.get("arguments"), ensure_ascii=False)[:2000]})
                    elif role == "toolResult" or b.get("type") == "toolResult":
                        turns.append({"role": "tool", "kind": "tool_result", "ts": ts, "text": str(b.get("text", ""))[:4000]})
            else:
                if d.get("type") not in ("user", "assistant") or d.get("isMeta"):
                    continue
                msg = d["message"]
                role = msg.get("role")
                content = msg.get("content")
                if isinstance(content, str):
                    turns.append({"role": role, "kind": "text", "ts": ts, "text": content})
                    continue
                for b in content or []:
                    t = b.get("type")
                    if t == "text":
                        turns.append({"role": role, "kind": "text", "ts": ts, "text": b["text"]})
                    elif t == "tool_use":
                        turns.append({"role": "assistant", "kind": "tool_call", "ts": ts, "name": b.get("name"),
                                      "text": json.dumps(b.get("input"), ensure_ascii=False)[:2000]})
                    elif t == "tool_result":
                        c = b.get("content")
                        text = c if isinstance(c, str) else "\n".join(_text_blocks(c))
                        turns.append({"role": "tool", "kind": "tool_result", "ts": ts, "text": text[:4000]})
            if len(turns) >= limit:
                turns.append({"role": "system", "kind": "text", "ts": ts, "text": f"… truncated at {limit} entries"})
                break
    return turns


# --------------------------------------------------------------------------- links for evidence / fix
def link_repo(cfg, repo, commit=None, path=None, pr=None):
    base = cfg.repos.get(repo or cfg.default_repo)
    if not base:
        return None
    if pr:
        return f"{base}/pull/{pr}"
    if path:
        return f"{base}/blob/{commit or 'HEAD'}/{path}"
    if commit:
        return f"{base}/commit/{commit}"
    return base


def resolve_evidence(cfg, notes, trees, entry, note_path):
    if isinstance(entry, str):
        entry = {"artifact": entry}
    e = dict(entry)
    if e.get("artifact"):
        try:
            rel = (cfg.vault / note_path.parent / e["artifact"]).resolve().relative_to(cfg.vault)
            e["artifact_vault"] = str(rel)
            e["artifact_url"] = f"/file/{rel}"
            e["artifact_exists"] = (cfg.vault / rel).exists()
            suf = rel.suffix.lower()
            e["artifact_kind"] = "image" if suf in IMAGE_EXT else suf.lstrip(".") or "file"
        except ValueError:
            e["artifact_exists"] = False
    if e.get("data"):
        e["data_url"] = link_repo(cfg, e.get("repo"), e.get("commit"), e["data"])
    if e.get("commit"):
        e["commit_url"] = link_repo(cfg, e.get("repo"), e["commit"])
    if e.get("note"):
        m = WIKI_LINK.search(str(e["note"]))
        if m:
            target = m.group(1)
            ids = trees.all_ids()
            rel = notes.resolve(target)
            e["note_href"] = f"#/node/{ids[target]}" if target in ids else (f"#/note/{rel}" if rel else None)
            e["note_title"] = m.group(2) or target
    return e


def resolve_fix(cfg, entry):
    if isinstance(entry, str):
        return {"note": entry}
    e = dict(entry)
    if e.get("pr"):
        m = re.fullmatch(r"([\w.-]+)#(\d+)", str(e["pr"]))
        if m:
            e["url"] = link_repo(cfg, m.group(1), pr=m.group(2))
    if e.get("commit"):
        m = re.fullmatch(r"(?:([\w.-]+)@)?([0-9a-f]{7,40})", str(e["commit"]))
        if m:
            e["url"] = link_repo(cfg, m.group(1), commit=m.group(2))
    return e


def candidates(cfg, project_dir):
    """Bullets under '## Candidates' in any type: ledger note of the project."""
    out = []
    for p in sorted(project_dir.rglob("*.md")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^type:\s*ledger\s*$", text[:2000], re.M):
            continue
        m = re.search(r"^## Candidates.*?$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if not m:
            continue
        for b in re.finditer(r"^- (.*(?:\n(?!- |\n).*)*)", m.group(1), re.M):
            item = b.group(1).strip()
            t = re.match(r"\*\*(.+?)\*\*", item)
            out.append({"title": t.group(1) if t else item[:120], "text": item, "note": str(p.relative_to(cfg.vault))})
    return out


# --------------------------------------------------------------------------- app
def build_app(cfg):
    trees, notes = Trees(cfg), NoteIndex(cfg)
    notes.start()
    experiments = Experiments(cfg, trees)
    render = Renderer(cfg, notes, trees, experiments)
    sessions = SessionIndex(cfg)
    services = Services(cfg)

    def exp_paths(e):
        """Cluster-side paths for an experiment: repo root, experiment dir, runs dir, observatory bundle."""
        root = cfg.repo_roots.get(e.get("repo") or cfg.default_repo)
        if not root or not e.get("experiment_dir"):
            return None
        exp = f"{root}/{e['experiment_dir']}"
        return {"root": root, "exp": exp, "runs": f"{exp}/runs", "bundle": f"{exp}/{cfg.observatory.get('bundle_subdir', 'dashboard')}"}

    def progress(e):
        """Which stages have figures, across arms: the run's actual progress regardless of `status:`."""
        stages = {f["stage"] for f in experiments.gallery(e) if f.get("level") == "run"}
        return {"init": "init" in stages, "checkpoint": any(s.startswith(("ckpt", "checkpoint")) for s in stages),
                "final": "final" in stages, "training": "training" in stages, "video": "video" in stages}

    def warm():  # first build of every cache, off the request path
        try:
            for prefix in trees.dirs():
                trees.tree(prefix)
            for e in experiments.all():
                experiments.gallery(e)
                experiments.stage_notes(e)
                for a in e.get("arms") or []:
                    experiments.run_files(e, a["run_id"])
        except Exception as exc:  # a broken note must not take the server down
            print("warm-up:", exc, flush=True)
        sessions.start()
    threading.Thread(target=warm, daemon=True).start()
    app = FastAPI(title="problem-tree cockpit")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (HERE / "webui" / "index.html").read_text(encoding="utf-8")

    @app.get("/webui/{name}")
    def webui(name: str):
        target = (HERE / "webui" / name).resolve()
        if target.parent != (HERE / "webui").resolve() or not target.is_file():
            raise HTTPException(404, name)
        return FileResponse(target)

    @app.get("/api/trees")
    def api_trees():
        return [{"prefix": k, "dir": str(v.relative_to(cfg.vault))} for k, v in trees.dirs().items()]

    @app.get("/api/tree/{prefix}")
    def api_tree(prefix: str):
        return trees.tree(prefix)

    @app.get("/api/node/{ident}")
    def api_node(ident: str):
        hit = trees.find(ident)
        if not hit:
            raise HTTPException(404, f"no node {ident}")
        prefix, t, n = hit
        path = pathlib.Path(n["path"])
        body = path.read_text(encoding="utf-8")
        body = body[body.find("\n---", 4) + 4:]
        body = re.sub(r"^\s*# .*\n", "", body, count=1)  # H1 repeats the title
        chain, cur = [], n.get("parent")
        while cur and cur in t["nodes"]:
            chain.append({"id": cur, "title": t["nodes"][cur]["title"]})
            cur = t["nodes"][cur].get("parent")
        kids = [t["nodes"][c] for c in n["children"]]
        return {
            "tree": prefix, "node": n, "path_remote": cfg.remote(n["path"]),
            "body_html": render.html(body, path.relative_to(cfg.vault)),
            "parents": chain[::-1],
            "children": [{k: c.get(k) for k in ("id", "title", "type", "status", "resolution", "label", "rollup", "opened")} for c in kids],
            "discovered_from": ({"id": n["discovered_from"], "title": t["nodes"][n["discovered_from"]]["title"]}
                                if n.get("discovered_from") in t["nodes"] else None),
            "discovered": [{"id": o["id"], "title": o["title"]} for o in t["nodes"].values() if o.get("discovered_from") == n["id"]],
            "before": [resolve_evidence(cfg, notes, trees, e, path.relative_to(cfg.vault)) for e in n.get("before") or []],
            "after": [resolve_evidence(cfg, notes, trees, e, path.relative_to(cfg.vault)) for e in n.get("after") or []],
            "artifact": (resolve_evidence(cfg, notes, trees, {"artifact": n["artifact"]}, path.relative_to(cfg.vault))
                         if n.get("artifact") else None),
            "fix": [resolve_fix(cfg, f) for f in n.get("fix") or []],
            "experiments": experiments.for_node(n),
            "sessions": node_sessions(cfg, sessions, n),
            "brief": next((str(b.relative_to(cfg.vault)) for b in [path.parent.parent / "briefs" / f"{n['id']}.md"]
                           if b.is_file()), None),
        }

    @app.get("/api/experiments")
    def api_experiments():
        out = []
        for e in experiments.all():
            p = public(e)
            p["launched"] = str(e.get("launched") or "")
            p["n_arms"] = len(e.get("arms") or [])
            p["n_nodes"] = len(e.get("nodes") or [])
            p["n_figures"] = sum(1 for a in e.get("arms") or [] if experiments.media_dir(e, a["run_id"]).is_dir())
            p["progress"] = progress(e)
            paths = exp_paths(e)
            p["tb"] = services.status(f"tb-{e['id']}")["running"]
            p["observatory"] = bool(paths) and pathlib.Path(cfg.local(paths["bundle"]), "manifest.json").exists()
            out.append(p)
        return sorted(out, key=lambda e: e["launched"] or "", reverse=True)

    # ---- services per experiment -------------------------------------------------------
    @app.get("/api/services")
    def api_services():
        return {"mode": "ssh:" + cfg.ssh_host if cfg.ssh_host else "local", "items": services.all()}

    @app.get("/api/experiment/{ident}/services")
    def api_exp_services(ident: str):
        e = experiments.get(ident)
        if not e:
            raise HTTPException(404, ident)
        paths = exp_paths(e)
        tb = services.status(f"tb-{e['id']}")
        obs = services.status(f"obs-{e['id']}")
        o = cfg.observatory
        built = bool(paths) and pathlib.Path(cfg.local(paths["bundle"]), "manifest.json").exists()
        runs_exist = bool(paths) and pathlib.Path(cfg.local(paths["runs"])).is_dir()
        build_env = {"SWEEP_DIR": paths["runs"], "SPEC": o.get("spec", ""), "BUNDLE_DIR": paths["bundle"], "DASHBOARD_MODE": o.get("mode", "dagger"),
                     "QUEUE": o.get("queue", "gpu_h100"), "WALLTIME": o.get("walltime", "12:00")} if paths else {}
        return {"mode": "ssh:" + cfg.ssh_host if cfg.ssh_host else "local", "paths": paths, "runs_exist": runs_exist, "progress": progress(e),
                "tensorboard": tb | {"available": runs_exist, "logdir": paths["runs"] if paths else None},
                "observatory": obs | {"built": built, "bundle": paths["bundle"] if paths else None, "build_env": build_env,
                                      "script": o.get("script"), "build_job": experiments._obs_jobs.get(e["id"])}}

    @app.post("/api/experiment/{ident}/tensorboard")
    def api_tb_start(ident: str):
        e = experiments.get(ident)
        paths = e and exp_paths(e)
        if not paths:
            raise HTTPException(404, "experiment has no experiment_dir / repo root")
        return services.start(f"tb-{e['id']}", f"{shlex.quote(cfg.tensorboard)} --logdir {shlex.quote(paths['runs'])} --host 127.0.0.1 --port {{port}} --reload_multifile true", cwd=paths["root"])

    @app.delete("/api/experiment/{ident}/tensorboard")
    def api_tb_stop(ident: str):
        return services.stop(f"tb-{ident}")

    class ObsBuild(BaseModel):
        env: dict[str, str] = {}

    @app.post("/api/experiment/{ident}/observatory/build")
    def api_obs_build(ident: str, req: ObsBuild):
        """Submit the observatory build (an LSF GPU job) with the env the user confirmed in the UI."""
        e = experiments.get(ident)
        paths = e and exp_paths(e)
        if not paths:
            raise HTTPException(404, "experiment has no experiment_dir / repo root")
        root = cfg.repo_roots.get(cfg.default_repo)
        r = services.run_once(f"bash {shlex.quote(cfg.observatory.get('script', 'dashboard/launch_dashboard_from_checkpoints.sh'))} build", cwd=root, env=req.env)
        m = re.search(r"Job <(\d+)>", r["output"])
        if m:
            experiments._obs_jobs[e["id"]] = {"job": int(m.group(1)), "submitted": dt.datetime.now().isoformat(timespec="seconds")}
        return r | {"job": int(m.group(1)) if m else None}

    @app.post("/api/experiment/{ident}/observatory/serve")
    def api_obs_serve(ident: str):
        e = experiments.get(ident)
        paths = e and exp_paths(e)
        if not paths:
            raise HTTPException(404, "experiment has no experiment_dir / repo root")
        if not pathlib.Path(cfg.local(paths["bundle"]), "manifest.json").exists():
            raise HTTPException(409, "no built bundle (manifest.json missing)")
        root = cfg.repo_roots.get(cfg.default_repo)
        return services.start(f"obs-{e['id']}", f"bash {shlex.quote(cfg.observatory.get('script', 'dashboard/launch_dashboard_from_checkpoints.sh'))} serve",
                              cwd=root, env={"BUNDLE_DIR": paths["bundle"], "HOST": "127.0.0.1"} | {"PORT": "{port}"}, daemonizes=True)

    @app.delete("/api/experiment/{ident}/observatory/serve")
    def api_obs_stop(ident: str):
        return services.stop(f"obs-{ident}")

    # ---- planning a run ---------------------------------------------------------------
    class Plan(BaseModel):
        id: str
        title: str
        kind: str = "dagger"
        previous: list[str] = []
        experiment_dir: str | None = None
        what_changed: str = ""
        next: str = ""
        nodes: list[str] = []

    @app.post("/api/experiments")
    def api_plan(req: Plan):
        """Create a planned experiment note via new.py, then fill the sections the form provided."""
        dirs = {str(e["_path"].parent) for e in experiments.all()}
        d = sorted(dirs)[0] if dirs else None
        if not d:
            for g in cfg.experiment_globs:
                hits = sorted(cfg.vault.glob(g))
                if hits:
                    d = str(hits[0])
        if not d:
            raise HTTPException(409, "no experiments folder found")
        cmd = [sys.executable, str(HERE / "new.py"), d, "experiment", "--id", req.id, "--title", req.title, "--kind", req.kind]
        for p in req.previous:
            cmd += ["--previous", p]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise HTTPException(400, (r.stderr or r.stdout).strip())
        path = pathlib.Path(r.stdout.strip())
        text = path.read_text(encoding="utf-8")
        if req.experiment_dir:
            text = text.replace("experiment_dir: null", f"experiment_dir: {json.dumps(req.experiment_dir)}", 1)
        if req.nodes:
            text = text.replace("nodes: []", "nodes: " + json.dumps([{"id": n, "role": "observed"} for n in req.nodes]), 1)
        for head, body in (("## What changed", req.what_changed), ("## Next run", req.next)):
            if body.strip():
                text = re.sub(rf"({re.escape(head)}\n)(.*?)(?=\n## |\Z)", lambda m: m.group(1) + body.strip() + "\n", text, count=1, flags=re.S)
        path.write_text(text, encoding="utf-8")
        experiments.invalidate()
        return {"id": path.stem, "path": str(path)}

    @app.get("/api/experiment/{ident}")
    def api_experiment(ident: str):
        e = experiments.get(ident)
        if not e:
            raise HTTPException(404, f"no experiment {ident}")
        path = e["_path"]
        body = re.sub(r"^\s*# .*\n", "", e["_body"].lstrip("\n"), count=1)
        ids = trees.all_ids()
        linked = []
        for l in e.get("nodes") or []:
            if isinstance(l, dict) and l.get("id") in ids:
                hit = trees.find(l["id"])
                if hit:
                    n = hit[2]
                    linked.append({"id": n["id"], "title": n["title"], "type": n["type"], "status": n["status"], "resolution": n.get("resolution"), "role": l.get("role")})
        prev = [{"id": p, "title": (experiments.get(p) or {}).get("title"), "exists": experiments.get(p) is not None} for p in e.get("previous") or []]
        nxt = [{"id": o["id"], "title": o["title"]} for o in experiments.all() if e["id"] in (o.get("previous") or [])]
        arms = []
        for a in e.get("arms") or []:
            files = experiments.run_files(e, a["run_id"])
            prov = files.get("provenance") or {}
            arms.append({**a, "media": experiments.media_dir(e, a["run_id"]).is_dir(),
                         "provenance": {k: {kk: v.get(kk) for kk in ("commit", "branch", "dirty")} for k, v in (prov.get("libraries") or {}).items()} if prov else None,
                         "bundle": (prov.get("bundle") or {}).get("path") if prov else None, "has_config": "config" in files})
        tokens = [e["id"], *[a["run_id"] for a in e.get("arms") or [] if a.get("run_id")]]
        if e.get("experiment_dir"):
            tokens.append(pathlib.Path(e["experiment_dir"]).name)
        return {"experiment": public(e) | {"launched": str(e.get("launched") or "")}, "path_remote": cfg.remote(path),
                "body_html": render.html(body, path.relative_to(cfg.vault)), "nodes": linked, "previous": prev, "next": nxt,
                "arms": arms, "gallery": experiments.gallery(e), "stage_notes": experiments.stage_notes(e),
                "tiers": [{"tier": i + 1, "name": tt.get("name"), "question": tt.get("question")} for i, tt in enumerate(cfg.figure_tiers)],
                "unassigned": sorted({f["card"] for f in experiments.gallery(e) if f["tier"] is None and f["level"] == "run"}),
                "repo_url": link_repo(cfg, e.get("repo"), path=e.get("experiment_dir")) if e.get("experiment_dir") else None,
                "sessions": sessions.query(tokens)}

    @app.get("/api/experiment/{ident}/diff")
    def api_experiment_diff(ident: str, vs: str, arm: str | None = None, vs_arm: str | None = None):
        """Flattened config.yaml differences between one arm of this experiment and one of `vs`."""
        e, o = experiments.get(ident), experiments.get(vs)
        if not e or not o:
            raise HTTPException(404, "experiment not found")
        pick = lambda ex, name: next((a for a in ex.get("arms") or [] if not name or a.get("name") == name), None)  # noqa: E731
        a, b = pick(e, arm), pick(o, vs_arm or arm)
        if not a or not b:
            raise HTTPException(404, "arm not found")
        ca, cb = experiments.run_files(e, a["run_id"]).get("config"), experiments.run_files(o, b["run_id"]).get("config")
        if ca is None or cb is None:
            return {"available": False, "reason": "config.yaml not mirrored for one of the runs (older layout)"}
        return {"available": True, "this": {"id": e["id"], "arm": a.get("name"), "run_id": a["run_id"]}, "vs": {"id": o["id"], "arm": b.get("name"), "run_id": b["run_id"]},
                "changes": json.loads(json.dumps(config_diff(cb, ca), default=str))}

    @app.get("/api/note")
    def api_note(name: str):
        rel = notes.resolve(name)
        if rel is None or rel.suffix.lower() != ".md":
            raise HTTPException(404, f"no note {name}")
        text = (cfg.vault / rel).read_text(encoding="utf-8", errors="replace")
        fm, body = {}, text
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            try:
                fm = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                fm = {}
            body = text[end + 4:]
        return {"path": str(rel), "title": rel.stem, "frontmatter": json.loads(json.dumps(fm, default=str)),
                "html": render.html(body, rel)}

    @app.get("/file/{path:path}")
    def file(path: str):
        target = (cfg.vault / path).resolve()
        if cfg.vault not in target.parents or not target.is_file():
            raise HTTPException(404, path)
        return FileResponse(target)

    @app.get("/api/sessions")
    def api_sessions(ids: str = Query(..., description="comma-separated ids/aliases")):
        return {"status": sessions.status(), "sessions": sessions.query(ids.split(","))}

    @app.get("/api/session")
    def api_session(path: str):
        p = pathlib.Path(path).resolve()
        if not any(root in p.parents for root in cfg.session_roots) or not p.is_file():
            raise HTTPException(404, path)
        meta = sessions.files.get(str(p)) or parse_session(p, cfg.session_roots)
        return {"meta": {k: v for k, v in meta.items() if k != "ids"} | commands(cfg, meta), "turns": transcript(p)}

    @app.post("/api/rescan")
    def api_rescan():
        threading.Thread(target=sessions.scan, daemon=True).start()
        return sessions.status()

    @app.get("/api/candidates/{prefix}")
    def api_candidates(prefix: str):
        d = trees.dirs().get(prefix)
        if d is None:
            raise HTTPException(404, prefix)
        return candidates(cfg, d.parent)

    class Promote(BaseModel):
        tree: str
        type: str = "problem"
        parent: str
        title: str
        aliases: list[str] = []
        discovered_from: str | None = None

    @app.post("/api/promote")
    def api_promote(req: Promote):
        d = trees.dirs().get(req.tree)
        if d is None:
            raise HTTPException(404, req.tree)
        cmd = [sys.executable, str(HERE / "new.py"), str(d), req.type, "--parent", req.parent, "--title", req.title]
        for a in req.aliases:
            cmd += ["--alias", a]
        if req.discovered_from:
            cmd += ["--discovered-from", req.discovered_from]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise HTTPException(400, (r.stderr or r.stdout).strip())
        path = pathlib.Path(r.stdout.strip())
        trees.invalidate()
        return {"id": path.stem, "path": str(path)}

    @app.get("/api/categories")
    def api_categories():
        return TAXONOMY

    class Categorize(BaseModel):
        prompt: str | None = None

    @app.post("/api/node/{ident}/categorize")
    def api_categorize(ident: str, req: Categorize):
        found = trees.find(ident)
        if not found:
            raise HTTPException(404, ident)
        _, _, n = found
        path = pathlib.Path(n["path"])
        text = path.read_text(encoding="utf-8")
        end = text.find("\n---", 4)
        body_md = text[end + 4:][:4000] if end >= 0 else ""
        taxonomy_desc = "\n".join(f"- {c['name']}: {c['description']}" for c in TAXONOMY)
        prompt = (f"Categorize this single problem-tree node into exactly ONE category.\n\n"
                  f"Existing taxonomy (prefer one of these unless the guidance below clearly calls for something else):\n{taxonomy_desc}\n\n"
                  f"Node id: {n['id']}\nNode title: {n['title']}\nNode body:\n{body_md}\n\n"
                  + (f"Additional guidance from the user: {req.prompt}\n\n" if req.prompt else "")
                  + "Reply with ONLY the category name on a single line, nothing else — no punctuation, no explanation.")
        claude_bin = shutil.which("claude") or str(pathlib.Path.home() / ".local/bin/claude")
        try:
            r = subprocess.run([claude_bin, "-p", prompt, "--model", "haiku", "--output-format", "text"],
                                capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "categorization timed out")
        if r.returncode:
            raise HTTPException(500, (r.stderr or r.stdout).strip()[:500])
        category = r.stdout.strip().splitlines()[0].strip().strip("\"'") if r.stdout.strip() else ""
        if not category:
            raise HTTPException(500, "empty category from model")
        set_frontmatter_field(path, "category", category)
        trees.invalidate()
        return {"id": n["id"], "category": category}

    return app


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(HERE / "config.yaml"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8891)
    args = ap.parse_args()
    cfg = Config(args.config)
    print(f"vault {cfg.vault}  trees {list(Trees(cfg).dirs())}  http://{args.host}:{args.port}/", flush=True)
    uvicorn.run(build_app(cfg), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
