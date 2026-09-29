---
name: wrap-up
description: End-of-task bookkeeping before a thread is retired — worklog lines, task-tree nodes current and validated, evidence beside the tree, this session's uncommitted work listed for commit, scratch removed. Use when the user says "wrap up", "do the bookkeeping", or is about to retire the thread.
---

# Wrap-up

Make sure everything this session did is recorded where the next reader looks, so nothing lives
only in the conversation. Work from your own actions this session; never touch another session's
files or dirty work.

Wrap-up never writes a daily or personal note; a separate day-end step does that, if the user
has one.

1. Worklog: every meaningful chunk has a line in today's worklog (location in the project's
   AGENTS.md), with the node id first.
2. Tree: every node you opened or changed is current — status, evidence, `## Outcome`. Any action
   item you wrote elsewhere names its node. Run validate.py --tree; report warnings, don't fix them.
   The wrap-up request is the user's go-ahead to close `done` the tasks this session finished (listed
   under `sessions:`, with `after:` and `## Outcome`); leave partial or blocked work open and say why.
   Child of a brief: if a node lists this session under `sessions:` and has a brief at
   `briefs/<id>.md` beside `problems/`, make its `## Outcome` answer the brief's *Report back*.
   Name the parent session from the brief's `parent_session` (with herdr, match it against
   `herdr agent list`, read only, and name its tab/pane; otherwise give `pi --session <path>` or
   `claude --resume <id>`). Print one line for the user to paste there:
   `<id> (<title>): <done|partial|blocked>, <one line>. Read <path to problems/<id>.md>`
   Summary: every node this session did real work on (analysis, a result, a decision) gets a
   `## Summary` between `## What` and `## Outcome`, refreshed rather than appended. Write it for
   an expert who was not in the session: plain words, no labels coined in the session, node ids
   explained. Four short parts: why we looked (the symptom and the doubt), what we found (each
   number with its figure path), what it means for the problem it serves, what is still open
   (with its node id).
3. Evidence: every number you gave in a reply has its figure or file beside the tree
   (media/problems/<id>/ or the note that cites it).
   Story point: if this session's work meets the bar in the `storyline` skill (most sessions
   don't), add its one-line suggestion to the report. Don't draft it.
4. Git: for each repo and the notes repository that holds the tree, list the files this session
   changed that are still uncommitted. The user asking for a wrap-up is permission to commit this
   session's changes to the notes repository — stage only your own hunks, never push. Code repos:
   ask for the commits (one per step). Never stage others' files.
5. Scratch: delete what you created under /tmp or the project's scratch folder (installs, test
   copies), and remove the task worktrees you created whose branch is merged or pushed
   (`git worktree remove`, clean trees only; keep the branch); list what you removed.
6. Report, in one short table: nodes opened / updated / closed; commits made; what is left
   uncommitted and why; files with no git history.
7. End the reply with exactly one of these lines, verbatim:
   - `WRAP-UP COMPLETE: this thread can be retired.` — only when steps 1–5 all passed and nothing
     waits on the user. A story point suggestion does not count as waiting.
   - `WRAP-UP INCOMPLETE: <what is left, e.g. commits awaiting approval>.` — otherwise.
