---
type: task
id: demo-i9j0
title: Log library versions with every run
parent: demo-e5f6
aliases: []
discovered_from: null
status: done
assignee: agent
category: 'Infrastructure'
opened: 2026-09-16
closed: 2026-09-19
before: []
after:
  - commit: pipeline@9be1d70
fix: []
source: human
tags: [demo, task]
---
# demo-i9j0 — Log library versions with every run

## What
Write numpy, scipy and the BLAS build into the run's config file.

## Outcome
- Done: every run directory has a versions.txt.
- Proof: commit pipeline@9be1d70, test_versions passes.
- Not verified: runs started before this commit.
