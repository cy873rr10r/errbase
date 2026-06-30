# errbase.plugin.zsh — auto-capture failed commands and learn their fixes.
#
# Install (zinit):   zinit load yourgithub/errbase
# Install (manual):  source /path/to/errbase.plugin.zsh
#
# What it does:
#   - On a non-zero exit, shows a known fix (if any) — silent on first sight.
#   - Remembers the FAILED command + its stderr.
#   - When the NEXT command SUCCEEDS, offers to link it as the fix — with your
#     permission. Nothing is stored or run without a 'y'.
#
# Privacy: stderr is captured to a temp file only for the last command, and is
# discarded immediately. errbase never auto-executes anything.

ERRBASE_CMD=${ERRBASE_CMD:-errbase}
typeset -g __errbase_last_cmd=""
typeset -g __errbase_last_err=""
typeset -g __errbase_pending=0     # 1 = we just saw a failure, awaiting a fix
typeset -g __errbase_stderr_file="${TMPDIR:-/tmp}/errbase_stderr.$$"

# Capture the command about to run, and tee its stderr.
__errbase_preexec() {
  __errbase_last_cmd="$1"
  # Redirect stderr of the running command into a temp file (and still show it).
  exec 2> >(tee "$__errbase_stderr_file" >&2)
}

__errbase_precmd() {
  local exit_code=$?

  # Restore stderr.
  exec 2>&1

  if [[ $exit_code -ne 0 && -n "$__errbase_last_cmd" ]]; then
    # A command just failed.
    __errbase_last_err="$(tail -c 2000 "$__errbase_stderr_file" 2>/dev/null)"
    [[ -z "$__errbase_last_err" ]] && __errbase_last_err="$__errbase_last_cmd"

    # Show a known fix (silent if none).
    "$ERRBASE_CMD" capture "$exit_code" "$__errbase_last_cmd" "$__errbase_last_err" 2>/dev/null

    __errbase_pending=1

  elif [[ $exit_code -eq 0 && $__errbase_pending -eq 1 && -n "$__errbase_last_cmd" ]]; then
    # A command SUCCEEDED right after a failure → candidate fix.
    # Ask permission before learning. (Skip trivial commands.)
    case "$__errbase_last_cmd" in
      ls|cd*|clear|pwd|errbase*|"") ;;  # ignore noise
      *)
        print -P "%F{99}errbase%f did the last command fix it? learn it? %F{244}[y/N]%f "
        read -k 1 reply
        echo
        if [[ "$reply" == "y" || "$reply" == "Y" ]]; then
          "$ERRBASE_CMD" fix "$__errbase_last_err" "$__errbase_last_cmd" 2>/dev/null
        fi
        ;;
    esac
    __errbase_pending=0
  fi

  rm -f "$__errbase_stderr_file" 2>/dev/null
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec __errbase_preexec
add-zsh-hook precmd  __errbase_precmd

# Convenience: `eb "<error>"` to recall a fix manually.
eb() { "$ERRBASE_CMD" recall "$*"; }
