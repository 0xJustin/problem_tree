# Problem tree — spec

Status: draft, decisions 1–5 settled with the user 2026-09-21. Step 1 (schema, templates,
validator) and step 2 (migration of P-01…P-14, five interior subsystem nodes, doc updates)
done 2026-09-21; cockpit (§10) delivered 2026-09-21 as `~/brain/.claude/tools/problem-tree/serve.py` + `webui/index.html` (FastAPI, uv venv on Python 3.13, `cockpit.sh` launcher); Mac always-on install via `mac/install.sh` (launchd agent + Dock app, `path_map` for cluster-form paths). Graph view and experiments (§14) added 2026-09-21. Pre-migration copy:
`agent_project_information/archive/2026-09-21_connectome_simulation_vault_pre-problem-tree.tar.gz`.

## 1. Purpose

Work on this project is a tree: one base problem (infer neural activity from behaviour),
subproblems found on the way down, collapsed back up as they resolve, with new problems
discovered on the way back. Each node needs (a) evidence the problem exists, with
provenance, (b) the work that addressed it, (c) evidence it was addressed, and (d) a way
back to the agent conversation that did the work.

The existing `Problem Ledger` (`P-nn` notes) already carries a–c for the ~15 model-level
problems. What is missing: the tree (nodes are flat), technical sub-issues (excluded from
the ledger, so lost), session linkage (none), robust evidence links (absolute vault
wikilinks into a gitignored symlinked folder), and a frontend that works over the network
volume (Obsidian on SMB is slow and cannot index the symlinked `media/`).

This spec keeps the markdown backend in the vault and adds: two node types in one tree,
hash IDs, structured evidence fields, relative artifact paths, inferred session links, a
validator, and a read-only web cockpit served from the cluster.

## 2. Prior art and what is borrowed

| tool | borrowed | not borrowed |
|---|---|---|
| [crux](https://github.com/mehdiforoozandeh/crux) — question→hypothesis→evidence tree in Obsidian-compatible md, stdlib Python engine, read-only `serve` cockpit | tree-as-flat-files with `parent:`; pre-registered instrument; derived (not asserted) verdicts; PI-gated close; read-only cockpit with rendered report beside the tree; "engine never judges" | its q/h/s vocabulary (would replace the working ledger); engine (8k lines, autopilot, wiki) |
| [beads](https://github.com/steveyegge/beads) / [nd](https://github.com/paivot-ai/nd) | `PREFIX-HASH` ids (4 base36 chars); `discovered_from` edge; epic rollup; append-only history idea | Dolt/SQLite store; claiming; sync branch |
| [Backlog.md](https://github.com/MrLesk/Backlog.md) | spec → plan → code review checkpoints as the reason nodes stay small | kanban model |
| [notes-web](https://github.com/arkan/notes-web), cc-session-browser family | serve markdown from where the files are local, view in a browser over the wire; read-only JSONL transcript rendering | — |
| [agentic-experiments](https://github.com/kadenmc/agentic-experiments), [figtracer](https://github.com/david-priest/figtracer) | evidence tied to commit; figure↔note provenance | hooks that refuse work |

## 3. Layout on disk

One tree per project, one `problems/` folder per project root, flat (the tree is in
frontmatter, not folders):

```
~/brain/02-Projects/connectome_simulation/
  problems/                      all nodes of the tree, one file per node, <id>.md
    cbe-root.md                  the base problem; parent: null
    cbe-k7q2.md                  a problem
    cbe-3m0x.md                  a task
  media/problems/<id>/           evidence files (gitignored; volume is backed up)
  connectome_body_eval/          aspect folders stay as they are (runs/, cards/, decisions/, notes/)
```

Evidence is referenced **relative to the note**: `../media/problems/cbe-k7q2/before.png`.
Never `![[absolute vault path]]`. Relative paths survive the Mac mount, the cluster path,
git, Obsidian and any renderer. Evidence is a copy of the figure/data, not a symlink, and
is treated as immutable once the row is `verified`. Large run outputs stay where the
exporter puts them (`<aspect>/media/`); only the specific before/after files are copied.

## 4. Node types

Two types, one file shape, one tree. Anything may be a child of anything.

**`problem`** — the ledger-grade node (unchanged admission test: visible in a card / run
outcome / measurement; fixed by a decision later runs inherit; before and after measured
with the same instrument). Agents do not open problems unasked; they list candidates and
the user promotes. The root and aspect-level nodes are problems too; they are allowed to
have no evidence of their own while they have children (their evidence is the collapse of
their children — but they may only be set `verified` by hand, with their own `after` at
their own `instrument`; children never auto-close a parent).

**`task`** — everything else met on the way: code bugs, OOMs, paths, plotting, refactors,
PR mechanics, dead ends. No evidence requirement. Agents open tasks freely under the node
they were working in. This is where the technical debris of a problem becomes visible
again when you return to the node.

## 5. Frontmatter

Common to both types:

```yaml
type: problem | task
id: cbe-k7q2                # <prefix>-<4 base36 chars>; minted by new.py; filename == id
title: "one sentence"
parent: cbe-root            # id of the parent; null only on the root
aliases: []                 # previous ids (P-13); wikilinks and session greps resolve through these
discovered_from: null       # id of the node whose work surfaced this one (beads semantics)
status: …                   # per type, below
opened: YYYY-MM-DD
closed: null                # date; required for verified/closed/done/dropped
sessions: []                # optional manual override, see §8: [{harness: pi|claude, ref: <path|uuid>}]
source: agent | human
domain: neuroscience
tags: [cbe, problem|task]
```

`problem` adds:

```yaml
status: open | fix-proposed | fix-landed | verified | closed
resolution: null | soft | hard     # soft = ok for now, todo left; hard = verified, nothing left
instrument: "DNg100 card, 12 seeds, per-leg P(rhythmic)"   # the measurement both evidences use
before:                            # evidence the problem exists; ≥1 for any status past open
  - artifact: ../media/problems/cbe-k7q2/before_dng100_12seeds.png
    data: experiments/2026-09-21_symmetrize-phase0/before_dng100_12seeds.json   # repo-relative
    repo: connectome_body_eval
    commit: 312d237
    branch: run-v4
    job: 154274084
    note: "nosym 0.52 ± 0.21; counts-only 0.56 ± 0.16"
after: []                          # same shape; ≥1 required for verified
fix:                               # lazy links, rendered as URLs by the cockpit
  - pr: synaptix#181
  - commit: synaptix@d8a91c1
  - config: symmetrize.gate=reconstruction
todo: ""                           # required when resolution: soft
```

`task` adds:

```yaml
status: open | done | dropped
assignee: null                     # justin | agent | pi:<session> | claude:<session> (all node types)
before: []                         # optional: why the task is worth doing; same entry shape as a problem's
after: []                          # required for done (from 2026-09-24): commit, test, job or artifact
artifact: null                     # legacy single relative path; counts as after-evidence in the cockpit
fix: []                            # optional, same shape as problem.fix
```

Body sections (human-readable; the frontmatter is the machine index):
problem — `## Problem`, `## Fix`, `## Evidence the fix worked (after)`, `## Follow-up`;
task — `## What`, `## Summary` (plain-language: why we looked, what we found, what it means for the parent, what is open; on any node with real work), `## Outcome` (three lines: Done / Proof / Not verified). Numbers in the body must have a file in `before:`/`after:`.

## 6. Invariants (enforced by `validate.py`)

Errors (exit 1):
- ids unique; aliases unique and disjoint from ids; filename stem == id
- exactly one root (`parent: null`); every `parent` and `discovered_from` resolves; no cycles
- `type` ∈ {problem, task}; `status` in the type's vocabulary; `title` non-empty
- every `before[].artifact`, `after[].artifact`, `artifact` path exists on disk
- problem: `fix-proposed|fix-landed|verified` ⇒ `before` and `fix` non-empty;
  `verified` ⇒ `after` non-empty and `instrument` set; `verified|closed` ⇒ `closed` date;
  `resolution` only when status ∈ {fix-landed, verified, closed}; `hard` ⇒ `verified`;
  `soft` ⇒ `todo` non-empty
- task: `done|dropped` ⇒ `closed` date; `done` ⇒ `after` non-empty unless `closed` < 2026-09-24
  (`STANDARD_SINCE` in validate.py; older tasks predate the evidence standard)

Warnings:
- a leaf `problem` with empty `before` (a candidate, not a row)
- `verified` without `resolution`; `todo` set but resolution not `soft`
- a `verified` node with an unresolved descendant
- `assignee` outside justin | agent | pi:<session> | claude:<session>
- a checkbox or `#task` line in any note beside `problems/` (the tree is the only task list)

Rollup (computed, never stored) over descendants: `open` = *leaf* problems in
{open, fix-proposed, fix-landed}; `soft` = problems with `resolution: soft`;
`tasks` = open tasks; `collapse` = *interior* problems still unresolved whose own subtree
is clear (nothing left below; awaiting the user's verdict). Label: `open` if any open; else
`soft` if any soft or open task; else `collapse` if any; else `clear`. Interior nodes
always show their label in the tree and the cockpit; leaves show nothing.

## 7. IDs and aliases

`<prefix>-<4 base36 chars of sha256(title + timestamp)>`, prefix per project (`cbe`),
root id fixed as `<prefix>-root`. Minted by `new.py`, collision-checked against ids and
aliases. Existing `P-01…P-14` are migrated to hash ids with `aliases: [P-nn]` so current
`[[P-nn]]` wikilinks and old session mentions still resolve.

## 8. Session linkage — inferred, not recorded

The cockpit lists, for each node, every agent session whose transcript mentions the node's
id or any alias, by scanning `~/.pi/agent/sessions/**/*.jsonl` and
`~/.claude/projects/**/*.jsonl` (both are plain JSONL keyed by cwd). No hooks, no agent
discipline, retroactive over existing sessions. Each hit shows harness, date, first user
message, and copyable `pi --session <path>` / `pi --fork <path>` / `claude --resume <uuid>`
commands, plus a read-only transcript view. The `sessions:` frontmatter list is a manual
override for a session that should be attached but never typed the id.

## 9. Tooling (step 1, delivered)

`~/brain/.claude/tools/problem-tree/`
- `validate.py DIR [--tree]` — invariants of §6, tree print with rollup. PyYAML required.
- `new.py DIR problem|task --parent ID --title "…" [--alias P-nn] [--discovered-from ID]`
  and `new.py DIR problem --root --prefix cbe --title "…"` — mints an id, writes the file
  from a template, prints the path.
- `templates/problem.md`, `templates/task.md`.

## 10. Cockpit (step 3, planned)

FastAPI server (`serve.py` + `webui/index.html`). Runs either on the cluster (vault local,
viewed through a tunnel) or as an always-on Mac app reading the mount (`mac/install.sh`:
launchd agent, Dock icon, `path_map` so copied paths/commands are in cluster form). Read-only
except one action. Re-parses frontmatter per request; optional watcher for live refresh.

Views: (1) tree, status-coloured, rollup badges, filter by tag; (2) node — title,
instrument, before/after artifacts side by side (image or tabulated JSON/CSV), fix links
as URLs, rendered body, children, `discovered_from` backlink; (3) sessions strip per node
(§8); (4) copy-figure and copy-embed (relative-path markdown) buttons; (5) ledger table
(replaces the Dataview query); (6) candidates inbox parsed from the ledger note, with
"promote" — the only write, calls `new.py`.

## 11. Agent rules

Not kept here: how agents work the tree is `~/song_workspace/AGENTS.md` › *The problem board*; a
problem's lifecycle (admission, promotion, routine) is `connectome_body_eval/Problem Ledger.md`. The
invariants those rules rely on are §6.

## 12. Migration (step 2, pending permission — moves and renames)

1. Create `02-Projects/connectome_simulation/connectome_body_eval/problems/` with `cbe-root` and one problem per
   aspect (`connectome_body_eval` today).
2. For each `connectome_body_eval/problems/P-nn.md`: mint id, move, add `aliases: [P-nn]`,
   `parent`, `resolution`, structured `before`/`after`/`fix` from the existing prose and
   `media/problems/P-nn/` files; rewrite `![[…]]` to relative paths. Move
   `connectome_body_eval/media/problems/` → `media/problems/` (gitignored both sides).
3. Point `Problem Ledger.md` index at the new ids; leave its rules text; its Dataview
   table gets a `FROM` update.
4. Vault `.gitignore`: add `02-Projects/connectome_simulation/media` (the current pattern
   `**/media` already matches; confirm). Vault `CLAUDE.md` folder contract: one row for
   `problems/` and `.claude/tools/`.
5. Run `validate.py --tree`; review the tree that falls out against how the work is
   actually thought about before building the cockpit.

## 13. Open items

- Whether `Run Ledger` rows and `decisions/` notes should become tree nodes or stay as
  linked notes (lean: stay; link from `fix:`/body).
- Whether the worklog line format gains an optional `[id]` token for `closeout`.

## 14. Experiments (model runs) — added 2026-09-21

One note per experiment or sweep (the unit a decision is made on), in
`<aspect>/experiments/<name>.md`, `type: experiment`, id = the common name (not hashed).
Migrated from the two `Run Ledger` tables by `migrate_run_ledger.py` (22 rows → 21 notes,
`latentode-grid` merged; original table kept as `old_Run_Ledger.md` here).

Frontmatter: `kind` dagger|expert|grid|init-study · `status` planned|running|done|superseded ·
`launched` · `repo`, `experiment_dir` (repo-relative) · `previous: [..]` (one or more; lineage,
and the reference for "what changed") · `arms: [{name, run_id, job}]` (sweeps have several; a
single run has one) · `changes: [{key, from, to, why, node}]` salient config deltas ·
`nodes: [{id, role}]` with role before|after|observed|spawned linking tree nodes · `figures:`
extra figure folders relative to the note · `notes:`, `sessions:`, `outbox`/`jobs` optional.
Body, fixed headings: **What changed**, **Observations**, **Remaining issues**, **Next run**.

Figures are not listed in the note: the cockpit walks `../media/single/<run_id>/<stage>/*.png`
for each arm (plus `figures:`), reads the exporter-mirrored `results.jsonl` beside them for
PASS/FAIL/MIXED badges and values, `provenance.yaml` for commits, `config.yaml` for a flattened
diff against `previous` (`GET /api/experiment/{id}/diff?vs=&arm=`). Node ↔ experiment links
are the union of the note's `nodes:` and what the tree's `before/after` entries imply (`run`,
`job`, `copied_from`). Session linkage: run ids and experiment folder names are grep tokens.

Cockpit: **runs** table (sortable) → run page: lineage strip, the four sections, linked tree
nodes, arms table (run id, job, commits per library with dirty marker, bundle, stage-note
links), config diff vs a chosen `previous` and arm, figure gallery (filter by arm / stage /
verdict / card name; **compare arms** = one row per card, one column per arm at a chosen
stage; copy image / `![[vault path]]` / path), sessions. Node pages get a **runs** box.

Rejected (user, 2026-09-21): *promote to evidence* from the UI — too much mechanism;
evidence attachment stays with the agent/editor. Deferred: a `lineage` graph view; orphan
figure folders (`media/dn_rhythmicity*`, `rigging_2026-09-11`) with no experiment note.

## 16. Figure tiers (user scheme, 2026-09-21)

Run galleries are ordered by five questions, encoded in the cockpit's `config.yaml › figure_tiers`
(not in code): **1 training** — did the run learn? (`training/*`, `training_curves*`) ·
**2 rigging** — are inputs and outputs wired through? (`R.*`, `health_stimulus`, `health_motor_path`,
`rigging_*`) · **3 biophysics & health** — is the connectome in a physiological regime?
(`activity/*` and `*_activity` first, then `E.*`, `health_voltage*`, `health_episode*`) ·
**4 sensory organs** — do the sensors behave like the literature? (`G.*`, `J.*`, `N.*`, `T.*`) ·
**5 circuit & behaviour** — does the circuit do what the papers say? (`D.*`, `H.*`, `I.*`, clamp
`A.* B.* C.* K.* M.*`, gait `S.*`, discriminators `X.*`, `video/*` last). Within a tier: pattern order,
then `stage_order` (init → checkpoint → final → health → health_nokill → nokill), then card; an
aggregate precedes its `*_examples/` instances, which are folded by default. Top-level files in `figures:` folders are aggregations across arms and sit above the tiers ("across arms");
subfolders there are arms. Per-run figures no pattern claims are shown under "other" — acceptable for
one-off experiments; a recurring family gets a pattern, never a server-side guess.

## 17. Runs as a control surface (2026-09-22)

The run page launches the two tools a run is read with: **TensorBoard** over the experiment's `runs/`
and the **Observatory** (the connectome eval dashboard: `dashboard/launch_dashboard_from_checkpoints.sh`
build = LSF GPU job over the sweep with a spec, serve = a web server over the bundle). Services run
where the cluster filesystem is native — locally when the cockpit is on the cluster, via
`ssh services.ssh_host` plus an automatic `ssh -L` forward when on the Mac — on ports from
`services.port_pool`, and open in a new tab. A build shows its full environment for confirmation
first (it costs a GPU). Planned runs are `status: planned` experiment notes created from the runs
table (`POST /api/experiments` → `new.py` + the What changed / Next run sections); progress
(init · checkpoint · final · training · video) is derived from figures on disk, not stored. The
cockpit's theme is the dashboard's stylesheet (`dashboard/static/styles.css` tokens); graph nodes
can be dragged (subtree follows, positions persist in the browser).

## 15. Design principle (user, 2026-09-21)

The UI speaks through design, not annotation. Colour, shape and position carry state
(status border, verdict dot, dashed = soft); words are for titles and content. Metadata and
actions appear on hover, not by default; counts are quiet numbers, not labels; no
instructional text in the interface. Prefer removing an element to explaining it.
