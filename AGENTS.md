# AGENTS.md

Operating notes for agents that use or change problem-tree. The README is the overview, `SPEC.md` is the
schema and its reasoning. This file holds what you need to run the tool and to work in it.

## Commands

```
python validate.py DIR [--tree]       invariants and a tree print with rollups; exit 1 on errors (PyYAML only)
python new.py DIR problem|task|observation --parent ID --title "…" [--alias LEGACY-ID] [--discovered-from ID] [--assignee WHO]
python new.py DIR problem --root --prefix xyz --title "…"
python new.py EXPDIR experiment --id NAME --title "…" [--kind ...] [--previous NAME]
./cockpit.sh [start|stop|restart|status|logs]     the cockpit on this host; no argument runs in the foreground
```

`DIR` is a project's `problems/` folder. Run `validate.py --tree` before any check-in and report its warnings.
Create nodes only with `new.py`: it mints the id, writes the file from `templates/`, and sets `parent:`,
`aliases:` and `discovered_from:`.

## Setup

```
pip install -r requirements.txt            # Python 3.10+; or: uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.yaml config.yaml         # then edit vault:, repos:, default_repo:
```

`cockpit.sh` uses `.venv/bin/python` here. The config is found in this order: `--config`, the
`PROBLEM_TREE_CONFIG` environment variable, then `config.yaml` next to `serve.py`. A project can keep its
config inside its own vault and set the variable.

## Configuration (`config.yaml`, paths may use `~`)

| key | meaning |
|---|---|
| `vault` | root of the notes vault |
| `tree_globs` | folders searched for trees: any `*.md` with `parent: null` under a `problems/` folder |
| `session_roots` | agent transcript folders grepped for node ids; an empty list turns session linking off |
| `repos`, `default_repo` | repo name to web URL, for `pr:`, `commit:` and `repo:` entries |
| `categories` | optional `[{name, description, color}]` used to color nodes; a node's `category:` may be any string |
| `path_map` | rewrites copied paths and resume commands when the vault is read through a mount |
| `tree_ttl`, `note_index_ttl` | seconds before a cache refreshes |
| `experiment_globs`, `run_media`, `figure_tiers`, `stage_order`, `services` | optional run pages, figure organization and TensorBoard launching (SPEC §14–17) |

Every cache (trees, experiment notes, galleries, stage notes, run files, wikilink index) serves the last value
at once and refreshes in a background thread after its TTL. Caches are warmed at startup. The session index
scans `session_roots` in the background, then incrementally by modification time, or on **rescan**.

## The cockpit

Read-only except one write: promoting an inbox candidate calls `new.py`. Views, in tab order:

- **tree**: graph (hand-written SVG in `webui/graph.js`, no graph library) or list. Dots show status:
  red open, orange fix-proposed, yellow fix-landed, green verified, grey closed; squares are tasks, diamonds
  observations; a green ring is a soft resolution. Interior nodes carry a rollup badge
  (`open / soft / collapse / clear`). Complete nodes (hard-verified, closed, done, dropped) are folded away
  unless *show complete* is on; soft-verified nodes stay visible. Drag a card to move its subtree (positions
  persist per tree in the browser), drag the background to pan, wheel to zoom, *fit* to refit.
- **node page**: breadcrumb, before and after evidence (images zoom, JSON and CSV tabulate, repo paths and
  commits link per `repos`), rendered body (wikilinks resolve to notes, nodes and aliases), children, and
  **sessions**: one row per agent chat whose first typed node id is this node, with copy resume and fork
  commands and a transcript view. *All mentions* widens it to every chat that typed the id.
- **todos**: every leaf problem and task, incomplete first, with an evidence column (two squares: before,
  after; filled when present).
- **runs** (optional): one row per experiment note; a run page has lineage, arms, a config diff against a
  previous run, and a figure gallery ordered by `figure_tiers`.
- **ledger**: all problems. **inbox**: bullets under `## Candidates` in the ledger note, each with a
  *promote* form.
- **storyline**: timeline or list of story points (`type: story` notes in `storyline/` beside `problems/`;
  SPEC §18), written by the `storyline` skill.
- `#/note/<name or path>` renders any vault note read-only.

Copy buttons (image, embed, id, link, path) need a localhost or https origin, so reach a remote cockpit
through an ssh tunnel.

## Running somewhere else

**Cockpit on a login node, viewed on a Mac:** `HOST=your.login.host bash mac/remote.sh` starts
`cockpit.sh` there if needed and holds a tunnel to `http://localhost:8891` (`PORT=8890` if the Mac agent
below holds 8891).

**Always-on Mac app, code on a mounted volume:** `MOUNT=… REMOTE_HOME=… bash mac/install.sh` (optional
`SSH_HOST`; see the script header). It installs a Python environment and config on the Mac, a launchd agent
that starts at login and waits for the mount, and `~/Applications/Problem Tree.app`. Use `mac/restart.sh`
after code edits, `mac/reload.sh`, `mac/stop.sh`, `mac/uninstall.sh`. The Mac config sets `path_map` so
copied commands paste into a remote shell. Log: `~/Library/Logs/problem-tree.log`.

## Skills

`skills/` holds `wrap-up`, `brief` and `storyline` in the `SKILL.md` format pi and Claude Code both load. They
find the project's `problems/` folder, worklog, scratch folder and required frontmatter through the
project's own `AGENTS.md`, so that file must name them. Install by linking each into a harness's skill
folder:

```
for s in wrap-up brief storyline; do
  ln -s "$PWD/skills/$s" ~/.pi/agent/skills/$s
  ln -s "$PWD/skills/$s" ~/.claude/skills/$s
done
```

## Working the tree

- Say which node you are working on. Open tasks freely under it; do not open problems unasked. List
  candidates and let the user promote one.
- A problem needs `before` evidence once it moves past `open`, and `after` evidence plus `instrument` to be
  `verified`. A task needs `after` to be `done`. Evidence paths are relative to the note and must exist.
- Children never close a parent; only the user sets an interior problem `verified`. `done` and `verified`
  need the user's go-ahead unless the project's `AGENTS.md` says otherwise.
- An observation is an issue deliberately parked; propose one in your reply and open it on the user's go-ahead.
- The tree is the only task list: no checkboxes or `#task` lines in other notes (`validate.py` warns).
- The full invariants are SPEC §6; the node shapes are SPEC §4–5.

## Changing the tool

- Keep it project-neutral. Project names, repo names, paths and taxonomies belong in the config, not in
  `serve.py`, `webui/` or `SPEC.md`. Read them from `Config` (`cfg.default_repo`, `cfg.categories`, …).
- A new frontmatter field or invariant goes in `SPEC.md`, `validate.py`, the matching template and, if it
  shows in the cockpit, `serve.py` and `webui/`.
- Check a change against the toy project, never against someone's real tree:
  `python validate.py example/vault/02-Projects/demo/problems --tree`, then run the cockpit with
  `PROBLEM_TREE_CONFIG=example/config.yaml python serve.py --port 8895`.
- `example/make_example.py` rebuilds the toy project; `example/screenshots.py` rebuilds `docs/img/` from a
  running example cockpit (needs `playwright`). Rebuild the images when the UI changes visibly.
- Write American spelling in prose and code.
