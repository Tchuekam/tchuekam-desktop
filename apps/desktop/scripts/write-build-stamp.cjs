"use strict"

/**
 * Writes apps/desktop/build/install-stamp.json with the git ref the desktop
 * .exe should pin to at first-launch bootstrap time.  This file ships inside
 * the packaged app via electron-builder's extraResources entry and is read
 * by electron/main.cjs to drive the install.ps1 stage bootstrap flow.
 *
 * Schema (subject to bump via STAMP_SCHEMA_VERSION):
 *   {
 *     "schemaVersion": 1,
 *     "commit":        "<40-char SHA>",
 *     "branch":        "<branch or tag name>",
 *     "builtAt":       "<ISO 8601 UTC timestamp>",
 *     "dirty":         true|false,
 *     "source":        "ci" | "local"
 *   }
 *
 * The stamp is only useful if a user's machine can clone it.  A build made from
 * a local checkout used to pin whatever HEAD and branch happened to be checked
 * out, so a build from an unpushed commit or a topic branch that was never
 * pushed (or was deleted after merging) made first-launch setup fail for every
 * user.  Local builds now pin a commit that exists on `origin`: HEAD itself
 * when it has been pushed, otherwise the newest ancestor that has.
 *
 * Source preference order:
 *   1. CI (GitHub Actions) -- the checkout came from the remote by definition.
 *   2. Local `git` against the parent repo (../..), verified against `origin`.
 *
 * Dev / out-of-repo builds without git produce an explicit error rather than
 * silently writing an unstamped manifest -- the packaged app refuses to
 * bootstrap without a stamp.
 */

const fs = require("fs")
const path = require("path")
const { execFileSync } = require("child_process")

const STAMP_SCHEMA_VERSION = 1
const REMOTE = "origin"
const LS_REMOTE_TIMEOUT_MS = 20000

const DESKTOP_ROOT = path.resolve(__dirname, "..")
const REPO_ROOT = path.resolve(DESKTOP_ROOT, "..", "..")
const OUT_DIR = path.join(DESKTOP_ROOT, "build")
const OUT_FILE = path.join(OUT_DIR, "install-stamp.json")

function git(args, cwd, opts) {
  try {
    return execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      // Never block a build on a credentials prompt for a private remote.
      env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
      ...opts
    }).trim()
  } catch {
    return null
  }
}

function isAncestor(commit, tip, cwd) {
  try {
    // Exit 0 = ancestor.  Non-zero covers both "not an ancestor" and "tip isn't
    // present locally", and neither lets us claim the commit is on the remote.
    execFileSync("git", ["merge-base", "--is-ancestor", commit, tip], { cwd, stdio: "ignore" })
    return true
  } catch {
    return false
  }
}

// The commits worth testing for a remote ref: its live tip and, for a branch,
// where our remote-tracking ref last saw it.  The live tip is often not in this
// clone (the remote moved since the last fetch), but the tracking ref is, and a
// commit under it is on the remote unless the branch was force-pushed.
function localShas(tip, cwd) {
  const shas = [tip.sha]
  const branch = /^refs\/heads\/(.+)$/.exec(tip.ref)
  if (branch) {
    const tracked = git(["rev-parse", "--verify", "--quiet", `refs/remotes/${REMOTE}/${branch[1]}^{commit}`], cwd)
    if (tracked && tracked !== tip.sha) shas.push(tracked)
  }
  return shas
}

function containsCommit(tip, commit, cwd) {
  return localShas(tip, cwd).some(sha => isAncestor(commit, sha, cwd))
}

/**
 * What the remote advertises: { defaultBranch, tips: [{ sha, ref }], live }.
 * `git ls-remote` is authoritative (a branch deleted upstream is gone from it
 * even if a stale remote-tracking ref lingers locally) but needs the network;
 * when it fails, `live` is false and the answer comes from the remote-tracking
 * refs of the last fetch.  Returns null when there is no usable remote at all.
 */
function readRemote(cwd) {
  if (git(["remote", "get-url", REMOTE], cwd) === null) return null

  const live = git(["ls-remote", "--symref", REMOTE, "HEAD", "refs/heads/*", "refs/tags/*"], cwd, {
    timeout: LS_REMOTE_TIMEOUT_MS
  })
  if (live) {
    let defaultBranch = null
    const tips = []
    for (const line of live.split("\n")) {
      const symref = /^ref: refs\/heads\/(\S+)\tHEAD$/.exec(line)
      if (symref) {
        defaultBranch = symref[1]
        continue
      }
      const [sha, ref] = line.split("\t")
      // Annotated tags list the tag object and, peeled with ^{}, its commit.
      if (sha && ref && ref !== "HEAD") tips.push({ sha, ref: ref.replace(/\^\{\}$/, "") })
    }
    return { defaultBranch: defaultBranch || "main", tips, live: true }
  }

  const tracked = git(["for-each-ref", "--format=%(objectname) %(refname)", `refs/remotes/${REMOTE}`], cwd)
  if (!tracked) return null
  const prefix = `refs/remotes/${REMOTE}/`
  const tips = tracked
    .split("\n")
    .map(line => line.split(" "))
    .filter(([, ref]) => ref && ref !== `${prefix}HEAD`)
    .map(([sha, ref]) => ({ sha, ref: `refs/heads/${ref.slice(prefix.length)}` }))
  const headRef = git(["symbolic-ref", "--short", `refs/remotes/${REMOTE}/HEAD`], cwd)
  return { defaultBranch: headRef ? headRef.slice(REMOTE.length + 1) : "main", tips, live: false }
}

/**
 * The branch or tag on the remote that contains `commit`, by a name
 * `git clone --branch` accepts, or null if none does.  The default branch wins
 * when it contains the commit: topic branches get deleted after merging, the
 * default branch does not.
 */
function holderRef(commit, remote, cwd) {
  const { defaultBranch, tips } = remote
  const defaultTip = tips.find(t => t.ref === `refs/heads/${defaultBranch}`)
  if (defaultTip && containsCommit(defaultTip, commit, cwd)) return defaultBranch

  const holder = tips.find(t => containsCommit(t, commit, cwd))
  return holder ? holder.ref.replace(/^refs\/(heads|tags)\//, "") : null
}

/**
 * Pin `commit` to something a user's machine can clone.
 *
 * Returns { commit, branch, pushed, live }.  `pushed` is false when `commit`
 * itself is not on the remote and an older commit that is was pinned instead, so
 * the caller can flag the stamp (the packaged code then differs from the pin).
 * `live` is false when the remote could not be reached and the answer comes from
 * the refs of the last fetch.  Returns null when the remote can't be consulted
 * at all; the caller keeps its own ref.
 */
function pinToRemote(commit, cwd) {
  const remote = readRemote(cwd)
  if (!remote) return null

  const branch = holderRef(commit, remote, cwd)
  if (branch) return { commit, branch, pushed: true, live: remote.live }

  // Not on the remote at all (unpushed, or its branch is gone): walk back to the
  // newest commit that is, on any of its refs.  Each ref's merge-base with the
  // commit is a pushed ancestor; of those keep one that descends from the rest.
  const bases = new Set()
  for (const tip of remote.tips) {
    for (const sha of localShas(tip, cwd)) {
      const base = git(["merge-base", commit, sha], cwd)
      if (base) bases.add(base)
    }
  }
  if (bases.size === 0) return null

  const newest = git(["merge-base", "--independent", ...bases], cwd)
  const base = newest ? newest.split("\n")[0] : [...bases][0]
  const baseBranch = holderRef(base, remote, cwd)
  return baseBranch ? { commit: base, branch: baseBranch, pushed: false, live: remote.live } : null
}

function fromCI(cwd, env) {
  if (env.GITHUB_ACTIONS !== "true" && !env.GITHUB_SHA) return null
  // The checkout is authoritative: for workflow_dispatch builds of a tag,
  // GITHUB_SHA is the dispatching branch's head, not the tag's commit.
  const sha = git(["rev-parse", "HEAD"], cwd) || env.GITHUB_SHA
  if (!sha) return null
  return {
    commit: sha,
    branch: env.GITHUB_REF_NAME || env.GITHUB_HEAD_REF || null,
    dirty: false, // CI builds from a checkout-of-ref by definition
    source: "ci"
  }
}

function fromLocalGit(cwd, log) {
  const sha = git(["rev-parse", "HEAD"], cwd)
  if (!sha) return null
  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
  // `git status --porcelain -uno` is empty iff tracked files match HEAD.
  // We exclude untracked files (-uno) intentionally: a developer who's
  // checked out an installer scratch dir alongside the repo shouldn't
  // poison every local build with a [DIRTY] stamp.  We DO care about
  // tracked-but-modified files because those mean the .exe content
  // differs from the commit being pinned.
  const status = git(["status", "--porcelain", "-uno"], cwd)
  const treeDirty = status !== null && status.length > 0

  const stamp = {
    commit: sha,
    branch: branch === "HEAD" ? null : branch, // detached HEAD -> null
    dirty: treeDirty,
    treeDirty, // not part of the written stamp: main() words its warning by it
    source: "local"
  }

  const pinned = pinToRemote(sha, cwd)
  if (!pinned) {
    log(
      `WARNING: could not check ${REMOTE} for ${sha.slice(0, 12)}.\n` +
        "  If that commit or branch is not pushed, first-launch setup will fail for users."
    )
    return stamp
  }

  if (!pinned.live) {
    log(
      `WARNING: could not reach ${REMOTE}; checked against the refs from your last fetch.\n` +
        "  A branch deleted on the remote since then would not be noticed."
    )
  }

  stamp.branch = pinned.branch
  if (!pinned.pushed) {
    log(
      `WARNING: ${sha.slice(0, 12)} is not on ${REMOTE}.\n` +
        `  Pinning ${pinned.commit.slice(0, 12)}, the newest ancestor that is, so users can clone it.\n` +
        "  Push your commits before publishing this build."
    )
    stamp.commit = pinned.commit
    stamp.dirty = true // the packaged code differs from the pinned commit
  }
  return stamp
}

/**
 * Decide what to stamp.  Exposed for tests; `env` and `cwd` are injectable.
 */
function resolveStamp({ cwd = REPO_ROOT, env = process.env, log = msg => console.warn("[write-build-stamp] " + msg) } = {}) {
  return fromCI(cwd, env) || fromLocalGit(cwd, log)
}

function main() {
  const stamp = resolveStamp()
  if (!stamp || !stamp.commit) {
    console.error(
      "[write-build-stamp] ERROR: could not determine git commit.\n" +
        "  - $GITHUB_SHA not set\n" +
        "  - `git rev-parse HEAD` failed at " +
        REPO_ROOT +
        "\n" +
        "Packaged builds require a git ref to pin first-launch install.ps1\n" +
        "against. Run from a git checkout or set $GITHUB_SHA explicitly."
    )
    process.exit(1)
  }

  // Only for real uncommitted edits: a stamp flagged dirty because an unpushed
  // commit was replaced by a pushed ancestor has already said so.
  if (stamp.treeDirty) {
    console.warn(
      "[write-build-stamp] WARNING: working tree is dirty.\n" +
        "  Pinning to " +
        stamp.commit.slice(0, 12) +
        " but the packaged code may differ from that commit.\n" +
        "  Commit your changes before publishing this build."
    )
  }

  const payload = {
    schemaVersion: STAMP_SCHEMA_VERSION,
    commit: stamp.commit,
    branch: stamp.branch,
    builtAt: new Date().toISOString(),
    dirty: stamp.dirty,
    source: stamp.source
  }

  fs.mkdirSync(OUT_DIR, { recursive: true })
  fs.writeFileSync(OUT_FILE, JSON.stringify(payload, null, 2) + "\n", "utf8")
  console.log(
    "[write-build-stamp] wrote " +
      path.relative(REPO_ROOT, OUT_FILE) +
      " -> " +
      stamp.commit.slice(0, 12) +
      (stamp.branch ? " (" + stamp.branch + ")" : "") +
      (stamp.dirty ? " [DIRTY]" : "")
  )
}

if (require.main === module) {
  main()
}

module.exports = { resolveStamp }
