---
name: storyline
description: Propose and write a story point — a milestone in the project's storyline, with one or two presentation-ready figures and a plain-language summary. Use when the user asks for a story point, says "add this to the storyline", or approves one suggested at wrap-up. Never draft one unasked.
---

# Storyline

The storyline is the project's readable history: the milestones, each shown by clean figures and a
short summary, for the user's own reference and for presentations. The task tree (the
`problems/` folder named in the project's AGENTS.md) holds the detailed record; a story point points
into it and replaces none of it. Same scope as the tree.

Story points live in the `storyline/` folder beside `problems/`, one note per point, figures in
`media/storyline/<slug>/` (committed, binaries via LFS). The slug is the note's file stem,
`<YYYY-MM-DD>_<short-kebab-name>`, used unchanged for the media folder and in `answers:`.

## The bar

A story point is a result worth other people's time, not proof of effort. Only a minority of tasks
qualify.

- **In:** training a model and deciding something from its output; a major problem exposed by
  analysis; a code bug whose fix other people on the team should see (it changes how they read
  results or use the code); an overview figure of where the project stands.
- **Out:** reorganizing, renaming, tooling; syntactic or local bug fixes; fixing a problem another
  task created; anything whose main message is "we did the work".

## Flow — three stops for the user

1. **Suggest** (only at wrap-up, or when asked whether something qualifies). One line in the
   wrap-up report: `Story point? <node id> (<title>): <the finding, one sentence>`, and which bar
   item it meets. Do not draft anything. Say nothing when the session's work is below the bar.
2. **Propose** (after the user asks or approves the suggestion). Reply with:
   - a title that states the finding ("The decoder, not the connectome, limits walking speed"),
   - the summary draft (below),
   - the figure plan: usually two figures, one showing the problem and one showing the solution,
     or one overview figure. For each, point to an existing figure (its path) if it already
     meets the figure rules below (most evidence figures carry internal ids and need a redraw),
     otherwise describe what a new one plots (data source, axes, comparison) and ask for guidance.
     Render new or redrawn figures to the project's scratch folder (AGENTS.md),
     under `storyline/<slug>/`, and show them to the user; don't file them yet.
   Iterate until the user approves the figures.
3. **Write** (on the user's approval of the figures). Copy or render the figures into
   `media/storyline/<slug>/`, write the note, delete the scratch copies, and reply with the
   note's path. Nodes are not edited; the story point's `nodes:` list is the link. Committing
   follows the project's git rules (at wrap-up, or when asked).

## Summary

Three to five sentences a colleague in the lab who knows the project but not this week's work can
read in 30 seconds: what we were trying to find out, what we did, what we saw, what it changed.
No run ids, node ids, code identifiers or abbreviations coined inside the project; translate
project shorthand into terms common in the field. Every number
in it appears in one of the figures.

## Figures — presentation-ready

The user drops these into their own slides unchanged. When the user picks existing figures, use them
unchanged; these rules apply only to figures the agent proposes or redraws.

- One message per figure; the title states the message, not the plotted variables.
- Plain axis labels with units; no internal ids, run ids or file paths in the figure.
- Legible at slide size: 16:9 or 4:3 canvas, fonts at least 14 pt at 10 in width, few panels
  (at most four).
- Colorblind-safe palette; the same color for the same thing across a story point's figures
  (e.g. before gray, after the accent color).
- Save PNG at 200 dpi and a vector copy (PDF or SVG) with the same stem.
- A redrawn figure keeps its script next to it (`media/storyline/<slug>/make_<stem>.py`) or names
  the repo script and commit that made it, so it can be regenerated.

## The note

`storyline/<slug>.md`, the slug's date being when the result landed (not when it was written up).
The cockpit's storyline tab shows it on the timeline; the summary is the prose between the H1 and
the first figure. Add any frontmatter fields the project's notes require (AGENTS.md).

```markdown
---
type: story
source: agent
date: YYYY-MM-DD
title: <the finding, as a sentence>
kind: decision | problem-exposed | fix | overview
nodes: [<node ids this story point draws on>]
experiments: [<experiment ids, if any>]
answers: <slug of an earlier story point this one resolves, if any>
figures:
  - {path: ../media/storyline/<slug>/<stem>.png, role: problem | solution | overview, caption: "<one line>"}
---
# <title>

<summary>

![](../media/storyline/<slug>/<stem>.png)
*<caption>*

## Where it came from
- [[<node id>]] — <node title>
```
