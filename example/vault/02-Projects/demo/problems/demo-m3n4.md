---
type: problem
id: demo-m3n4
title: Figure 3 cannot be regenerated from the raw data
parent: demo-root
aliases: []
discovered_from: null
status: fix-proposed
assignee: agent
category: 'Statistics'
opened: 2026-09-14
closed: null
resolution: null
instrument: "figure 3 regenerated from raw files"
before:
  - artifact: ../media/problems/demo-m3n4/before.png
after: []
fix:
  - pr: pipeline#218
todo: ""
source: human
tags: [demo, problem]
---
# demo-m3n4 — Figure 3 cannot be regenerated from the raw data

## Problem
Two panels depend on a notebook that was edited by hand.

## Fix
Move the panel code into a script that reads only the raw files.
