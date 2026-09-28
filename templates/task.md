---
type: task
id: {id}
title: {title}
parent: {parent}
aliases: {aliases}
discovered_from: {discovered_from}
status: open
assignee: {assignee}
opened: {date}
closed: null
before: []                  # optional: why the task is worth doing
after: []                   # required for done: commit, test, job or artifact
fix: []
sessions: []
source: agent
domain: neuroscience
tags: [{prefix}, task]
---
# {id} — {title_plain}

## What
What went wrong or what needs doing, and where it showed up (job id, path, error).

## Outcome
- Done: what became true (or why dropped).
- Proof: what ran or was observed; the entries in `after:`.
- Not verified: what was not checked, or "none".
