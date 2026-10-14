#!/usr/bin/env python3
"""Regenerate the toy project in example/: invented nodes and plots, used for the README screenshots.

    python make_example.py        (needs matplotlib and numpy)

Writes example/vault/02-Projects/demo/{problems,storyline,media}. Safe to re-run; it overwrites those folders.
"""
import pathlib
import shutil
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
PROJ = HERE / "vault" / "02-Projects" / "demo"
BLUE, ORANGE, GREEN, GRAY = "#2563eb", "#ea580c", "#16a34a", "#9ca3af"
rng = np.random.default_rng(7)
CATEGORY = {"demo-a1b2": "Statistics", "demo-c3d4": "Data & loading", "demo-r2s3": "Data & loading", "demo-e5f6": "Infrastructure",
            "demo-g7h8": "Infrastructure", "demo-i9j0": "Infrastructure", "demo-k1l2": "Statistics", "demo-m3n4": "Statistics",
            "demo-o5p6": "Infrastructure", "demo-q7r8": "Data & loading", "demo-s9t0": "Infrastructure", "demo-u1v2": "Infrastructure"}


def fig_path(node, name):
    p = PROJ / "media" / "problems" / node / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save(fig, path):
    for ax in fig.axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def hist_pair(node, before, after, xlabel):
    for name, data, color, title in (("before.png", before, ORANGE, "before"), ("after.png", after, GREEN, "after")):
        fig, ax = plt.subplots(figsize=(4, 2.8))
        ax.hist(data, bins=np.arange(min(before.min(), after.min()) - 0.5, max(before.max(), after.max()) + 1.5), color=color)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("reruns")
        ax.set_title(title, loc="left", fontsize=10)
        save(fig, fig_path(node, name))


def bars_pair(node, before, after, ylabel, labels):
    for name, vals, color, title in (("before.png", before, ORANGE, "before"), ("after.png", after, GREEN, "after")):
        fig, ax = plt.subplots(figsize=(4, 2.8))
        ax.bar(labels, vals, color=color)
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, max(max(before), max(after)) * 1.15)
        ax.set_title(title, loc="left", fontsize=10)
        save(fig, fig_path(node, name))


def scatter(node, name, noise, color, title):
    x = rng.uniform(0, 1, 60)
    fig, ax = plt.subplots(figsize=(4, 2.8))
    ax.scatter(x, x + rng.normal(0, noise, x.size), s=12, color=color)
    ax.plot([0, 1], [0, 1], color=GRAY, lw=1)
    ax.set_xlabel("laptop")
    ax.set_ylabel("cluster")
    ax.set_title(title, loc="left", fontsize=10)
    save(fig, fig_path(node, name))


def trace(node, name):
    t = np.arange(200)
    y = np.sin(t / 9) + rng.normal(0, 0.15, t.size)
    y[131:134] = np.nan
    fig, ax = plt.subplots(figsize=(4, 2.8))
    ax.plot(t, y, color=BLUE, lw=1)
    ax.set_xlabel("sample (x1000)")
    ax.set_ylabel("channel 41")
    ax.set_title("three NaN samples", loc="left", fontsize=10)
    save(fig, fig_path(node, name))


def node(id, type, title, parent, status, body, extra="", opened="2026-09-20", closed=None, assignee=None):
    category = CATEGORY.get(id)
    fm = f"""---
type: {type}
id: {id}
title: {title}
parent: {parent}
aliases: []
discovered_from: null
status: {status}
assignee: {assignee or 'null'}
{('category: ' + repr(category) + chr(10)) if category else ''}opened: {opened}
closed: {closed or 'null'}
{extra}source: human
tags: [demo, {type}]
---
# {id} — {title}

{textwrap.dedent(body).strip()}
"""
    (PROJ / "problems" / f"{id}.md").write_text(fm)


def ev(node_id, *names):
    return "".join(f"  - artifact: ../media/problems/{node_id}/{n}\n" for n in names)


def main():
    if PROJ.exists():
        shutil.rmtree(PROJ)
    (PROJ / "problems").mkdir(parents=True)

    # ---- evidence figures
    hist_pair("demo-a1b2", rng.integers(11, 19, 20), np.full(20, 14), "clusters found")
    bars_pair("demo-c3d4", [41, 9, 8], [12, 9, 8], "minutes", ["load", "filter", "sort"])
    scatter("demo-e5f6", "before.png", 0.12, ORANGE, "cluster vs laptop, before")
    scatter("demo-m3n4", "before.png", 0.2, ORANGE, "panel C, notebook vs raw data")
    bars_pair("demo-s9t0", [3, 5, 2], [3, 5, 2], "outputs", ["fig1", "fig2", "fig3"])
    trace("demo-q7r8", "channel41.png")

    # ---- the tree
    node("demo-root", "problem", "Make the analysis pipeline's results reproducible", "null", "open", """
        ## Problem
        The same recordings give different numbers depending on when and where the pipeline runs.
        """, opened="2026-09-01", extra="instrument: \"\"\nbefore: []\nafter: []\nfix: []\ntodo: \"\"\n")

    node("demo-a1b2", "problem", "The same recording gives a different cluster count on every rerun", "demo-root", "verified", """
        ## Problem
        Twenty reruns of one recording found between 11 and 18 clusters.

        ## Fix
        Seed every random number generator from the run config.

        ## Evidence the fix worked (after)
        Twenty reruns now find 14 clusters each time.
        """, opened="2026-09-03", closed="2026-09-10", assignee="agent", extra=f"""resolution: hard
instrument: "cluster count over 20 reruns of recording 3"
before:
{ev('demo-a1b2', 'before.png')}after:
{ev('demo-a1b2', 'after.png')}fix:
  - commit: pipeline@4f2a9c1
todo: ""
""")

    node("demo-c3d4", "problem", "Runtime grew fourfold after the filter change", "demo-root", "fix-landed", """
        ## Problem
        Loading dominates: 41 minutes against 12 before the change.

        ## Fix
        Cache the decoded recording between stages.

        ## Follow-up
        The cache fixes reruns; the first load is still slow. Profile the loader.
        """, opened="2026-09-12", assignee="agent", extra=f"""resolution: soft
instrument: "wall-clock minutes per stage, recording 3"
before:
{ev('demo-c3d4', 'before.png')}after:
{ev('demo-c3d4', 'after.png')}fix:
  - pr: pipeline#212
todo: "profile the first load"
""")
    node("demo-r2s3", "task", "Profile the first load of a recording", "demo-c3d4", "open", """
        ## What
        The cache hides the slow first load; find where the time goes.
        """, opened="2026-09-18", assignee="agent", extra="before: []\nafter: []\nfix: []\n")

    node("demo-e5f6", "problem", "Results differ between the laptop and the cluster", "demo-root", "open", """
        ## Problem
        Cluster counts agree, but spike times drift by up to 2 samples.
        """, opened="2026-09-15", extra=f"""resolution: null
instrument: "spike time difference, laptop vs cluster"
before:
{ev('demo-e5f6', 'before.png')}after: []
fix: []
todo: ""
""")
    node("demo-g7h8", "task", "Pin library versions in a lockfile", "demo-e5f6", "open", """
        ## What
        Both machines resolve different numpy builds.
        """, opened="2026-09-16", assignee="claude:session", extra="before: []\nafter: []\nfix: []\n")
    node("demo-i9j0", "task", "Log library versions with every run", "demo-e5f6", "done", """
        ## What
        Write numpy, scipy and the BLAS build into the run's config file.

        ## Outcome
        - Done: every run directory has a versions.txt.
        - Proof: commit pipeline@9be1d70, test_versions passes.
        - Not verified: runs started before this commit.
        """, opened="2026-09-16", closed="2026-09-19", assignee="agent", extra="before: []\nafter:\n  - commit: pipeline@9be1d70\nfix: []\n")
    node("demo-k1l2", "task", "Compare float precision on both machines", "demo-e5f6", "open", """
        ## What
        Rerun the filter in float64 on both and compare.
        """, opened="2026-09-17", extra="before: []\nafter: []\nfix: []\n")

    node("demo-m3n4", "problem", "Figure 3 cannot be regenerated from the raw data", "demo-root", "fix-proposed", """
        ## Problem
        Two panels depend on a notebook that was edited by hand.

        ## Fix
        Move the panel code into a script that reads only the raw files.
        """, opened="2026-09-14", assignee="agent", extra=f"""resolution: null
instrument: "figure 3 regenerated from raw files"
before:
{ev('demo-m3n4', 'before.png')}after: []
fix:
  - pr: pipeline#218
todo: ""
""")
    node("demo-o5p6", "task", "Script the figure 3 export", "demo-m3n4", "done", """
        ## What
        One command writes all panels.

        ## Outcome
        - Done: `make fig3` writes the panels.
        - Proof: output matches the paper figure pixel for pixel.
        - Not verified: panel C on a clean checkout.
        """, opened="2026-09-18", closed="2026-09-22", assignee="agent", extra="before: []\nafter:\n  - commit: pipeline@c77a310\nfix: []\n")
    node("demo-q7r8", "observation", "Three NaN samples in channel 41 of one recording", "demo-m3n4", "noted", """
        ## Observation
        Samples 131000 to 134000 of recording 5 are NaN, in one channel.

        ## Why not now
        The channel is excluded by the quality filter; tracing the acquisition fault would take days.
        """, opened="2026-09-21", extra=f"before:\n{ev('demo-q7r8', 'channel41.png')}promoted_to: null\nrevisit: \"if a second recording shows it\"\n")

    node("demo-s9t0", "problem", "No record of which parameters produced a result", "demo-root", "open", """
        ## Problem
        Notebooks overwrite their own outputs; nothing links a plot to its settings.
        """, opened="2026-09-23", extra=f"resolution: null\ninstrument: \"\"\nbefore:\n{ev('demo-s9t0', 'before.png')}after: []\nfix: []\ntodo: \"\"\n")
    node("demo-u1v2", "task", "Write the run config next to every output", "demo-s9t0", "open", """
        ## What
        One YAML per output directory.
        """, opened="2026-09-23", assignee="agent", extra="before: []\nafter: []\nfix: []\n")

    # ---- storyline
    (PROJ / "storyline").mkdir()
    for slug, date, title, kind, nodes, caps in (
        ("2026-09-10_seeds-fix-cluster-count", "2026-09-10", "Seeding the random number generators makes the cluster count repeatable", "fix", "[demo-a1b2]",
         ("Twenty reruns of one recording found 11 to 18 clusters.", "After seeding, all twenty find 14.")),
        ("2026-09-22_runtime-after-cache", "2026-09-22", "Caching the decoded recording cuts the pipeline from 58 to 29 minutes", "fix", "[demo-c3d4]",
         ("Loading takes 41 of the 58 minutes.", "With the cache, loading takes 12.")),
    ):
        d = PROJ / "media" / "storyline" / slug
        d.mkdir(parents=True)
        node_id = nodes.strip("[]")
        shutil.copy(PROJ / "media" / "problems" / node_id / "before.png", d / "problem.png")
        shutil.copy(PROJ / "media" / "problems" / node_id / "after.png", d / "solution.png")
        (PROJ / "storyline" / f"{slug}.md").write_text(f"""---
type: story
source: human
date: {date}
title: {title}
kind: {kind}
nodes: {nodes}
experiments: []
figures:
  - {{path: ../media/storyline/{slug}/problem.png, role: problem, caption: "{caps[0]}"}}
  - {{path: ../media/storyline/{slug}/solution.png, role: solution, caption: "{caps[1]}"}}
---
# {title}

{caps[0]} {caps[1]}
""")


if __name__ == "__main__":
    main()
