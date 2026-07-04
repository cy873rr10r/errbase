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
import uuid
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
DATASET = "errbase_v3"

# ──────────────────────────────────────────────────────────────────────────
# Cognee Cloud.   export COGNEE_API_KEY="your_cognee_key"
# Pure HTTP to api.cognee.ai (or your tenant's dedicated endpoint). No local
# DB, no setup. If not set, errbase runs on its local graph cache only.
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


def cognee_available() -> bool:
    """A Cognee Cloud key is configured (we'll attempt to use it)."""
    return _CLOUD_OK


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
    return "local cache"


# ── Cognee Cloud HTTP client (stdlib only — no extra deps) ─────────────────
# Endpoints/payloads below were verified directly against the live API —
# the docs' Python SDK names (remember/recall/improve) don't map 1:1 onto
# the REST paths (add/cognify/search), and several fields are camelCase.
def _cloud_headers(extra: dict | None = None) -> dict:
    headers = {"X-Api-Key": COGNEE_API_KEY}
    if COGNEE_TENANT_ID:
        headers["X-Tenant-Id"] = COGNEE_TENANT_ID
    if extra:
        headers.update(extra)
    return headers


def _cloud_request(method: str, path: str, data: bytes | None = None,
                    headers: dict | None = None, timeout: int = 60):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        f"{COGNEE_CLOUD_URL}{path}", data=data,
        headers=_cloud_headers(headers), method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        try:
            error_body = json.loads(e.read().decode())
            error_msg = error_body.get("detail", error_body.get("error", str(e)))
        except Exception:
            error_msg = str(e)
        raise RuntimeError(f"API error {e.code} at {path}: {error_msg}") from e


def _cloud_post(path: str, payload: dict, timeout: int = 60):
    return _cloud_request(
        "POST", path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, timeout=timeout,
    )


def _cloud_remember(text: str, filename: str = "memory.txt"):
    """Store text in Cognee cloud via multipart /add (it's a file-upload
    endpoint, not JSON — sending JSON silently fails validation).
    Returns (dataset_id, data_id), or (None, None) on failure.
    """
    boundary = uuid.uuid4().hex
    body = bytearray()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="datasetName"'
              f'\r\n\r\n{DATASET}\r\n').encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="data"; '
              f'filename="{filename}"\r\nContent-Type: text/plain\r\n\r\n').encode()
    body += text.encode() + b"\r\n"
    body += f'--{boundary}--\r\n'.encode()
    try:
        resp = _cloud_request(
            "POST", "/api/v1/add", data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        dataset_id = resp.get("dataset_id") if resp else None
        info = (resp.get("data_ingestion_info") or []) if resp else []
        data_id = info[0].get("data_id") if info else None
        return dataset_id, data_id
    except Exception:
        return None, None


def _cloud_cognify(block: bool = True):
    """Trigger graph enrichment in Cognee cloud. Blocks by default so a
    recall() right after is guaranteed to see the new data."""
    try:
        _cloud_post("/api/v1/cognify", {"datasets": [DATASET], "run_in_background": not block})
    except Exception:
        pass  # Optional operation; failures don't break recall


def _cloud_recall(query: str):
    """Query Cognee cloud graph via /api/v1/search (the SDK's recall() maps
    to this REST path, not /api/v1/recall — that path doesn't exist)."""
    try:
        return _cloud_post("/api/v1/search", {
            "searchType": "GRAPH_COMPLETION",
            "query": query,
            "datasets": [DATASET],
            "topK": 5,
        })
    except Exception:
        return None


_dataset_id_cache: dict[str, str] = {}


def _cloud_dataset_id() -> str | None:
    """Resolve the errbase dataset's UUID (needed for delete calls)."""
    if DATASET in _dataset_id_cache:
        return _dataset_id_cache[DATASET]
    try:
        datasets = _cloud_request("GET", "/api/v1/datasets") or []
        for d in datasets:
            if d.get("name") == DATASET:
                _dataset_id_cache[DATASET] = d["id"]
                return d["id"]
    except Exception:
        pass
    return None


def _cloud_delete_dataset() -> bool:
    """Delete the whole errbase dataset from Cognee Cloud.

    One retry on failure: observed intermittent 500s from the Cloud API on
    datasets that have been rapidly recreated (delete -> add -> delete...),
    which succeed on a second attempt.
    """
    ds_id = _cloud_dataset_id()
    if not ds_id:
        return False
    import time
    for attempt in range(2):
        try:
            _cloud_request("DELETE", f"/api/v1/datasets/{ds_id}")
            _dataset_id_cache.pop(DATASET, None)
            return True
        except Exception:
            if attempt == 0:
                time.sleep(1.5)
    return False


def _cloud_delete_data(data_id: str) -> bool:
    """Delete a single data item from the errbase dataset."""
    ds_id = _cloud_dataset_id()
    if not ds_id or not data_id:
        return False
    try:
        _cloud_request("DELETE", f"/api/v1/datasets/{ds_id}/data/{data_id}")
        return True
    except Exception:
        return False


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
# Public API used by the CLI
# ----------------------------------------------------------------------------
def store_fix(command: str, error_text: str, fix_command: str, system: str,
              cognify: bool = True) -> str:
    """Permanently remember an error and the fix that resolved it.

    cognify=False skips the blocking re-index after this one add — use for
    bulk loads (seed) where 50 back-to-back blocking cognify calls have been
    observed to overload/error out Cognee Cloud's pipeline. Callers doing
    bulk inserts should add everything, then call cognee_brain.cognify()
    once at the end.
    """
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
            _, data_id = _cloud_remember(memory_text)
            if data_id:
                # track the cloud data_id so forget_before/forget_class can
                # actually delete this entry from Cognee's graph, not just local cache
                data = _load_local()
                data["cards"][cid].setdefault("cloud_data_ids", []).append(data_id)
                _save_local(data)
            if cognify:
                _cloud_cognify(block=True)
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

    def _tombstoned() -> bool:
        # Cognee Cloud's per-item delete removes the source record but does not
        # retroactively prune nodes already extracted into the graph (verified:
        # delete + re-cognify still answers from the deleted entry). Without this
        # check, forget_before/forget_class would appear to work, then the exact
        # same error would silently resurface from stale cloud data on next recall.
        data = _load_local()
        tombstones = data.get("tombstones", {})
        if _card_id(error_text) in tombstones:
            return True
        return any(
            _tokens(error_text) & _tokens(t["error"])
            and len(_tokens(error_text) & _tokens(t["error"])) / max(1, len(_tokens(error_text) | _tokens(t["error"]))) >= 0.5
            for t in tombstones.values()
        )

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
        if _tombstoned():
            return None
        q = f"What exact shell command fixes this terminal error: {error_text.strip()}"
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

    if cognee_first:
        return _cognee() or _local()
    return _local() or _cognee()


# Cognee's GRAPH_COMPLETION answers sometimes render plain ASCII hyphens as
# typographic Unicode dash variants (observed: U+2011 non-breaking hyphen).
# Left un-normalized, this silently breaks exact-match checks and produces
# fix commands that look right but fail to run (different byte, same glyph).
_DASH_VARIANTS = "‐‑‒–—―−"


def _normalize_dashes(text: str) -> str:
    for ch in _DASH_VARIANTS:
        text = text.replace(ch, "-")
    return text


def _parse_cloud(resp) -> str:
    """Cognee Cloud /search returns [{dataset_name, search_result: [...]}, ...].
    Pull the first answer string out, defensively."""
    if resp is None:
        return ""
    if isinstance(resp, str):
        return _normalize_dashes(resp.strip())
    if isinstance(resp, list):
        for entry in resp:
            text = _parse_cloud(entry)
            if text:
                return text
        return ""
    if isinstance(resp, dict):
        for k in ("search_result", "result", "answer", "text", "content", "results"):
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return _normalize_dashes(v.strip())
            if isinstance(v, list) and v:
                return _parse_cloud(v[0])
    return str(resp).strip()


def selftest():
    """Real Cognee round-trip; caches the honest result for the label."""
    ok, detail = _selftest_impl()
    _write_health(ok, detail)
    return ok, detail


def _selftest_impl():
    """Real Cognee round-trip: remember a marker, recall it. Returns (ok, detail).

    Uses a fresh unique marker each run and checks the recall answer actually
    contains the fix — a prior version declared "LIVE" as long as recall
    returned *any* text, even unrelated content already in the graph.
    """
    marker_id = f"ZZQ-{uuid.uuid4().hex[:8]}"
    marker_fix = f"run-errbase-selftest-{uuid.uuid4().hex[:6]}"
    marker = f"errbase selftest: the fix for {marker_id} is `{marker_fix}`."

    # Cloud path
    if _CLOUD_OK:
        try:
            _, data_id = _cloud_remember(marker)
            if not data_id:
                return False, "Cloud /add did not return a data_id — ingestion likely failed."
        except Exception as e:
            return False, f"Cloud /add failed: {type(e).__name__}: {str(e)[:160]}"
        try:
            _cloud_cognify(block=True)
        except Exception as e:
            return False, f"Cloud /cognify failed: {type(e).__name__}: {str(e)[:160]}"
        try:
            resp = _cloud_recall(f"What fixes {marker_id}?")
            answer = _parse_cloud(resp)
        except Exception as e:
            return False, f"Cloud /search failed: {type(e).__name__}: {str(e)[:160]}"
        if marker_fix in answer:
            return True, f"Cognee Cloud round-trip verified. recall correctly returned: {answer[:120]}"
        return False, f"Cloud round-trip ran but recall didn't return the expected fix. Got: {answer[:160] or '(empty)'}"

    return False, "No Cognee backend configured (set COGNEE_API_KEY)."


def all_cards() -> list:
    """Every stored card, for the whole-graph overview."""
    return list(_load_local().get("cards", {}).values())


def confirm_fix(error_text: str, fix_command: str, system: str) -> bool:
    """User verified the fix worked — reinforce it (improve/memify).

    Returns whether a matching card was actually found and reinforced.

    Card lookup falls back to fuzzy matching (same as recall_fix) if the
    exact error_text hash misses — callers, especially LLM agents, don't
    always reproduce identical wording between the recall_fix call and a
    later confirm_fix call, and an exact-hash-only lookup would silently
    find nothing in that case. Fix-text matching falls back to the sole
    stored fix (or best token-overlap match among several) for the same
    reason: callers don't always reproduce the exact stored string verbatim.
    """
    cid = _card_id(error_text)
    data = _load_local()
    card = data["cards"].get(cid) or _fuzzy_local(error_text, data)
    if not card or not card["fixes"]:
        return False
    f = next((x for x in card["fixes"] if x["command"] == fix_command), None)
    if not f:
        if len(card["fixes"]) == 1:
            f = card["fixes"][0]
        else:
            q = _tokens(fix_command)
            f = max(card["fixes"], key=lambda x: len(q & _tokens(x["command"])))
    f["confirms"] += 1
    card["fixes"].sort(key=lambda x: x["confirms"], reverse=True)
    _save_local(data)
    # Call improve() to adapt weights in the graph based on user feedback
    improve()
    return True


def remember_text(text: str, source: str = "user input") -> str:
    """Ingest raw text into the knowledge graph.
    
    Returns the ID of the ingested memory card.
    """
    memory_id = hashlib.sha1(text.encode()).hexdigest()[:12]
    memory_text = f"User submitted this information: {text}\nSource: {source}"
    
    if _CLOUD_OK:
        try:
            _cloud_remember(memory_text)
            _cloud_cognify(block=True)  # block so it's recallable immediately
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

    This is called automatically after remember() and on confirm_fix(). Cognee
    Cloud (this tenant) doesn't expose a separate memify/feedback endpoint —
    /api/v1/memify and /api/v1/feedback both 404 — so this re-runs cognify(),
    blocking, so the reinforced "confirmed N time(s)" text is re-indexed
    before the next recall.
    """
    result = {"status": "skipped", "detail": "local cache only"}

    if _CLOUD_OK:
        try:
            _cloud_cognify(block=True)
            result = {"status": "ok", "detail": "Cognee Cloud graph re-indexed"}
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
            _cloud_cognify(block=False)
            result = {"status": "ok", "detail": "Cognee Cloud cognify queued (runs in background)"}
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
    tombstones = data.setdefault("tombstones", {})
    for cid, card in list(data["cards"].items()):
        try:
            created = datetime.fromisoformat(card.get("created", ""))
            if created < cutoff:
                deleted.append(cid)
                if _CLOUD_OK:
                    for data_id in card.get("cloud_data_ids", []):
                        _cloud_delete_data(data_id)
                    tombstones[cid] = {"error": card["error"], "ts": datetime.now(timezone.utc).isoformat()}
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
    tombstones = data.setdefault("tombstones", {})
    for cid, card in list(data["cards"].items()):
        if error_class.lower() in card.get("error", "").lower():
            deleted.append(cid)
            if _CLOUD_OK:
                for data_id in card.get("cloud_data_ids", []):
                    _cloud_delete_data(data_id)
                tombstones[cid] = {"error": card["error"], "ts": datetime.now(timezone.utc).isoformat()}
            del data["cards"][cid]

    if deleted:
        _save_local(data)
    return len(deleted)


def forget_all() -> bool:
    """Wipe local cache and the Cognee dataset. Returns whether the cloud
    side actually confirmed deletion (local cache is always cleared either way)."""
    _save_local({"cards": {}})
    if _CLOUD_OK:
        try:
            return _cloud_delete_dataset()
        except Exception:
            return False
    return True


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
    """Pull a command out of a Cognee NL answer, else return text.

    Cognee's GRAPH_COMPLETION answers use either a fenced code block
    (```bash\ncmd\n```) or a single-backtick inline span (`cmd`) — handle
    both, fenced first since a naive single-backtick split mangles it
    (each ``` contains 3 backtick chars).
    """
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            block = parts[1]
            lines = [ln for ln in block.strip().splitlines() if ln.strip()]
            # first line may just be a language tag (e.g. "bash")
            if lines and lines[0].strip().isalpha() and len(lines) > 1:
                lines = lines[1:]
            if lines:
                return lines[0].strip()
    if "`" in text:
        parts = text.split("`")
        if len(parts) >= 2:
            return parts[1].strip()
    return text.strip().splitlines()[0][:200]
