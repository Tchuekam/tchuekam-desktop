"use strict"

/**
 * The install stamp tells a packaged app which commit and branch to clone on
 * first launch, so it has to name something that exists on the remote.  These
 * tests build throwaway repos with a local bare "origin" (no network) and check
 * what write-build-stamp.cjs decides to pin.
 */

const assert = require("node:assert/strict")
const { execFileSync } = require("node:child_process")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const { after, before, describe, test } = require("node:test")

const { resolveStamp } = require("./write-build-stamp.cjs")

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "build-stamp-test-"))
const savedEnv = {}
let counter = 0

before(() => {
  // Keep the developer's global git config (hooks, signing, aliases) out of it.
  for (const key of ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"]) savedEnv[key] = process.env[key]
  process.env.GIT_CONFIG_GLOBAL = path.join(scratch, "gitconfig")
  process.env.GIT_CONFIG_NOSYSTEM = "1"
})

after(() => {
  for (const [key, value] of Object.entries(savedEnv)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
  fs.rmSync(scratch, { recursive: true, force: true })
})

function git(cwd, ...args) {
  return execFileSync("git", ["-c", "user.name=test", "-c", "user.email=test@example.invalid", ...args], {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"]
  }).trim()
}

/** A work clone with one pushed commit on the default branch (main unless told otherwise). */
function fixture({ defaultBranch = "main" } = {}) {
  const root = path.join(scratch, `repo-${++counter}`)
  const origin = path.join(root, "origin.git")
  const work = path.join(root, "work")
  fs.mkdirSync(root, { recursive: true })
  git(root, "init", "--bare", "-b", defaultBranch, origin)
  git(root, "clone", origin, work)

  const commit = (file, content) => {
    fs.writeFileSync(path.join(work, file), content)
    git(work, "add", file)
    git(work, "commit", "-m", `${file}: ${content}`)
    return git(work, "rev-parse", "HEAD")
  }

  // The clone of an empty repo has an unborn HEAD; make sure it is the default branch.
  git(work, "symbolic-ref", "HEAD", `refs/heads/${defaultBranch}`)
  const a = commit("a.txt", "a")
  git(work, "push", "origin", defaultBranch)
  return { root, origin, work, a, commit }
}

function stampFor(work, env = {}) {
  const warnings = []
  const stamp = resolveStamp({ cwd: work, env, log: msg => warnings.push(msg) })
  return { stamp, warnings }
}

describe("local builds are pinned to something the remote has", () => {
  test("a pushed HEAD on main is pinned as is", () => {
    const { work, a } = fixture()
    const { stamp, warnings } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "main")
    assert.equal(stamp.dirty, false)
    assert.equal(stamp.source, "local")
    assert.deepEqual(warnings, [])
  })

  test("an unpushed commit pins its newest pushed ancestor", () => {
    const { work, a, commit } = fixture()
    commit("b.txt", "unpushed")
    const { stamp, warnings } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "main")
    assert.equal(stamp.dirty, true, "the packaged code differs from the pinned commit")
    assert.equal(stamp.treeDirty, false, "the working tree itself is clean")
    assert.equal(warnings.length, 1)
  })

  test("the newest pushed ancestor is looked for on every branch, not only the default one", () => {
    const { work, commit } = fixture()
    git(work, "checkout", "-b", "feat/x")
    const b = commit("b.txt", "pushed topic work")
    git(work, "push", "origin", "feat/x")
    commit("c.txt", "unpushed")
    const { stamp, warnings } = stampFor(work)
    assert.equal(stamp.commit, b)
    assert.equal(stamp.branch, "feat/x")
    assert.equal(stamp.dirty, true)
    assert.equal(warnings.length, 1)
  })

  test("the remote's default branch is read from its HEAD, not assumed to be main", () => {
    const { work, a } = fixture({ defaultBranch: "master" })
    // The commit is also on a branch that sorts before master in ls-remote's
    // output, so only knowing the default branch makes the stamp say "master".
    git(work, "push", "origin", "master:refs/heads/feat/y")
    const { stamp, warnings } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "master")
    assert.deepEqual(warnings, [])
  })

  test("a topic branch that was never pushed is replaced by main", () => {
    const { work, a, commit } = fixture()
    git(work, "checkout", "-b", "feat/never-pushed")
    commit("b.txt", "topic work")
    const { stamp } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "main")
  })

  test("a pushed topic branch is pinned by name", () => {
    const { work, commit } = fixture()
    git(work, "checkout", "-b", "feat/pushed")
    const b = commit("b.txt", "topic work")
    git(work, "push", "origin", "feat/pushed")
    const { stamp, warnings } = stampFor(work)
    assert.equal(stamp.commit, b)
    assert.equal(stamp.branch, "feat/pushed")
    assert.equal(stamp.dirty, false)
    assert.deepEqual(warnings, [])
  })

  test("a topic branch deleted on the remote after merging falls back to main", () => {
    const { work, origin, a, commit } = fixture()
    git(work, "checkout", "-b", "feat/merged-and-deleted")
    commit("b.txt", "topic work")
    git(work, "push", "origin", "feat/merged-and-deleted")
    // The remote deletes the branch (PR auto-delete); our remote-tracking ref
    // for it is now stale.
    git(origin, "branch", "-D", "feat/merged-and-deleted")
    const { stamp } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "main")
  })

  test("a commit only reachable from a pushed tag is pinned to that tag", () => {
    const { work, commit } = fixture()
    git(work, "checkout", "-b", "release-wip")
    const b = commit("b.txt", "release")
    git(work, "tag", "-a", "v9.9.9", "-m", "release")
    git(work, "push", "origin", "v9.9.9")
    const { stamp } = stampFor(work)
    assert.equal(stamp.commit, b)
    assert.equal(stamp.branch, "v9.9.9")
    assert.equal(stamp.dirty, false)
  })

  test("a clone that is behind the remote is not flagged", () => {
    const { root, origin, work, a } = fixture()
    // Someone else advances main on the remote; our clone has not fetched yet.
    const other = path.join(root, "other")
    git(root, "clone", origin, other)
    fs.writeFileSync(path.join(other, "c.txt"), "c")
    git(other, "add", "c.txt")
    git(other, "commit", "-m", "c")
    git(other, "push", "origin", "main")

    const { stamp, warnings } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "main")
    assert.equal(stamp.dirty, false)
    assert.deepEqual(warnings, [])
  })

  test("when origin can't be reached the refs of the last fetch are used, and the build says so", () => {
    const { root, work, a } = fixture()
    git(work, "remote", "set-url", "origin", path.join(root, "gone.git"))
    const { stamp, warnings } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "main")
    assert.equal(stamp.dirty, false)
    assert.equal(warnings.length, 1)
    assert.match(warnings[0], /last fetch/)
  })

  test("uncommitted edits are reported without moving the pin", () => {
    const { work, a } = fixture()
    fs.writeFileSync(path.join(work, "a.txt"), "edited")
    const { stamp } = stampFor(work)
    assert.equal(stamp.commit, a)
    assert.equal(stamp.dirty, true)
    assert.equal(stamp.treeDirty, true)
  })

  test("a checkout with no remote keeps its own ref and warns", () => {
    const root = path.join(scratch, `repo-${++counter}`)
    fs.mkdirSync(root, { recursive: true })
    git(root, "init", "-b", "main")
    fs.writeFileSync(path.join(root, "a.txt"), "a")
    git(root, "add", "a.txt")
    git(root, "commit", "-m", "a")
    const { stamp, warnings } = stampFor(root)
    assert.equal(stamp.commit, git(root, "rev-parse", "HEAD"))
    assert.equal(stamp.branch, "main")
    assert.equal(warnings.length, 1)
  })

  test("outside a git checkout there is nothing to stamp", () => {
    const empty = path.join(scratch, `empty-${++counter}`)
    fs.mkdirSync(empty, { recursive: true })
    assert.equal(stampFor(empty).stamp, null)
  })
})

describe("CI builds", () => {
  test("trust the checkout and name the ref that triggered the build", () => {
    const { work, a } = fixture()
    const { stamp, warnings } = stampFor(work, {
      GITHUB_ACTIONS: "true",
      GITHUB_REF_NAME: "v1.2.3",
      // workflow_dispatch builds of a tag report the dispatching branch's head
      // here, not the commit that was checked out.
      GITHUB_SHA: "0".repeat(40)
    })
    assert.equal(stamp.commit, a)
    assert.equal(stamp.branch, "v1.2.3")
    assert.equal(stamp.dirty, false)
    assert.equal(stamp.source, "ci")
    assert.deepEqual(warnings, [])
  })

  test("a workflow_dispatch build of a tag stamps the tag's commit, not the dispatching branch's head", () => {
    const { work, a, commit } = fixture()
    git(work, "checkout", "-b", "release")
    const tagged = commit("b.txt", "release")
    git(work, "tag", "v2.0.0")
    git(work, "checkout", "--detach", "v2.0.0")
    // What GitHub reports for a dispatch run: the branch it was dispatched on
    // and that branch's head, while the checkout is the tag.
    const { stamp } = stampFor(work, {
      GITHUB_ACTIONS: "true",
      GITHUB_REF_NAME: "main",
      GITHUB_SHA: a
    })
    assert.equal(stamp.commit, tagged)
    assert.equal(stamp.branch, "main")
    assert.equal(stamp.source, "ci")
  })
})
