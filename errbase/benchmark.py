#!/usr/bin/env python3
"""
benchmark.py — measure errbase's graph matching vs naive flat-text matching.

Why this exists: the pitch claims graph beats flat RAG. Don't borrow Cognee's
92.5% — measure YOUR number on YOUR error set so you can defend it.

Method:
  1. Seed the graph with the canonical error → fix cards.
  2. For each error, generate realistic VARIANTS (reworded, extra noise, the way
     stderr actually looks — never identical to the stored text).
  3. For each variant, ask both retrievers for a fix:
       - FLAT: exact/substring match on stored error text (a stand-in for naive
         history search / flat-chunk matching).
       - GRAPH: errbase's class + token-overlap matching (the real recall path).
  4. Score: did the returned fix equal the correct fix for that error?

Run:  python -m errbase.benchmark
"""

import os
from pathlib import Path

# isolate the benchmark store so it doesn't touch your real ~/.errbase
os.environ["HOME"] = str(Path("/tmp/errbase_bench").resolve())
Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)

from rich.console import Console
from rich.table import Table
from rich import box

from . import cognee_brain as brain

console = Console()
ACCENT, OK, WARN = "#7c5cff", "#2ecf6b", "#ffb454"

# (canonical error, correct fix, [realistic variants as stderr would appear])
CASES = [
    (
        "permission denied on /run/user/1000/hyprland-0 socket",
        "rm -f /run/user/$(id -u)/hyprland-*.lock && systemctl --user restart hyprland",
        [
            "Permission denied (os error 13): /run/user/1000/hyprland-0",
            "could not open hyprland socket: permission denied",
            "hyprctl: permission denied accessing /run/user/1000/hyprland-0.lock",
        ],
    ),
    (
        "error: failed to commit transaction (conflicting files) pacman",
        "sudo pacman -S --overwrite '*' <package>",
        [
            "error: failed to commit transaction (conflicting files)",
            "pacman: conflicting files found, transaction failed",
            "failed to commit transaction: /usr/lib/foo.so exists in filesystem",
        ],
    ),
    (
        "Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
        "sudo systemctl start docker && sudo usermod -aG docker $USER",
        [
            "docker: Cannot connect to the Docker daemon. Is the docker daemon running?",
            "Cannot connect to Docker daemon at unix:///var/run/docker.sock",
            "error during connect: docker daemon not running",
        ],
    ),
    (
        "error: externally-managed-environment pip install",
        "python -m venv .venv && source .venv/bin/activate && pip install <package>",
        [
            "error: externally-managed-environment",
            "This environment is externally managed (PEP 668), pip install blocked",
            "pip refused: externally managed environment",
        ],
    ),
    (
        "bind: address already in use port 8000",
        "fuser -k 8000/tcp",
        [
            "OSError: [Errno 98] Address already in use: port 8000",
            "bind: address already in use (8000)",
            "uvicorn error: [Errno 98] Address already in use",
        ],
    ),
    (
        "error: GPGME error: No data signature keyring pacman",
        "sudo pacman-key --refresh-keys && sudo pacman -Sy archlinux-keyring",
        [
            "error: GPGME error: No data",
            "pacman signature from database is invalid: keyring out of date",
            "GPGME error: invalid signature, refresh keyring",
        ],
    ),
]


def flat_lookup(variant: str, cards: list):
    """Naive baseline: return a fix only on substring overlap of the raw text."""
    v = variant.lower()
    for c in cards:
        stored = c["error"].lower()
        # flat match: stored error appears in variant or vice-versa
        if stored in v or v in stored:
            return c["fixes"][0]["command"]
    return None


def run():
    brain.forget_all()
    cards_meta = []
    for err, fix, _ in CASES:
        brain.store_fix("", err, fix, "Linux")
        cards_meta.append({"error": err, "fix": fix})
    cards = brain.all_cards()

    flat_hits = graph_hits = total = 0
    rows = []
    for err, correct_fix, variants in CASES:
        for v in variants:
            total += 1
            # FLAT baseline
            flat = flat_lookup(v, cards)
            flat_ok = (flat == correct_fix)
            # GRAPH (errbase real recall)
            g = brain.recall_fix(v)
            graph_ok = bool(g and g["fix"] == correct_fix)
            flat_hits += flat_ok
            graph_hits += graph_ok
            rows.append((v[:48], flat_ok, graph_ok))

    # results table
    t = Table(box=box.ROUNDED, border_style=ACCENT,
              title="errbase benchmark · graph vs flat text matching")
    t.add_column("error variant (as stderr appears)", style="dim")
    t.add_column("flat", justify="center")
    t.add_column("graph", justify="center")
    for v, f, g in rows:
        t.add_row(
            v,
            f"[{OK}]✓[/{OK}]" if f else "[red]✗[/red]",
            f"[{OK}]✓[/{OK}]" if g else "[red]✗[/red]",
        )
    console.print(t)

    flat_pct = 100 * flat_hits / total
    graph_pct = 100 * graph_hits / total
    summary = Table(box=box.HEAVY, border_style=ACCENT)
    summary.add_column("retriever", style="bold")
    summary.add_column("accuracy", justify="right")
    summary.add_row("flat text match (baseline)", f"[{WARN}]{flat_pct:.0f}%[/{WARN}]")
    summary.add_row("errbase graph match", f"[bold {OK}]{graph_pct:.0f}%[/bold {OK}]")
    console.print(summary)
    console.print(
        f"\n[dim]On {total} realistic error variants, errbase's graph matching "
        f"resolved [/dim][bold {OK}]{graph_pct:.0f}%[/bold {OK}][dim] to the correct "
        f"fix vs [/dim][{WARN}]{flat_pct:.0f}%[/{WARN}][dim] for flat text matching.[/dim]\n"
    )


if __name__ == "__main__":
    run()
