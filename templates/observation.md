---
type: observation
id: {id}
title: {title}
parent: {parent}
aliases: {aliases}
discovered_from: {discovered_from}
status: noted               # noted | promoted | dismissed
opened: {date}
closed: null                # required for promoted / dismissed
before: []                  # required: the figure that shows it
promoted_to: null           # the problem or task that took it on, once promoted
revisit: ""                 # optional: the condition that would make it worth the time
sessions: []
source: agent
domain: neuroscience
tags: [{prefix}, observation]
---
# {id} — {title_plain}

## Observation
What was seen, where, with its numbers (each number's file in `before:`).

## Why not now
What resolving it would take, and why that is out of proportion to the questions in front of it.
