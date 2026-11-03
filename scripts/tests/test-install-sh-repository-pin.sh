#!/bin/bash
# Tests for how install.sh's clone_repo handles a pinned commit.
#
#   bash scripts/tests/test-install-sh-repository-pin.sh [path/to/install.sh]
#
# The desktop app stamps each build with the commit and branch it was built
# from, and its first launch asks install.sh to clone exactly that.  A branch
# that was never pushed (or was deleted after the PR merged) used to fail the
# whole install, so the app could never finish its first-launch setup.
#
# These run the real clone_repo (lifted out of install.sh) against a throwaway
# local "origin", so they need git but no network.  Pass a path to run them
# against another copy of the script, e.g. an older revision.

set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install_script="${1:-$here/../install.sh}"
[ -f "$install_script" ] || { echo "Could not locate install.sh at $install_script"; exit 1; }

# The test keeps git's global config (and so the developer's ~/.gitconfig) out of
# it with GIT_CONFIG_GLOBAL, which git only honours from 2.32; the fixture also
# needs `git init -b` (2.28).  Refuse to run on older git rather than touch them.
git_version="$(git --version | sed -E 's/^git version ([0-9]+\.[0-9]+).*/\1/')"
git_major="${git_version%%.*}"
git_minor="${git_version##*.}"
if [ "$git_major" -lt 2 ] || { [ "$git_major" -eq 2 ] && [ "$git_minor" -lt 32 ]; }; then
    echo "SKIP: needs git >= 2.32 (found $git_version)"
    exit 0
fi

failures=0
assert_eq() {  # expected actual label
    if [ "$1" = "$2" ]; then
        echo "OK: $3"
    else
        echo "FAIL: $3"
        echo "  expected: $1"
        echo "  actual:   $2"
        failures=$((failures + 1))
    fi
}

# Lift the functions under test out of install.sh (tr: tolerate CRLF checkouts).
extract_function() {  # name
    tr -d '\r' < "$install_script" | awk -v name="$1" '
        $0 ~ "^" name "\\(\\) \\{" { printing = 1 }
        printing { print }
        printing && /^}/ { exit }'
}
helpers="$(extract_function clone_into_install_dir)"
clone_repo_src="$(extract_function clone_repo)"
[ -n "$clone_repo_src" ] || { echo "clone_repo not found in $install_script"; exit 1; }
eval "$helpers"
eval "$clone_repo_src"

LOG=""
log_info()    { :; }
log_success() { :; }
log_error()   { LOG="$LOG
ERR: $*"; }
log_warn()    { echo "WARN: $*" >> "$warn_log"; }

root="$(mktemp -d)"
warn_log="$root/warnings.log"
trap 'rm -rf "$root"' EXIT

# clone_repo / git commands below must not touch the real git config.
export GIT_CONFIG_GLOBAL="$root/gitconfig"
export GIT_TERMINAL_PROMPT=0
git_t() { git -c user.name=test -c user.email=test@example.invalid "$@"; }

# main:  A
# topic: A -> B       (pushed; also tagged v1)
# C:     a local-only commit that origin has never seen
origin="$root/origin.git"
seed="$root/seed"
git init -q --bare -b main "$origin"
git clone -q "$origin" "$seed" 2>/dev/null
echo a > "$seed/f.txt"
git_t -C "$seed" add f.txt
git_t -C "$seed" commit -q -m A
git_t -C "$seed" branch -M main
git_t -C "$seed" push -q origin main 2>/dev/null
commit_a="$(git -C "$seed" rev-parse HEAD)"
git_t -C "$seed" checkout -q -b topic
echo b > "$seed/f.txt"
git_t -C "$seed" commit -q -am B
git_t -C "$seed" push -q origin topic 2>/dev/null
commit_b="$(git -C "$seed" rev-parse HEAD)"
echo c > "$seed/f.txt"
git_t -C "$seed" commit -q -am "C (never pushed)"
commit_c="$(git -C "$seed" rev-parse HEAD)"

REPO_URL_SSH="$root/no-such-remote.git"
REPO_URL_HTTPS="$origin"

run_scenario() {  # branch commit dir  -> sets $status and $head
    BRANCH="$1" INSTALL_COMMIT="$2" INSTALL_DIR="$3"
    : > "$warn_log"
    # install.sh runs under `set -e`; do the same so a failed git call aborts.
    ( set -e; clone_repo ) >/dev/null 2>&1
    status=$?
    head="$(git -C "$3" rev-parse HEAD 2>/dev/null || true)"
}

echo
echo "-- commit pinned, branch no longer on the remote --"
run_scenario gone-topic "$commit_b" "$root/t1"
assert_eq 0 "$status" "install succeeds"
assert_eq "$commit_b" "$head" "checkout lands on the pinned commit"

echo
echo "-- commit pinned but never pushed, branch exists --"
run_scenario topic "$commit_c" "$root/t2"
assert_eq 0 "$status" "install succeeds"
assert_eq "$commit_b" "$head" "falls back to the branch tip"
assert_eq 1 "$(grep -c "$commit_c" "$warn_log")" "warns that the pinned commit is unavailable"

echo
echo "-- commit pinned but never pushed, branch gone too --"
run_scenario gone-topic "$commit_c" "$root/t3"
assert_eq 0 "$status" "install succeeds"
assert_eq "$commit_a" "$head" "stays on the remote's default branch"

echo
echo "-- no pin: branch clone still honours --branch --"
run_scenario topic "" "$root/t4"
assert_eq 0 "$status" "install succeeds"
assert_eq "$commit_b" "$head" "checks out the requested branch"
assert_eq topic "$(git -C "$root/t4" rev-parse --abbrev-ref HEAD)" "on that branch, not detached"

echo
echo "-- re-running over an existing install --"
run_scenario main "$commit_a" "$root/t5"
assert_eq "$commit_a" "$head" "first run pins A"
run_scenario main "$commit_b" "$root/t5"
assert_eq 0 "$status" "update succeeds"
assert_eq "$commit_b" "$head" "update moves to the new pin"
run_scenario gone-topic "$commit_a" "$root/t5"
assert_eq 0 "$status" "update with a deleted branch succeeds"
assert_eq "$commit_a" "$head" "update follows the pin, not the branch"

echo
echo "-- a pin the remote has, but the checkout fails for a real reason --"
run_scenario main "$commit_a" "$root/t6"
assert_eq "$commit_a" "$head" "first run pins A"
echo "local edit" > "$root/t6/f.txt"
run_scenario main "$commit_b" "$root/t6"
assert_eq 1 "$([ "$status" -ne 0 ] && echo 1 || echo 0)" "the failed checkout aborts the install instead of being papered over"
assert_eq 0 "$(grep -c 'not available from the remote' "$warn_log")" "no false 'not available from the remote' warning"
assert_eq "$commit_a" "$head" "the checkout is left where it was"

echo
echo "-- re-running over an install whose local branch is behind the remote --"
run_scenario main "" "$root/t7"
assert_eq "$commit_a" "$head" "first run installs main at A"
git_t -C "$seed" checkout -q main
echo d > "$seed/f.txt"
git_t -C "$seed" commit -q -am D
git_t -C "$seed" push -q origin main 2>/dev/null
commit_d="$(git -C "$seed" rev-parse HEAD)"
run_scenario main "$commit_c" "$root/t7"
assert_eq 0 "$status" "update with an unpushed pin succeeds"
assert_eq "$commit_d" "$head" "falls back to the CURRENT branch tip, not a stale local branch"

echo
if [ "$failures" -gt 0 ]; then
    echo "FAILED: $failures assertion(s) failed"
    exit 1
fi
echo "All repository-pin tests passed."
