#!/usr/bin/env python3
"""Regenerate docs/img/*.png from the toy project. Needs playwright and a Chromium build.

    PROBLEM_TREE_CONFIG=example/config.yaml ./cockpit.sh start     # or serve.py --port 8895
    python example/screenshots.py [http://127.0.0.1:8895]
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8895"
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=sys.argv[2]) if len(sys.argv) > 2 else p.chromium.launch()
    pg = b.new_page(viewport={"width": 1500, "height": 900}, device_scale_factor=2)

    def go(h, wait=1200):
        pg.goto(f"{URL}/#/{h}")
        pg.wait_for_timeout(wait)

    go("node/demo-c3d4")
    pg.check("#showComplete")
    pg.click("text=fit")
    pg.wait_for_timeout(800)
    pg.screenshot(path=OUT / "tree-graph.png", clip={"x": 10, "y": 335, "width": 640, "height": 250})
    pg.screenshot(path=OUT / "node-evidence.png", clip={"x": 695, "y": 45, "width": 805, "height": 560})
    pg.screenshot(path=OUT / "cockpit.png")
    go("todos")
    pg.screenshot(path=OUT / "todos.png", clip={"x": 695, "y": 45, "width": 805, "height": 520})
    go("storyline")
    pg.screenshot(path=OUT / "storyline.png", clip={"x": 0, "y": 30, "width": 1500, "height": 640})
    b.close()
