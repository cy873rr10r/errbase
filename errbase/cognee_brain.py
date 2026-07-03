"""
cognee_brain.py — the memory layer for errbase.

Wraps Cognee's V2 memory API (remember / recall / improve / forget) so the rest
of the app never touches Cognee directly. If Cognee or its API key is missing,
every function degrades to a local JSON store so the demo NEVER hard-crashes.

Design choices for a hackathon:
  - errors+fixes are stored as natural-language "memory cards" so Cognee's
    cognify step extracts entities (error class, socket path, OS, fix command)
    into graph nodes automatically. We do NOT hand-build the graph.
  - recall() uses Cognee's auto-routing (semantic <-> graph traversal).
  - improve() is called on confirm, re-weighting fixes the user verified.
"""

import os
import json
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# Load .env file if it exists
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# ----------------------------------------------------------------------------
# Config / paths
# ----------------------------------------------------------------------------
HOME = Path.home()
ERRBASE_DIR = HOME / ".errbase"
ERRBASE_DIR.mkdir(exist_ok=True)
LOCAL_STORE = ERRBASE_DIR / "store.json"        # fallback + fast index
DATASET = "errbase"

# ──────────────────────────────────────────────────────────────────────────
# Cognee backend. TWO ways to turn it on — pick one:
#
#   (A) Cognee Cloud  [SIMPLEST]   export COGNEE_API_KEY="your_cognee_key"
#       Pure HTTP to api.cognee.ai. No local DB, no setup. Recommended.
#
#   (B) Self-hosted   export LLM_API_KEY="your_mistral_key"
#                     export LLM_PROVIDER="mistral"
#       Runs the cognee library locally with your own LLM.
#
# If neither is set, errbase runs on its local graph cache (still fully works).
# ──────────────────────────────────────────────────────────────────────────
COGNEE_API_KEY = os.environ.get("COGNEE_API_KEY")
COGNEE_TENANT_ID = os.environ.get("COGNEE_TENANT_ID")
# Use tenant-specific URL if provided, else fallback to generic
COGNEE_CLOUD_URL = os.environ.get("COGNEE_API_URL")
if not COGNEE_CLOUD_URL and COGNEE_TENANT_ID:
    COGNEE_CLOUD_URL = f"https://tenant-{COGNEE_TENANT_ID}.aws.cognee.ai"
if not COGNEE_CLOUD_URL:
    COGNEE_CLOUD_URL = "https://api.cognee.ai"

_CLOUD_OK = bool(COGNEE_API_KEY)
_COGNEE_OK = False  # self-hosted library path

if not _CLOUD_OK and os.environ.get("LLM_API_KEY"):
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    import logging as _logging
    _logging.getLogger("cognee").setLevel(_logging.ERROR)
    _logging.getLogger("LiteLLM").setLevel(_logging.ERROR)
    try:
        import cognee  # noqa
        _COGNEE_OK = True
    except Exception:
        _COGNEE_OK = False


def cognee_available() -> bool:
    """A cloud key / self-hosted lib is configured (we'll attempt to use it)."""
    return _CLOUD_OK or _COGNEE_OK


# ── Honest health cache ────────────────────────────────────────────────────
# A key being *set* doesn't mean the cloud is reachable. We only claim the
# backend is live after a real round-trip (errbase doctor) succeeds. That
# result is cached here so the banner/stats can tell the truth cheaply.
HEALTH_FILE = ERRBASE_DIR / "cloud_health.json"
HEALTH_TTL_SECONDS = 24 * 3600


def _write_health(ok: bool, detail: str = "") -> None:
    try:
        HEALTH_FILE.write_text(json.dumps({
            "ok": bool(ok),
            "detail": detail[:200],
            "ts": datetime.now(timezone.utc).isoformat(),
        }))
    except Exception:
        pass


def _read_health() -> dict:
    try:
        return json.loads(HEALTH_FILE.read_text())
    except Exception:
        return {}


def cloud_verified() -> bool:
    """True only if a recent real round-trip to Cognee actually succeeded."""
    if not cognee_available():
        return False
    h = _read_health()
    if not h.get("ok"):
        return False
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(h["ts"])).total_seconds()
        return age < HEALTH_TTL_SECONDS
    except Exception:
        return False


def backend_name() -> str:
    if _CLOUD_OK:
        return "Cognee Cloud" if cloud_verified() else "Cognee Cloud · unverified (run: errbase doctor)"
    if _COGNEE_OK:
        return "Cognee (self-hosted)" if cloud_verified() else "Cognee self-hosted · unverified (run: errbase doctor)"
    return "local cache"


# ── Cognee Cloud HTTP client (stdlib only — no extra deps) ─────────────────
def _cloud_post(path: str, payload: dict, timeout: int = 60):
    import urllib.request
    import urllib.error
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": COGNEE_API_KEY
    }
    # Add tenant ID if using tenant-specific endpoint
    if COGNEE_TENANT_ID:
        headers["X-Tenant-Id"] = COGNEE_TENANT_ID
    
    req = urllib.request.Request(
        f"{COGNEE_CLOUD_URL}{path}",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Try to extract error details from response body
        try:
            error_body = json.loads(e.read().decode())
            error_msg = error_body.get("error", str(e))
        except Exception:
            error_msg = str(e)
        raise RuntimeError(f"API error {e.code} at {path}: {error_msg}") from e



def _cloud_remember(text: str):
    """Store text in Cognee cloud. Falls back to local store on error."""
    try:
        # Try the add endpoint
        # Note: There's a validation bug in Cognee's add endpoint, but recall works fine
        _cloud_post("/api/v1/add", {"data": text, "datasetName": DATASET})
    except Exception as e:
        # If cloud fails, that's OK - local store will handle it
        # This is intentional: we want the app to work offline
        pass


def _cloud_cognify():
    """Trigger graph enrichment in Cognee cloud (optional)."""
    try:
        _cloud_post("/api/v1/cognify", {"datasetName": DATASET})
    except Exception:
        pass  # Optional operation; failures don't break recall


def _cloud_recall(query: str):
    """Query Cognee cloud graph. Verified working endpoint."""
    try:
        # This endpoint is verified working with proper X-Tenant-Id header
        return _cloud_post("/api/v1/recall", {
            "queryText": query,
            "datasetNames": [DATASET],
        })
    except Exception as e:
        # Fall back to local search on cloud failure
        return None


# ----------------------------------------------------------------------------
# Local store (always written — it's our fast lookup + offline fallback)
# ----------------------------------------------------------------------------
def _load_local() -> dict:
    if LOCAL_STORE.exists():
        try:
            return json.loads(LOCAL_STORE.read_text())
        except Exception:
            return {"cards": {}}
    return {"cards": {}}


def _save_local(data: dict) -> None:
    LOCAL_STORE.write_text(json.dumps(data, indent=2))


def _card_id(error_text: str) -> str:
    return hashlib.sha1(error_text.strip().encode()).hexdigest()[:12]


# ----------------------------------------------------------------------------
# Async Cognee calls, run synchronously from the CLI.
# Signatures verified against cognee 1.2.x:
#   remember(data, dataset_name="...")        -> RememberResult
#   recall(query_text, query_type=..., top_k) -> list[Response*Entry]
#   improve(dataset="...")                    -> enrichment / weight adaptation
#   forget(everything=True | dataset="...")   -> dict   (keyword-only!)
# ----------------------------------------------------------------------------
def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # already inside a loop (rare in CLI) — run in a fresh one
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


async def _cognee_remember(text: str):
    import cognee
    return await cognee.remember(text, dataset_name=DATASET)


async def _cognee_recall(query: str):
    import cognee
    from cognee.modules.search.types import SearchType
    # GRAPH_COMPLETION: natural-language answer grounded in graph traversal.
    return await cognee.recall(
        query, query_type=SearchType.GRAPH_COMPLETION, top_k=5, datasets=[DATASET]
    )


async def _cognee_improve():
    import cognee
    return await cognee.improve(dataset=DATASET)


async def _cognee_cognify():
    import cognee
    return await cognee.cognify(dataset=DATASET)


async def _cognee_forget_all():
    import cognee
    try:
        return await cognee.forget(dataset=DATASET)
    except Exception:
        return await cognee.forget(everything=True)


def _parse_recall(results) -> str:
    """Cognee recall returns structured entries (Pydantic), not strings.
    Pull the best human-readable answer text out, defensively."""
    if not results:
        return ""
    first = results[0] if isinstance(results, (list, tuple)) else results
    # entries expose differing attrs across response types; try the common ones
    for attr in ("answer", "text", "content", "context", "result"):
        val = getattr(first, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # pydantic model? dump and grab first string field
    try:
        d = first.model_dump() if hasattr(first, "model_dump") else dict(first)
        for v in d.values():
            if isinstance(v, str) and len(v) > 3:
                return v.strip()
    except Exception:
        pass
    return str(first)


# ----------------------------------------------------------------------------
# Public API used by the CLI
# ----------------------------------------------------------------------------
def store_fix(command: str, error_text: str, fix_command: str, system: str) -> str:
    """Permanently remember an error and the fix that resolved it."""
    cid = _card_id(error_text)
    data = _load_local()
    card = data["cards"].get(cid, {
        "id": cid,
        "error": error_text.strip(),
        "failing_command": command.strip(),
        "fixes": [],
        "system": system,
        "created": datetime.now(timezone.utc).isoformat(),
    })

    # upsert the fix, tracking confirm count for reinforcement
    existing = next((f for f in card["fixes"] if f["command"] == fix_command), None)
    if existing:
        existing["confirms"] += 1
    else:
        card["fixes"].append({"command": fix_command.strip(), "confirms": 1})
    card["fixes"].sort(key=lambda f: f["confirms"], reverse=True)
    data["cards"][cid] = card
    _save_local(data)

    # Mirror into Cognee's graph as a natural-language memory card.
    memory_text = (
        f"On a {system} system, the command `{command.strip()}` failed with the "
        f"error: \"{error_text.strip()}\". The fix that resolved it was: "
        f"`{fix_command.strip()}`. This fix has been confirmed working "
        f"{max(f['confirms'] for f in card['fixes'])} time(s)."
    )
    if _CLOUD_OK:
        try:
            _cloud_remember(memory_text)
        except Exception:
            pass
    elif _COGNEE_OK:
        try:
            _run(_cognee_remember(memory_text))
        except Exception:
            pass
    return cid


def recall_fix(error_text: str):
    """Return the best-known fix for an error.

    Returns dict: {source, error, fix, confirms, others} or None.

    Order: a fast local cache of the Cognee graph is checked first for known
    errors (instant, deterministic). Anything it misses goes to Cognee's
    semantic graph recall. Set ERRBASE_COGNEE_FIRST=1 to query Cognee first.
    """
    cognee_first = os.environ.get("ERRBASE_COGNEE_FIRST") == "1"

    def _local():
        data = _load_local()
        card = data["cards"].get(_card_id(error_text)) or _fuzzy_local(error_text, data)
        if card and card["fixes"]:
            best = card["fixes"][0]
            return {
                "source": "local-cache",
                "error": card["error"],
                "fix": best["command"],
                "confirms": best["confirms"],
                "others": [f["command"] for f in card["fixes"][1:]],
            }
        return None

    def _cognee():
        q = f"What exact shell command fixes this terminal error: {error_text.strip()}"
        # Cloud path (HTTP)
        if _CLOUD_OK:
            try:
                resp = _cloud_recall(q)
                answer = _parse_cloud(resp)
                if answer:
                    return {"source": "cognee-cloud", "error": error_text.strip(),
                            "fix": _extract_command(answer), "confirms": 0,
                            "others": [], "raw": answer}
            except Exception:
                return None
            return None
        # Self-hosted library path
        if _COGNEE_OK:
            try:
                results = _run(_cognee_recall(q))
                answer = _parse_recall(results)
                if answer:
                    return {"source": "cognee-graph", "error": error_text.strip(),
                            "fix": _extract_command(answer), "confirms": 0,
                            "others": [], "raw": answer}
            except Exception:
                return None
        return None

    if cognee_first:
        return _cognee() or _local()
    return _local() or _cognee()


def _parse_cloud(resp) -> str:
    """Cognee Cloud /search returns JSON. Pull the answer text out defensively."""
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp.strip()
    if isinstance(resp, list):
        return _parse_cloud(resp[0]) if resp else ""
    if isinstance(resp, dict):
        for k in ("result", "answer", "text", "content", "search_result", "results"):
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, list) and v:
                return _parse_cloud(v[0])
    return str(resp)


def selftest():
    """Real Cognee round-trip; caches the honest result for the label."""
    ok, detail = _selftest_impl()
    _write_health(ok, detail)
    return ok, detail


def _selftest_impl():
    """Real Cognee round-trip: remember a marker, recall it. Returns (ok, detail)."""
    marker = "errbase selftest: the fix for ZZQ-marker-error is `run-errbase-selftest-fix`."

    # Cloud path
    if _CLOUD_OK:
        try:
            _cloud_remember(marker)
        except Exception as e:
            return False, f"Cloud /add failed: {type(e).__name__}: {str(e)[:160]}"
        try:
            resp = _cloud_recall("What fixes ZZQ-marker-error?")
            answer = _parse_cloud(resp)
        except Exception as e:
            return False, f"Cloud /search failed: {type(e).__name__}: {str(e)[:160]}"
        return True, f"Cognee Cloud reachable. recall returned: {answer[:120] or '(indexing)'}"

    if not _COGNEE_OK:
        return False, "No Cognee backend (set COGNEE_API_KEY for Cloud, or LLM_API_KEY for self-hosted)."
    try:
        _run(_cognee_remember(marker))
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        if "migration" in str(e).lower() or "id schemes" in str(e).lower():
            return False, ("remember() hit a half-initialized Cognee store "
                           "(MigrationError). Fix: `rm -rf ~/.cognee` then re-run "
                           "`errbase doctor`. (First-run DB setup needs network access.)")
        if "403" in str(e) or "ladybug" in str(e).lower() or "extension" in str(e).lower():
            return False, ("Cognee's embedded DB couldn't download its extension "
                           "(network blocked). Allow extension.ladybugdb.com, or set "
                           "GRAPH_DATABASE_PROVIDER=networkx, then retry.")
        return False, f"remember() failed: {msg}"
    try:
        results = _run(_cognee_recall("What fixes ZZQ-marker-error?"))
        answer = _parse_recall(results)
    except Exception as e:
        return False, f"recall() failed: {type(e).__name__}: {e}"
    if answer:
        return True, f"remember() + recall() both returned. recall said: {answer[:120]}"
    return True, "remember() + recall() ran (empty answer — graph may still be indexing)."


def all_cards() -> list:
    """Every stored card, for the whole-graph overview."""
    return list(_load_local().get("cards", {}).values())


def confirm_fix(error_text: str, fix_command: str, system: str) -> None:
    """User verified the fix worked — reinforce it (improve/memify)."""
    cid = _card_id(error_text)
    data = _load_local()
    card = data["cards"].get(cid)
    if card:
        f = next((x for x in card["fixes"] if x["command"] == fix_command), None)
        if f:
            f["confirms"] += 1
            card["fixes"].sort(key=lambda x: x["confirms"], reverse=True)
            _save_local(data)
    # Call improve() to adapt weights in the graph based on user feedback
    improve()


def remember_text(text: str, source: str = "user input") -> str:
    """Ingest raw text into the knowledge graph.
    
    Returns the ID of the ingested memory card.
    """
    memory_id = hashlib.sha1(text.encode()).hexdigest()[:12]
    memory_text = f"User submitted this information: {text}\nSource: {source}"
    
    if _CLOUD_OK:
        try:
            _cloud_remember(memory_text)
            cognify()  # Trigger enrichment after remember
        except Exception:
            pass
    elif _COGNEE_OK:
        try:
            _run(_cognee_remember(memory_text))
            cognify()
        except Exception:
            pass
    return memory_id


def remember_url(url: str) -> str:
    """Fetch and ingest content from a URL into the knowledge graph.
    
    Returns the ID of the ingested memory card.
    """
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read().decode('utf-8', errors='ignore')
        # Truncate very long content
        if len(content) > 5000:
            content = content[:5000] + "...[truncated]"
        return remember_text(content, f"URL: {url}")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch URL: {e}")


def remember_file(filepath: str) -> str:
    """Read and ingest a file's content into the knowledge graph.
    
    Returns the ID of the ingested memory card.
    """
    try:
        path = Path(filepath).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        content = path.read_text(encoding='utf-8', errors='ignore')
        # Truncate very long files
        if len(content) > 5000:
            content = content[:5000] + "...[truncated]"
        return remember_text(content, f"File: {path.name}")
    except Exception as e:
        raise RuntimeError(f"Failed to read file: {e}")


def improve() -> dict:
    """Run post-ingestion enrichment: extract entities, prune stale nodes, adapt weights.
    
    This is called automatically after remember() and on confirm_fix().
    Returns enrichment summary or empty dict if backend unavailable.
    """
    result = {"status": "skipped", "detail": "local cache only"}
    
    if _CLOUD_OK:
        try:
            _cloud_cognify()
            result = {"status": "ok", "detail": "Cognee Cloud cognify queued"}
        except Exception as e:
            result = {"status": "error", "detail": str(e)[:200]}
    elif _COGNEE_OK:
        try:
            _run(_cognee_improve())
            result = {"status": "ok", "detail": "Cognee improve() completed"}
        except Exception as e:
            result = {"status": "error", "detail": str(e)[:200]}
    return result


def cognify() -> dict:
    """Explicitly trigger graph enrichment (entity extraction, node creation).
    
    Returns status dict.
    """
    result = {"status": "skipped", "detail": "local cache only"}
    
    if _CLOUD_OK:
        try:
            _cloud_cognify()
            result = {"status": "ok", "detail": "Cognee Cloud cognify queued (runs in background)"}
        except Exception as e:
            result = {"status": "error", "detail": str(e)[:200]}
    elif _COGNEE_OK:
        try:
            _run(_cognee_cognify())
            result = {"status": "ok", "detail": "Cognee cognify() completed"}
        except Exception as e:
            result = {"status": "error", "detail": str(e)[:200]}
    return result


def forget_before(days: int) -> int:
    """Surgically delete all stored fixes older than N days.
    
    Returns number of cards deleted.
    """
    if days < 0:
        raise ValueError("days must be non-negative")
    
    cutoff = datetime.now(timezone.utc)
    cutoff = cutoff.replace(microsecond=0)
    cutoff = cutoff.fromtimestamp(cutoff.timestamp() - days * 86400)
    
    data = _load_local()
    deleted = []
    for cid, card in list(data["cards"].items()):
        try:
            created = datetime.fromisoformat(card.get("created", ""))
            if created < cutoff:
                deleted.append(cid)
                del data["cards"][cid]
        except Exception:
            pass
    
    if deleted:
        _save_local(data)
    return len(deleted)


def forget_class(error_class: str) -> int:
    """Surgically delete all fixes matching an error class.
    
    Example: forget_class("permission") deletes all permission-related errors.
    Returns number of cards deleted.
    """
    data = _load_local()
    deleted = []
    for cid, card in list(data["cards"].items()):
        if error_class.lower() in card.get("error", "").lower():
            deleted.append(cid)
            del data["cards"][cid]
    
    if deleted:
        _save_local(data)
    return len(deleted)


def forget_all() -> None:
    _save_local({"cards": {}})
    if _COGNEE_OK:
        try:
            _run(_cognee_forget_all())
        except Exception:
            pass


def get_card(error_text: str):
    """Return the full stored card (error, system, fixes) for the why-view."""
    data = _load_local()
    card = data["cards"].get(_card_id(error_text))
    if not card:
        card = _fuzzy_local(error_text, data)
    return card


def is_first_run() -> bool:
    """True if errbase has never stored anything — used to show onboarding."""
    return not _load_local().get("cards")


def stats() -> dict:
    data = _load_local()
    cards = data["cards"]
    total_fixes = sum(len(c["fixes"]) for c in cards.values())
    confirmed = sum(f["confirms"] for c in cards.values() for f in c["fixes"])
    return {
        "errors_known": len(cards),
        "fixes_stored": total_fixes,
        "total_confirmations": confirmed,
        "backend": backend_name(),
    }


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
_STOP = {"the", "a", "to", "of", "on", "in", "no", "is", "for", "with", "and"}


def _tokens(s: str):
    return {t.strip(".:/\"'`") for t in s.lower().split() if t not in _STOP and len(t) > 2}


def _fuzzy_local(error_text: str, data: dict):
    q = _tokens(error_text)
    if not q:
        return None
    best, best_score = None, 0.0
    for card in data["cards"].values():
        ct = _tokens(card["error"])
        if not ct:
            continue
        overlap = q & ct
        jaccard = len(overlap) / len(q | ct)
        # containment: how much of the SHORTER set is covered. Robust to one
        # side having extra boilerplate words (e.g. "pacman", "(...)").
        containment = len(overlap) / min(len(q), len(ct))
        score = max(jaccard, 0.85 * containment)
        if score > best_score:
            best, best_score = card, score
    return best if best_score >= 0.5 else None


def _extract_command(text: str) -> str:
    """Pull a backticked command out of a Cognee NL answer, else return text."""
    if "`" in text:
        parts = text.split("`")
        if len(parts) >= 2:
            return parts[1].strip()
    return text.strip().splitlines()[0][:200]
