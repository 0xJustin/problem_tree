---
type: problem
id: demo-a1b2
title: The same recording gives a different cluster count on every rerun
parent: demo-root
aliases: []
discovered_from: null
status: verified
assignee: agent
category: 'Statistics'
opened: 2026-09-03
closed: 2026-09-10
resolution: hard
instrument: "cluster count over 20 reruns of recording 3"
before:
  - artifact: ../media/problems/demo-a1b2/before.png
after:
  - artifact: ../media/problems/demo-a1b2/after.png
fix:
  - commit: pipeline@4f2a9c1
todo: ""
source: human
tags: [demo, problem]
---
# demo-a1b2 — The same recording gives a different cluster count on every rerun

## Problem
Twenty reruns of one recording found between 11 and 18 clusters.

## Fix
Seed every random number generator from the run config.

## Evidence the fix worked (after)
Twenty reruns now find 14 clusters each time.
