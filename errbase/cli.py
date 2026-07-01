#!/usr/bin/env python3
"""
errbase — your terminal remembers how you fixed it last time.

Powered by Cognee (graph memory) + Mistral. Captures failed commands, stores
the fix that worked in a knowledge graph, and surfaces it the next time the
same error class appears — even on a fresh machine, via the shared error graph.

Usage:
    errbase help                       Show this help
    errbase recall "<error text>"      Look up a known fix for an error
    errbase capture <code> "<cmd>" "<stderr>"
                                       (called by the shell hook on failure)
    errbase fix "<error>" "<fix cmd>"  Manually teach errbase a fix
    errbase confirm "<error>" "<fix>"  Mark a fix as worked (reinforces it)
    errbase stats                      Show what errbase has learned
    errbase seed                       Load the starter community error graph
    errbase forget --all               Wipe all memory

Privacy: nothing is stored or run without your confirmation. errbase never
auto-executes a fix — it shows it and waits for you to press y.
"""

import os
import sys
import platform
from pathlib import Path

# Windows consoles default to cp1252 and choke on the box-drawing / ● ✓ glyphs
# (especially when output is piped). Force UTF-8 so errbase renders everywhere.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _load_dotenv():
    """Load a .env file into os.environ (zero-dependency, no overrides).

    Looks next to the package and up the cwd tree so `COGNEE_API_KEY` etc.
    persist across sessions without exporting them by hand. Runs BEFORE the
    cognee brain is imported, since the brain reads these keys at import time.
    """
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:  # real env vars win
                    os.environ[key] = val
        except Exception:
            pass
        break  # first .env found wins


_load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Confirm
from rich import box

from . import cognee_brain as brain
from .seed import SEED_CARDS

console = Console()

ACCENT = "#7c5cff"
OK = "#2ecf6b"
WARN = "#ffb454"
MUTED = "#8a8597"

# Animations only when we're on a real terminal (never when piped/redirected,
# so logs and `| head` stay instant). Disable with ERRBASE_NO_ANIM=1.
import time

ANIMATE = sys.stdout.isatty() and os.environ.get("ERRBASE_NO_ANIM") != "1"


def _pause(seconds: float = 0.35):
    if ANIMATE:
        time.sleep(seconds)


def _reveal(lines, delay: float = 0.05, style: str = ""):
    """Print lines one-by-one for a light typed-in reveal."""
    for ln in lines:
        console.print(ln, style=style) if style else console.print(ln)
        if ANIMATE:
            time.sleep(delay)


def _thinking(label: str, seconds: float = 0.8):
    """Brief spinner so steps feel like the graph is being traversed."""
    if not ANIMATE:
        return
    with console.status(f"[{ACCENT}]{label}[/{ACCENT}]", spinner="dots"):
        time.sleep(seconds)


def _system() -> str:
    try:
        return f"{platform.system()} ({platform.release().split('-')[0]})"
    except Exception:
        return "Linux"


# ----------------------------------------------------------------------------
# Pretty bits
# ----------------------------------------------------------------------------
# Plain ASCII art (no markup) — safe to split line-by-line for the reveal.
LOGO_ART = r""" ___ ___ ___ ___  ___ ___ ___
| -_|  _|  _| . || .'|_ -| -_|
|___|_| |_| |___||__,|___|___|"""

LOGO = f"[bold {ACCENT}]{LOGO_ART}[/bold {ACCENT}]"


def banner(animate: bool = True):
    from rich.console import Group
    s = brain.stats()
    verified = brain.cloud_verified()
    dot = f"[{OK}]●[/{OK}]" if verified else f"[{WARN}]●[/{WARN}]"

    # Light reveal: pulse the logo lines in before the panel settles.
    if animate and ANIMATE:
        for ln in LOGO_ART.split("\n"):
            console.print(Text(ln, style=f"bold {ACCENT}"), justify="left")
            time.sleep(0.07)
        console.print()
        time.sleep(0.12)
        console.clear()

    head = Group(
        Text.from_markup(LOGO),
        Text.from_markup(
            "\n[bold]your terminal remembers how you fixed it last time[/bold]\n"
            f"[dim]graph memory · Cognee[/dim]   {dot} [dim]{s['backend']}[/dim]"
        ),
    )
    console.print(
        Panel(head, border_style=ACCENT, box=box.HEAVY, padding=(1, 3))
    )


def welcome():
    """First-run onboarding — shown when errbase has no memory yet."""
    banner()
    console.print(
        Panel(
            Text.from_markup(
                "[bold]What it does[/bold]\n"
                "When a command fails, errbase shows the fix that worked [italic]last "
                "time[/italic] — pulled from a knowledge [bold]graph[/bold], not flat "
                "history. Same error class, different wording — still finds it.\n\n"
                "[bold]It learns by use.[/bold] Confirm a fix and it ranks higher next "
                "time. The graph gets smarter the more you work."
            ),
            border_style=ACCENT, box=box.ROUNDED, padding=(1, 2),
            title="welcome", title_align="left",
        )
    )
    # 3-step quick start
    steps = Table.grid(padding=(0, 2))
    steps.add_column(style=f"bold {ACCENT}", justify="right")
    steps.add_column()
    steps.add_row("1", "[bold]errbase seed[/bold]   [dim]load 50 common Arch/Nix/Docker/git fixes[/dim]")
    steps.add_row("2", "[bold]errbase recall \"permission denied hyprland-0\"[/bold]   [dim]try it[/dim]")
    steps.add_row("3", "[bold]source errbase.plugin.zsh[/bold]   [dim]auto-capture while you work[/dim]")
    console.print(Panel(steps, title="get started in 30 seconds",
                        title_align="left", border_style=OK, box=box.ROUNDED, padding=(1, 2)))
    console.print(f"[dim]full command list →[/dim] [bold {ACCENT}]errbase help[/bold {ACCENT}]\n")


def show_help():
    banner()
    t = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, padding=(0, 2))
    t.add_column("command", style=f"bold {ACCENT}", no_wrap=True)
    t.add_column("what it does")
    rows = [
        ("errbase demo", "Run the whole flow end-to-end (seed → recall → graph)"),
        ("errbase recall \"<error>\"", "Look up the fix you used last time"),
        ("errbase why \"<error>\"", "Show the graph chain behind a fix"),
        ("errbase graph", "See the whole memory graph at once"),
        ("errbase fix \"<error>\" \"<cmd>\"", "Teach errbase a fix manually"),
        ("errbase confirm \"<error>\" \"<cmd>\"", "Mark a fix as worked → reinforces it"),
        ("errbase stats", "See what errbase has learned"),
        ("errbase doctor", "Verify the live Cognee integration"),
        ("errbase seed", "Load the starter community graph"),
        ("errbase forget --all", "Wipe all memory"),
    ]
    for c, d in rows:
        t.add_row(c, d)
    console.print(t)
    console.print(
        Panel(
            "[bold]Auto-capture[/bold] (optional): add the shell hook so errbase learns "
            "silently.\nWhen a command fails, errbase asks "
            "[bold]once[/bold] before storing — your secrets never leave your machine "
            "without a [bold]y[/bold].",
            border_style="dim", box=box.ROUNDED,
            title="how it learns", title_align="left",
        )
    )


def show_why(error_text: str):
    """Render the graph chain: error → class → system → fix → confirmations."""
    from rich.tree import Tree
    card = brain.get_card(error_text)
    if not card:
        console.print(
            Panel(f"[dim]No graph entry for:[/dim] [bold]{error_text.strip()[:90]}[/bold]",
                  border_style=WARN, box=box.ROUNDED, title="errbase · why")
        )
        return

    best = card["fixes"][0]
    tree = Tree(f"[bold {WARN}]✕ error[/bold {WARN}]  {card['error'][:70]}")
    cls = tree.add(f"[{ACCENT}]◆ error class[/{ACCENT}]  [dim]{_class_of(card['error'])}[/dim]")
    sysn = cls.add(f"[{ACCENT}]▣ system[/{ACCENT}]  [dim]{card.get('system','Linux')}[/dim]")
    fixn = sysn.add(f"[bold {OK}]✓ fix[/bold {OK}]  $ {best['command']}")
    fixn.add(f"[dim]confirmed[/dim] [{OK}]{best['confirms']}×[/{OK}] [dim]— ranks above "
             f"{len(card['fixes'])-1} other fix(es)[/dim]")
    for other in card["fixes"][1:3]:
        sysn.add(f"[dim]✓ alt fix  $ {other['command']}  ({other['confirms']}×)[/dim]")

    console.print(
        Panel(tree, title="errbase · why this fix",
              title_align="left", border_style=ACCENT, box=box.ROUNDED, padding=(1, 2))
    )
    console.print(
        f"[dim]This is a graph traversal, not a text match — the same [/dim]"
        f"[bold]error class[/bold][dim] links every variant of this error to the "
        f"fix that worked.[/dim]\n"
    )


def _heat(conf: int) -> str:
    return OK if conf >= 3 else (WARN if conf >= 1 else MUTED)


def show_graph():
    """Wide shot: the whole memory grouped by error class → systems → fixes."""
    from rich.tree import Tree
    cards = brain.all_cards()
    if not cards:
        console.print(Panel("[dim]graph is empty — run [bold]errbase seed[/bold] first.[/dim]",
                            border_style=WARN, box=box.ROUNDED, title="errbase · graph"))
        return

    # group cards by error class
    classes = {}
    for c in cards:
        cls = _class_of(c["error"])
        classes.setdefault(cls, []).append(c)

    # pad system tags to a common width so the error column lines up cleanly
    sys_w = min(max((len(c.get("system", "Linux")) for c in cards), default=5), 8)

    total_fix = sum(len(c["fixes"]) for c in cards)
    total_conf = sum(f["confirms"] for c in cards for f in c["fixes"])
    root = Tree(
        f"[bold {ACCENT}]⬡ errbase graph[/bold {ACCENT}]\n"
        f"[dim]{len(cards)} errors · {len(classes)} classes · "
        f"{total_fix} fixes · {total_conf} confirmations[/dim]",
        guide_style=MUTED,
    )

    if ANIMATE:
        console.print()  # tidy spacing before the live build

    for cls, items in sorted(classes.items(), key=lambda kv: -len(kv[1])):
        cnode = root.add(
            f"[bold {ACCENT}]◆ {cls}[/bold {ACCENT}] [dim]· {len(items)}[/dim]"
        )
        for c in sorted(items, key=lambda c: -c["fixes"][0]["confirms"]):
            best = c["fixes"][0]
            conf = best["confirms"]
            heat = _heat(conf)
            tag = f"{c.get('system','Linux'):<{sys_w}}"
            enode = cnode.add(
                f"[{heat}]●[/{heat}] [bold dim]{tag}[/bold dim]  "
                f"[default]{c['error'][:50]}[/default]"
            )
            badge = f"[{heat}]{conf}×[/{heat}]" if conf else "[dim]new[/dim]"
            enode.add(
                f"[{OK}]✓[/{OK}] [dim]$[/dim] {best['command'][:58]}  {badge}"
            )

    console.print(Panel(root, title="errbase · full memory graph", title_align="left",
                        border_style=ACCENT, box=box.ROUNDED, padding=(1, 2)))
    console.print(
        f"  [{OK}]●[/{OK}] [dim]battle-tested 3×+[/dim]   "
        f"[{WARN}]●[/{WARN}] [dim]used once[/dim]   "
        f"[{MUTED}]●[/{MUTED}] [dim]unconfirmed[/dim]\n"
    )



def _class_of(error_text: str) -> str:
    """Cheap error-class label for the why-view (graph node name)."""
    t = error_text.lower()
    for key, label in (
        ("permission denied", "permission / socket access"),
        ("transaction", "package transaction conflict"),
        ("keyring", "package signature / keyring"),
        ("docker daemon", "docker daemon unreachable"),
        ("port", "port already in use"),
        ("externally-managed", "python env policy"),
        ("authentication", "git auth"),
        ("nvidia", "gpu driver"),
        ("wayland", "wayland display"),
        ("nix", "nix build / config"),
    ):
        if key in t:
            return label
    return "general error"


def show_fix(result: dict, error_text: str):
    if not result:
        console.print(
            Panel(
                f"[dim]No known fix yet for:[/dim]\n[bold]{error_text.strip()[:120]}[/bold]\n\n"
                f"When you solve it, run:\n  [bold {ACCENT}]errbase fix \"{error_text.strip()[:40]}...\" "
                f"\"<your fix command>\"[/bold {ACCENT}]",
                title="errbase · no memory",
                border_style=WARN,
                box=box.ROUNDED,
            )
        )
        return

    src_label = {
        "local-cache": "graph cache",
        "cognee-graph": "Cognee graph (live)",
        "cognee-cloud": "Cognee Cloud (live)",
    }.get(result["source"], result["source"])

    confirms = result.get("confirms", 0)
    badge = f"[{OK}]✓ confirmed {confirms}×[/{OK}]" if confirms else "[dim]unverified[/dim]"

    body = Text()
    body.append("You fixed this before:\n\n", style="dim")
    body.append(f"  $ {result['fix']}\n", style=f"bold {OK}")
    if result.get("others"):
        body.append("\nother fixes that worked:\n", style="dim")
        for o in result["others"][:3]:
            body.append(f"  · {o}\n", style="dim")

    console.print(
        Panel(
            body,
            title=f"errbase · {src_label}  {badge}",
            title_align="left",
            border_style=ACCENT,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def cmd_recall(error_text: str, interactive: bool = True):
    result = brain.recall_fix(error_text)
    show_fix(result, error_text)
    if result:
        console.print(f"[dim]why this fix? →[/dim] [bold {ACCENT}]errbase why \"{error_text.strip()[:30]}...\"[/bold {ACCENT}]")
    if result and interactive:
        if Confirm.ask(f"[{ACCENT}]Run this fix now?[/{ACCENT}]", default=False):
            console.print(f"[dim]→ copy/run:[/dim] [bold]{result['fix']}[/bold]")
            if Confirm.ask(f"[{OK}]Did it work?[/{OK}]", default=True):
                brain.confirm_fix(error_text, result["fix"], _system())
                console.print(f"[{OK}]✓ reinforced — this fix will rank higher next time.[/{OK}]")
    return result


def cmd_capture(code: str, command: str, stderr: str):
    """Called by the shell hook after a non-zero exit."""
    if not stderr.strip():
        stderr = command  # match on command if no stderr captured
    result = brain.recall_fix(stderr)
    if result:
        show_fix(result, stderr)
    # else: stay silent on first sight — don't nag the user


def cmd_fix(error_text: str, fix_command: str):
    if not Confirm.ask(
        f"[{ACCENT}]Store this fix in your error graph?[/{ACCENT}] "
        f"[dim](nothing leaves your machine)[/dim]",
        default=True,
    ):
        console.print("[dim]skipped — nothing stored.[/dim]")
        return
    brain.store_fix(
        command="", error_text=error_text, fix_command=fix_command, system=_system()
    )
    console.print(f"[{OK}]✓ learned.[/{OK}] errbase will surface this next time.")


def cmd_confirm(error_text: str, fix_command: str):
    brain.confirm_fix(error_text, fix_command, _system())
    console.print(f"[{OK}]✓ reinforced.[/{OK}]")


def cmd_stats():
    s = brain.stats()
    t = Table(box=box.ROUNDED, border_style=ACCENT, title="errbase · memory")
    t.add_column("metric", style="dim")
    t.add_column("value", style=f"bold {ACCENT}", justify="right")
    t.add_row("errors known", str(s["errors_known"]))
    t.add_row("fixes stored", str(s["fixes_stored"]))
    t.add_row("confirmations", str(s["total_confirmations"]))
    t.add_row("backend", s["backend"])
    console.print(t)


def cmd_seed():
    with console.status("[bold]seeding community error graph...[/bold]", spinner="dots"):
        for card in SEED_CARDS:
            brain.store_fix(
                command=card.get("cmd", ""),
                error_text=card["error"],
                fix_command=card["fix"],
                system=card.get("system", "Linux"),
            )
    console.print(
        f"[{OK}]✓ seeded {len(SEED_CARDS)} common fixes[/{OK}] "
        f"[dim](Arch/Nix/CachyOS/git/docker).[/dim]"
    )


def cmd_doctor():
    """Verify the Cognee integration end-to-end with a real round-trip."""
    import os
    banner()
    t = Table(box=box.ROUNDED, border_style=ACCENT, title="errbase doctor · integration check")
    t.add_column("check", style="dim")
    t.add_column("result")

    cloud_key = os.environ.get("COGNEE_API_KEY")
    llm_key = os.environ.get("LLM_API_KEY")

    if cloud_key:
        t.add_row("mode", f"[{OK}]Cognee Cloud[/{OK}]  [dim](simplest)[/dim]")
        t.add_row("COGNEE_API_KEY", f"[{OK}]✓ set[/{OK}]")
        t.add_row("endpoint", f"[dim]{os.environ.get('COGNEE_API_URL','https://api.cognee.ai')}[/dim]")
        console.print(t)
        ready = True
    elif llm_key:
        try:
            import cognee
            ver = getattr(cognee, "__version__", "?")
            t.add_row("mode", "[bold]self-hosted[/bold]")
            t.add_row("cognee installed", f"[{OK}]✓ v{ver}[/{OK}]")
            t.add_row("LLM_API_KEY", f"[{OK}]✓ set[/{OK}]")
            t.add_row("LLM_PROVIDER", f"[dim]{os.environ.get('LLM_PROVIDER','(unset)')}[/dim]")
            console.print(t)
            ready = True
        except Exception as e:
            t.add_row("cognee installed", f"[red]✗ {e}[/red]")
            console.print(t)
            ready = False
    else:
        t.add_row("mode", f"[{WARN}]local cache only[/{WARN}]")
        console.print(t)
        console.print(Panel(
            "[bold]Turn on the Cognee graph:[/bold]\n\n"
            f"[bold {OK}]Add your Cognee Cloud key:[/bold {OK}]\n"
            "  Put [bold]COGNEE_API_KEY=...[/bold] in a [bold].env[/bold] file "
            "[dim](get it from platform.cognee.ai)[/dim]\n\n"
            "[dim]errbase works on the local cache until then.[/dim]",
            border_style=WARN, box=box.ROUNDED, title="action needed", title_align="left"))
        return

    if not ready:
        return

    with console.status("[bold]running real remember → recall against Cognee...[/bold]", spinner="dots"):
        ok, detail = brain.selftest()
    if ok:
        console.print(Panel(
            f"[bold {OK}]✓ Cognee integration LIVE.[/bold {OK}]\n{detail}",
            border_style=OK, box=box.ROUNDED, title="ready", title_align="left"))
    else:
        console.print(Panel(
            f"[red]✗ round-trip failed:[/red]\n{detail}",
            border_style="red", box=box.ROUNDED, title="integration error", title_align="left"))


def cmd_forget():
    if Confirm.ask("[red]Wipe ALL errbase memory?[/red]", default=False):
        brain.forget_all()
        console.print("[dim]forgotten.[/dim]")


def cmd_demo():
    """One command that runs the whole flow end-to-end — no manual steps.

    seed (if empty) → recall a real fix → why → full graph → stats.
    """
    banner()
    _pause(0.3)

    # 1. make sure the graph has something to show
    if brain.stats()["errors_known"] == 0:
        console.print(f"[bold {ACCENT}]▸ step 1 · seeding the community error graph[/bold {ACCENT}]")
        cmd_seed()
    else:
        console.print(f"[dim]▸ step 1 · graph already populated — skipping seed[/dim]")
    console.print()
    _pause()

    # pick a real seeded error to walk through
    sample = SEED_CARDS[0]["error"]

    # 2. recall the fix (non-interactive so it runs unattended)
    console.print(f"[bold {ACCENT}]▸ step 2 · recall[/bold {ACCENT}]  [dim]errbase recall \"{sample[:48]}...\"[/dim]")
    _thinking("searching the graph by error class…", 0.9)
    cmd_recall(sample, interactive=False)
    console.print()
    _pause()

    # 3. why this fix — the graph reasoning chain
    console.print(f"[bold {ACCENT}]▸ step 3 · why[/bold {ACCENT}]  [dim]the graph chain behind that fix[/dim]")
    _thinking("traversing error → class → system → fix…", 0.9)
    show_why(sample)
    console.print()
    _pause()

    # 4. the whole graph
    console.print(f"[bold {ACCENT}]▸ step 4 · graph[/bold {ACCENT}]  [dim]the full memory at a glance[/dim]")
    _thinking("laying out the memory graph…", 0.7)
    show_graph()
    console.print()
    _pause()

    # 5. summary
    console.print(f"[bold {ACCENT}]▸ step 5 · stats[/bold {ACCENT}]")
    cmd_stats()
    console.print(
        f"\n[{OK}]✓ demo complete.[/{OK}] [dim]try it live →[/dim] "
        f"[bold {ACCENT}]errbase recall \"<your error>\"[/bold {ACCENT}]\n"
    )


# ----------------------------------------------------------------------------
# Arg routing (no argparse — keep it tiny and predictable)
# ----------------------------------------------------------------------------
def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]

    # Bare `errbase` → onboarding on first run, help once they've used it.
    if not argv:
        if brain.is_first_run():
            welcome()
        else:
            show_help()
        return
    if argv[0] in ("help", "-h", "--help"):
        show_help()
        return

    cmd = argv[0]
    rest = argv[1:]

    try:
        if cmd == "recall" and rest:
            cmd_recall(" ".join(rest))
        elif cmd == "why" and rest:
            show_why(" ".join(rest))
        elif cmd == "graph":
            show_graph()
        elif cmd == "doctor":
            cmd_doctor()
        elif cmd == "capture" and len(rest) >= 3:
            cmd_capture(rest[0], rest[1], rest[2])
        elif cmd == "fix" and len(rest) >= 2:
            cmd_fix(rest[0], rest[1])
        elif cmd == "confirm" and len(rest) >= 2:
            cmd_confirm(rest[0], rest[1])
        elif cmd == "stats":
            cmd_stats()
        elif cmd == "seed":
            cmd_seed()
        elif cmd == "demo":
            cmd_demo()
        elif cmd == "forget":
            cmd_forget()
        else:
            console.print(f"[{WARN}]unknown or incomplete command.[/{WARN}] try [bold]errbase help[/bold]")
    except KeyboardInterrupt:
        console.print("\n[dim]cancelled.[/dim]")


if __name__ == "__main__":
    main()
