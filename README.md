# errbase

### Your terminal remembers how you fixed it last time.

You've hit `permission denied on /run/user/1000/hyprland-0` before. You fixed it.
Three weeks later it happens again — and you're back on Google, re-finding the
same answer.

**errbase ends that.** When a command fails, it shows you the fix that worked
*last time* — pulled from a knowledge graph, not a flat history file.

---

## Why it's different from `Ctrl-R` history or RAG

Normal tools match **text**. errbase matches **meaning + relationships**.

It's built on [**Cognee**](https://github.com/topoteretes/cognee), which stores
each error as nodes in a graph — the error class, the socket path, your OS, and
the exact fix — all linked. So a *slightly different* error message still finds
the right fix, because the graph knows it's the **same error class**.

> Cognee reports **92.5%** retrieval accuracy on graph-structured memory vs
> ~60% for flat-chunk RAG. errbase applies that same graph structure to your
> shell errors.

**It gets smarter the more you use it.** Confirm a fix and errbase calls
Cognee's `improve()` to re-weight it — a fix you've verified 5 times ranks above
one you tried once.

---

## See it in 30 seconds

```bash
pip install "errbase[graph]"        # graph brain (Cognee + Mistral)
export LLM_API_KEY="your_mistral_key"
export LLM_PROVIDER="mistral"

errbase seed                        # load 50 common Arch/Nix/Docker/git fixes
errbase recall "permission denied on hyprland-0 socket"
```

```
╭─ errbase · your graph  ✓ confirmed 3× ──────────────────────────╮
│  You fixed this before:                                         │
│    $ rm -f /run/user/$(id -u)/hyprland-*.lock && systemctl ...  │
╰─────────────────────────────────────────────────────────────────╯
```

---

## Auto-mode: it learns while you work

Add the shell plugin and errbase captures failures silently:

```bash
# zinit
zinit load yourgithub/errbase
# or manual
source ~/errbase/errbase.plugin.zsh
```

Now when a command fails and your **next** command fixes it, errbase asks
**once** if it should remember. That's it — your error graph builds itself.

**Privacy:** everything is local-first. errbase **never** stores or runs a fix
without your `y`. Your secrets never leave your machine.

---

## The 10x angle: a shared error graph

Every Arch / NixOS / CachyOS user hits the same 50 errors. Today everyone
solves them alone. errbase turns one person's fix into **everyone's** fix — a
community knowledge graph that ships as a one-line plugin install.

One install. Every error someone already solved, solved for you too.

---

## Commands

| command | does |
|---|---|
| `errbase recall "<error>"` | look up the fix you used last time |
| `errbase fix "<error>" "<cmd>"` | teach it a fix |
| `errbase confirm "<error>" "<cmd>"` | mark a fix as worked (reinforces it) |
| `errbase stats` | what errbase has learned |
| `errbase seed` | load the starter community graph |
| `errbase forget --all` | wipe memory |

---

Built with **Cognee** (graph memory) · **Mistral** (entity extraction) ·
**Rich** (terminal UI).
