---
name: brief
description: Write a self-contained prompt (a brief) for a child task-tree node, so the user can start a fresh agent session on it by pasting the brief's path. Use when the user says "write a brief", "brief this", "hand this off", or asks for a prompt for a new session on a node. Never launch or prompt the child session yourself.
---

# Brief

The user runs one session per piece of work, loosely. When work surfaces a child node that deserves
its own session, this session writes the child's prompt to a file; the user starts the session and
pastes the path. You write the file and stop.

1. Node: find the child's node, or open a task for it with
   `new.py <problems dir> task --parent <id> --discovered-from <this session's node> --title "…"`
   (`new.py` ships with the task-tree tool; the project's AGENTS.md names the `problems/` folder).
   Fill its `## What` and `before:` if they are empty.
2. Brief: write `briefs/<node-id>.md` beside `problems/` (overwrite an older brief for the same
   node only after saying so). No checkboxes; the tree is the only task list. Add any frontmatter
   fields the project's notes require (AGENTS.md). Shape:

   ```markdown
   ---
   type: note
   source: agent
   node: <node-id>
   parent_node: <this session's node id>
   parent_session: <$PI_SESSION_FILE, or the Claude session id, or null>
   written: YYYY-MM-DD
   cwd: ~/…
   repo: <repo, branch or worktree the work belongs in>
   ---
   # Brief: <node-id> — <title>

   ## Goal            one or two sentences
   ## Why             the before: evidence, as ~/ paths
   ## What the parent knows
                       decisions, files and lines, commands, dead ends — only what this session
                       actually established; say what is unverified
   ## Constraints     point to AGENTS.md rules instead of restating them; name the repo/worktree
   ## Done means      **must**: the after: evidence that closes the node; the three-line ## Outcome
                       **if cheap**: extras (a card, a GPU probe) the session may defer with a note
   ## Report back     what the parent session needs to hear when this is done
   ## First move      1. Add this session to the node's `sessions:` list —
                          `{harness: pi, ref: <$PI_SESSION_ID>}` (Claude: `{harness: claude, ref: <session uuid>}`),
                          appending, never replacing other entries.
                       2. Read the node and the files above, propose a plan, and stop for the user.
   ```

3. Reply with the brief's `~/` path on its own line (plain, pasteable) and the node(s) you opened or
   updated, each with its short parenthetical. Do not start, split, or prompt any session or pane.
