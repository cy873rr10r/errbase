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
   errbase remember ...       errbase recall "..."            errbase improve ...
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

## Memory lifecycle

Under the hood, errbase is built around four operations on the graph:

| stage | what it does |
|---|---|
| **remember** | ingest text, a URL, or a file into the graph |
| **recall** | query it — semantic similarity + graph traversal, not exact string match |
| **improve** | enrich the graph and re-weight fixes based on your feedback |
| **forget** | prune entries — all of them, older than N days, or matching a class |

`remember` / `recall` / `improve` / `forget` map directly onto Cognee's own
memory lifecycle API — errbase is a domain-specific CLI over exactly those
four operations.

---

## Commands

| command | what it does |
|---|---|
| `errbase demo` | run the whole flow end-to-end (start here) |
| `errbase recall "<error>"` | look up the fix you used last time |
| `errbase why "<error>"` | show the graph chain behind a fix |
| `errbase graph` | see the whole memory graph |
| `errbase remember "<error>" "<cmd>"` | teach it a fix |
| `errbase improve "<error>" "<cmd>"` | mark a fix as worked (reinforces it) |
| `errbase remember "<text>"` | ingest raw text into the graph |
| `errbase remember-url "<url>"` | fetch a URL and ingest it |
| `errbase remember-file "<path>"` | read a file and ingest it |
| `errbase improve` | run graph enrichment (extract entities, adapt weights) |
| `errbase cognify` | trigger explicit graph node creation |
| `errbase seed` | load the starter community graph |
| `errbase stats` | what errbase has learned |
| `errbase doctor` | check the Cognee connection |
| `errbase forget --all` | wipe memory |
| `errbase forget --before=<days>` | delete fixes older than N days |
| `errbase forget --class="<term>"` | delete errors matching a term |

---

## Turning on the graph brain (optional)

errbase works out of the box on a **local cache**. To switch on the real graph
memory ([Cognee Cloud](https://platform.cognee.ai)), add a key.

Put your key in a `.env` file next to the project:

```
COGNEE_API_KEY="your_key_from_platform.cognee.ai"
```

errbase loads `.env` automatically — no exporting needed. Then:

```bash
errbase doctor    # verifies the live connection
errbase seed      # first real write to the cloud graph
errbase demo
```

> One key is all you need — Cognee Cloud runs the graph extraction for you.

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

Built with **Cognee** (graph memory) · **Rich** (terminal UI).
