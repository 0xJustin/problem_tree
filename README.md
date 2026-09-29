# problem-tree

A tree-structured problem/task ledger, kept as plain Markdown notes with a spec-checked
schema, plus a read-only web cockpit to browse it. Built for teams where humans and coding
agents (pi, Claude Code, ...) work the same backlog side by side: every node is one file,
every session states which node it's on, and nothing is "the current status" except a
node's own state in the tree.

Originated as internal tooling for a connectome-modeling project; genericized here to run
against any Markdown vault. See `SPEC.md` for the full schema and design rationale (it still
uses that project as its worked example in places).

```
validate.py DIR [--tree]      invariants + tree print with rollups; exit 1 on errors (PyYAML only)
new.py DIR problem|task --parent ID --title "…" [--alias LEGACY-ID] [--discovered-from ID]
new.py DIR problem --root --prefix xyz --title "…"
new.py EXPDIR experiment --id NAME --title "…" [--kind ...] [--previous NAME]
templates/problem.md, templates/task.md, templates/experiment.md
serve.py, webui/, config.yaml   the cockpit (FastAPI, .venv)

cluster            cockpit.sh [start|stop|restart|status|logs]       (no arg = foreground)
Mac app            mac/install.sh · mac/launch.sh · mac/reload.sh · mac/stop.sh · mac/uninstall.sh
Mac ↔ cluster      mac/remote.sh [start|status|restart|stop]          set HOST to your login node
```

`DIR` is a project's `problems/` folder, e.g. `~/vault/02-Projects/my-project/problems`.

## Quick start

1. `cp config.example.yaml config.yaml` and edit `vault:`, `repos:`, `default_repo:` for your
   own notes vault and repositories.
2. `uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python fastapi "uvicorn[standard]" pyyaml markdown`
   (or `pip install -r requirements.txt` into any Python 3.10+ environment).
3. Create your first tree: `new.py <vault>/.../problems problem --root --prefix xyz --title "The thing you're trying to solve"`.
4. Run the cockpit: `./cockpit.sh` (foreground) or `./cockpit.sh start` (background), then open
   `http://127.0.0.1:8891`.

## Node model

Each node is one Markdown file with frontmatter: `parent:` (null for a root problem), a status
in `open → fix-proposed → fix-landed → verified → closed` (or `dropped`), and whether it's a
problem (circle) or task (square). Evidence images live under `media/problems/<id>/` by
relative path. `validate.py` checks the tree's invariants (every parent exists, no cycles, ids
match the pattern, evidence present where the schema requires it) and can print the whole tree
with status rollups. `new.py` is the only thing that should create a node — it mints the id,
writes the file from `templates/`, and wires `parent:`/`aliases:`/`discovered_from:` correctly.

## Cockpit

Read-only browser over every tree found by `config.yaml › tree_globs`. Two ways to run it:

**As a Mac app, code on a mounted remote.** In a Mac terminal, with the remote volume mounted:
`bash '/path/to/problem-tree/mac/install.sh'` (needs `MOUNT` and `REMOTE_HOME` set — see the
script's header). Installs a Python env + config on the Mac's own disk, a launchd agent that
starts at login, waits for the mount and restarts on exit, and `~/Applications/Problem Tree.app`
(Dock icon → `http://localhost:8891`). For an own-window app: Safari → File → *Add to Dock*. The
code stays on the mount, so edits there take effect on the next restart: `bash …/mac/restart.sh`
(kickstarts the agent, or bootstraps it if the install step failed, stopping any hand-started
server on the port first). The Mac config sets `path_map` so copied paths and agent
resume/fork commands come out in remote form, ready to paste into a remote shell. Remove with
`mac/uninstall.sh`. Log: `~/Library/Logs/problem-tree.log`.

**On the remote host itself, forwarded to a Mac.** `HOST=your.login.host bash …/mac/remote.sh`
starts `cockpit.sh -d` there if needed and holds a keep-alive tunnel to the same
`http://localhost:8891` (use `PORT=8890` if the Mac agent holds 8891). Faster first loads and
galleries if the vault is on local disk there; needs ssh/VPN up and a process on the login node.
Or just run `cockpit.sh -d` inside any remote session with its own port forwarding.

Every cache (trees, experiment notes, galleries, stage-note index, run files, wikilink index) is
stale-while-revalidate: a request always gets the last value at once and a background thread
refreshes it after its TTL (`tree_ttl`, `note_index_ttl`). Caches are warmed at startup, so the
first click is as fast as the tenth. The session index (for linking agent transcripts to nodes)
scans `session_roots` in the background, then incrementally by mtime, refreshed periodically or
via **rescan**.

- **Tree** (left): status dots (red open · orange fix-proposed · yellow fix-landed · green
  verified · grey closed; squares are tasks; a green ring = soft), rollup badge on interior
  nodes (`open / soft / collapse / clear`), filter box, *show complete* / *hide tasks* toggles.
  **Complete nodes (hard-verified, closed, done, dropped) are folded away by default**: a parent
  shows a small count of what is folded beneath it; when everything below is complete the ⊖
  handle becomes a green ✓ with the count — click it to reveal that branch, or *show complete*
  for all. Soft-verified nodes stay visible (they still carry a todo). Search reveals matching
  complete nodes.
- **Node**: breadcrumb, pills, before/after evidence side by side (images zoom on click; JSON/CSV
  tabulate; repo paths and commits link to GitHub per `config.yaml › repos`), fix links, rendered
  body (wikilinks resolve to notes or nodes; legacy aliases resolve too), children, and
  **sessions**: one row per agent chat the user started on this node (the first node id the user
  typed, directly or in a pasted brief path; *all mentions* widens it to every chat where the user
  typed the id), with copy resume/fork commands and a read-only transcript view.
- **Copy buttons**: image to clipboard, relative embed for notes in `problems/`, wiki-style embed
  for any other note, id, link, file path. Clipboard needs a localhost or https origin — hence
  the ssh tunnel; otherwise the button opens the file instead.
- **todos**: every leaf problem and task as a sortable table, incomplete rows first, complete rows
  dimmed below. An evidence column shows two squares, before and after: filled when present,
  hollow when missing.
- **ledger**: sortable table of all problems. **inbox**: bullets under a `## Candidates` section
  in the ledger note, each with a *promote* form (the cockpit's only write — it calls `new.py`);
  plus a create-by-hand form for tasks.
- **Theme**: plain, dashboard-neutral CSS out of the box; point it at your own project's
  stylesheet if you want the cockpit to read as one system with an existing eval dashboard.
- **Graph interaction**: drag a card to move it (its subtree comes along, edges follow);
  positions persist per tree in the browser; *reset layout* undoes them. Drag the background to
  pan, wheel to zoom, *fit* to refit. All hand-rolled SVG (`webui/graph.js`) — no graph library.
- **runs** (optional): if you configure `experiment_globs`, one row per experiment note → a run
  page with lineage, free-text sections, linked tree nodes, arms, a config diff vs. a previous
  run, and a figure gallery organized by `config.yaml › figure_tiers` — built for a validation-card
  pipeline that tags each figure by tier/stage/card, but the whole `experiments`/`figure_tiers`
  section is optional if you don't have one.
- **storyline**: the project's milestones for people — a calendar timeline (drag/wheel pans,
  ctrl/pinch zooms, ←/→ steps) or a date-ordered list of *story points*, each with a plain-language
  summary and one or two presentation-ready figures (problem → solution), zoomable and copyable at
  full resolution. Story points are `type: story` notes in `storyline/` beside `problems/`
  (SPEC §18), written by the `storyline` skill.
- `#/note/<name or path>` renders any vault note read-only (a Markdown reader with wikilink
  support, no Obsidian required).

## Agent skills

`skills/` holds the workflow skills that keep the tree current, in the `SKILL.md` format both pi
and Claude Code load:

- **wrap-up**: end-of-task bookkeeping — worklog, nodes current and validated, evidence filed,
  commits listed, scratch removed; may suggest a story point.
- **brief**: writes a self-contained prompt for a child node, for a fresh session to pick up.
- **storyline**: proposes and, after the user approves the figures, writes a story point.

They find project locations (the `problems/` folder, worklog, scratch folder, required note
frontmatter) through the project's `AGENTS.md`. Install by linking each into the harness's skill
folder:

```
for s in wrap-up brief storyline; do
  ln -s "$PWD/skills/$s" ~/.pi/agent/skills/$s
  ln -s "$PWD/skills/$s" ~/.claude/skills/$s
done
```

## What to adapt for your own project

- `config.yaml` — your vault path, repo links, and (optional) figure-tier scheme.
- `webui/index.html`'s experiment-arms table has a couple of column labels (library names) left
  over from the origin project's own multi-repo layout; harmless if you don't use the `runs`
  view, worth a look if you do.
- The `mac/` scripts need `MOUNT`/`REMOTE_HOME` (and optionally `SSH_HOST`) for your own remote
  host and mount point — see each script's header comment.

## Setup

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python fastapi "uvicorn[standard]" pyyaml markdown
```
or `pip install -r requirements.txt`.
