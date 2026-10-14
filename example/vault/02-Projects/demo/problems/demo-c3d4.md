---
type: problem
id: demo-c3d4
title: Runtime grew fourfold after the filter change
parent: demo-root
aliases: []
discovered_from: null
status: fix-landed
assignee: agent
category: 'Data & loading'
opened: 2026-09-12
closed: null
resolution: soft
instrument: "wall-clock minutes per stage, recording 3"
before:
  - artifact: ../media/problems/demo-c3d4/before.png
after:
  - artifact: ../media/problems/demo-c3d4/after.png
fix:
  - pr: pipeline#212
todo: "profile the first load"
source: human
tags: [demo, problem]
---
# demo-c3d4 — Runtime grew fourfold after the filter change

## Problem
Loading dominates: 41 minutes against 12 before the change.

## Fix
Cache the decoded recording between stages.

## Follow-up
The cache fixes reruns; the first load is still slow. Profile the loader.
