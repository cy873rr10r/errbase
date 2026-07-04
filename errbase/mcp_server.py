"""
mcp_server.py — exposes errbase's memory lifecycle as MCP tools.

Lets an LLM agent (Claude Code, etc.) call remember/recall/improve directly
while it works, instead of a human typing `errbase ...` commands by hand.

Run:                        python3 -m errbase.mcp_server
Register with Claude Code:  claude mcp add errbase -- python3 -m errbase.mcp_server

Destructive bulk-wipe ops (forget --all / --before) are intentionally not
exposed here — errbase's own privacy principle is that nothing is deleted
without a human confirming. forget_class is included since it's scoped and
low-risk (matches errbase's existing tombstone safety net).
"""

from mcp.server.fastmcp import FastMCP

from . import cognee_brain as brain

mcp = FastMCP(
    "errbase",
    instructions=(
        "errbase gives you persistent memory of shell/terminal error fixes "
        "across sessions. MANDATORY: whenever a shell command fails, call "
        "recall_fix(error_text) BEFORE running any diagnostic commands "
        "yourself (ss, lsof, ps, journalctl, etc.) or proposing a fix. If it "
        "returns a known fix, use that instead of re-diagnosing from "
        "scratch. Only fall back to your own diagnosis if recall_fix "
        "returns 'No known fix'. After you fix a NEW error yourself (one "
        "recall_fix didn't know), call remember_fix to store it — but only "
        "after you've actually run the fix and confirmed the error is gone."
    ),
)


@mcp.tool()
def recall_fix(error_text: str) -> str:
    """Look up a known fix for a shell/terminal error, matched by meaning not exact text.
    Call this FIRST, before running any diagnostic commands, whenever a shell command fails."""
    result = brain.recall_fix(error_text)
    if not result:
        return f"No known fix for: {error_text}"
    return (
        f"Fix: {result['fix']}\n"
        f"Confirmed {result['confirms']} time(s). Source: {result['source']}"
    )


@mcp.tool()
def remember_fix(error_text: str, fix_command: str, system: str = "Linux") -> str:
    """Permanently store an error -> fix pair in the knowledge graph.

    IMPORTANT:
    - Only call this AFTER you have actually run fix_command and verified
      the error is resolved (e.g. re-ran the original failing command and
      it now succeeds). Do not call this for a fix you have only proposed
      or reasoned about but not executed and confirmed.
    - fix_command MUST be the literal, exact, copy-pasteable shell command
      you ran — NOT a prose description of the fix (NOT "find the process
      and kill it"). A future recall_fix() call returns this string
      verbatim as the fix to run, so it must be directly executable as-is.
    - Prefer a REUSABLE, general-purpose command over one tied to a
      one-off, ephemeral value like a PID. A PID is different every time a
      process starts, so "kill 153253" is worthless on the next occurrence
      of this exact same error. Use the general pattern instead:
        BAD:  "kill 153253"
        GOOD: "fuser -k 8123/tcp"
      Same idea for other ephemeral identifiers (container IDs, temp paths,
      timestamps) — store the general command, not the one-time value.
    - If recall_fix() returned a fix that turned out to be stale or wrong
      (e.g. it referenced a PID/ID that no longer applies), correct the
      memory instead of leaving it: call forget_class with a keyword from
      error_text, then remember_fix again with a corrected, reusable fix.
      Otherwise the same wrong fix keeps resurfacing every future session.
    """
    brain.store_fix(command="", error_text=error_text, fix_command=fix_command, system=system)
    return f"Learned: '{error_text}' -> '{fix_command}'"


@mcp.tool()
def confirm_fix(error_text: str, fix_command: str, system: str = "Linux") -> str:
    """Confirm a fix from recall_fix worked again — reinforces it so it ranks higher next time.

    Only call this after you actually ran fix_command this session and it
    resolved the error again. Do not call it just because a fix was recalled
    — recall alone doesn't prove it still works in the current context.

    Pass the SAME error_text you passed to recall_fix, verbatim, so this
    finds the right card — reinforcement fails silently-but-honestly (see
    return value) if the wording doesn't match closely enough.
    """
    found = brain.confirm_fix(error_text, fix_command, system)
    if found:
        return "Reinforced."
    return (
        "No matching stored fix found for that error_text — nothing was "
        "reinforced. Use remember_fix instead if this is actually a new fix."
    )


@mcp.tool()
def remember_note(text: str) -> str:
    """Ingest freeform text/notes into the knowledge graph (not an error/fix pair)."""
    mid = brain.remember_text(text, source="mcp-agent")
    return f"Remembered (id={mid})"


@mcp.tool()
def forget_class(error_class: str) -> str:
    """Delete stored errors/fixes matching a keyword, e.g. 'docker'. Scoped, not a full wipe."""
    n = brain.forget_class(error_class)
    return f"Deleted {n} card(s) matching '{error_class}'"


@mcp.tool()
def memory_stats() -> str:
    """See how many errors/fixes errbase currently knows, and which backend is active."""
    s = brain.stats()
    return (
        f"errors known: {s['errors_known']}, fixes stored: {s['fixes_stored']}, "
        f"confirmations: {s['total_confirmations']}, backend: {s['backend']}"
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
