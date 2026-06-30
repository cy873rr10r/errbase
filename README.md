# errbase

### Your terminal remembers how you fixed it last time.

You hit an error. You fix it. Three weeks later it happens again — and you're
back on Google re-finding the same answer.

**errbase ends that.** When an error shows up, it gives you the fix that worked
*last time* — pulled from a knowledge graph, not a flat history file.

---

## Try it in 10 seconds

```bash
python -m errbase demo
```

That one command does everything: loads a starter graph, looks up a real fix,
shows *why* that fix was chosen, draws the whole memory graph, and prints stats.
No setup, no API key needed.

---

## How it works (3 steps)

```
   you teach it a fix          you ask about an error        you confirm it worked
   ──────────────────  ──►   ─────────────────────────  ──►  ─────────────────────
   errbase fix ...            errbase recall "..."            errbase confirm ...
   stored in the graph        matched by *meaning*, not       fix ranks higher
                              exact text                       next time
```

1. **Store** — every error is saved as a small graph: *error → class → system → fix*.
2. **Recall** — a *similar* error still finds the right fix, because the graph
   matches the **error class**, not the exact words.
3. **Reinforce** — confirm a fix and it ranks higher. The graph gets smarter the
   more you use it.

You don't need an error to happen to use it — just type the error text and ask.

---

## Commands

| command | what it does |
|---|---|
| `errbase demo` | run the whole flow end-to-end (start here) |
| `errbase recall "<error>"` | look up the fix you used last time |
| `errbase why "<error>"` | show the graph chain behind a fix |
| `errbase graph` | see the whole memory graph |
| `errbase fix "<error>" "<cmd>"` | teach it a fix |
| `errbase confirm "<error>" "<cmd>"` | mark a fix as worked (reinforces it) |
| `errbase seed` | load the starter community graph |
| `errbase stats` | what errbase has learned |
| `errbase doctor` | check the Cognee connection |
| `errbase forget --all` | wipe memory |

---

## Turning on the graph brain (optional)

errbase works out of the box on a **local cache**. To switch on the real graph
memory ([Cognee](https://github.com/topoteretes/cognee) + Mistral), add a key.

Easiest — **Cognee Cloud**. Put your key in a `.env` file next to the project:

```
COGNEE_API_KEY="your_key_from_platform.cognee.ai"
```

errbase loads `.env` automatically — no exporting needed. Then:

```bash
errbase doctor    # verifies the live connection
errbase seed      # first real write to the cloud graph
errbase demo
```

> Prefer self-hosting? Set `LLM_API_KEY` + `LLM_PROVIDER=mistral` instead.
> See `.env.example` for all options.

---

## Auto-capture (optional)

Add the shell plugin and errbase learns silently while you work:

```bash
source ~/errbase/errbase.plugin.zsh
```

When a command fails and your **next** command fixes it, errbase asks **once**
if it should remember. Your error graph builds itself.

**Privacy:** everything is local-first. errbase never stores or runs a fix
without your `y`. Your secrets never leave your machine.

---

Built with **Cognee** (graph memory) · **Mistral** (entity extraction) ·
**Rich** (terminal UI).
