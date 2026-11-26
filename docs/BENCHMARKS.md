# TchueKAM — benchmark baseline

Recorded baseline for the platform. The point of writing numbers down is to
make regressions visible: re-run the harness after a change and compare.

Reproduce with:

```bash
python scripts/benchmark.py --json bench.json
```

**Reference hardware:** 4 vCPU, 16 GB RAM. PostgreSQL 16 and Redis 7 on the
same host, 4 gunicorn workers, pool 10+10 per worker.

**The load generator shares those 4 vCPUs with the server** and takes roughly
half a core. Server-side capacity on a dedicated instance is higher than what
is recorded here. Treat these as a floor, and re-measure on the instance size
you actually deploy (`docs/CAPACITY.md` §6).

Recorded: 2026-11-26.

---

## 1. Headline

| | |
|---|---|
| Throughput plateau | **406 req/s** at concurrency 50 |
| Load shedding begins | concurrency 100 |
| **Server errors (5xx) across the whole sweep (25 → 400)** | **0** |
| 1000 concurrent users, 3 s think time | 295 req/s, 96.1% 2xx, p99 882 ms |
| Cold boot to first `/readyz` 200 | **1.15 s** |
| Graceful drain on SIGTERM | 0.97 s |
| Resident memory, 4 workers | 531 MB, +256 MB worst-case hashing |
| Hot-path queries lacking an index | **none** |

The zero is the number that matters. Before this work the same sweep returned
500s from concurrency 100 upward and throughput fell to 15 req/s at 200
(`docs/CAPACITY.md` §3). Overload now produces fast 503s instead of errors.

---

## 2. Per-endpoint latency, concurrency 1

No queueing at concurrency 1, so this is each endpoint's own cost. 100
iterations after two warm-up calls.

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| `GET /health` | 0.52 ms | 0.72 ms | 1.48 ms |
| `GET /readyz` | 3.10 ms | 4.50 ms | 6.02 ms |
| `GET /api/v1/users/me` | 5.15 ms | 7.68 ms | 15.58 ms |
| `GET /api/v1/users/me/devices` | 6.08 ms | 8.38 ms | 11.28 ms |
| `GET /api/v1/organizations` | 6.65 ms | 10.32 ms | 14.63 ms |
| `GET /api/v1/audit/logs?limit=20` | 7.14 ms | 10.29 ms | 11.33 ms |
| `GET /api/v1/audit/logs?limit=100` | 10.04 ms | 13.33 ms | 14.79 ms |

Reading it:

- `/health` touches nothing. At 0.52 ms it is the floor — the cost of the ASGI
  stack, middleware chain and JSON serialisation.
- `/readyz` is 6× that because it makes two SQL round trips plus a Redis ping.
  Appropriate for a readiness probe, and it is exempt from rate limiting and
  admission control so a busy instance can still answer it.
- Authenticated endpoints land at 5–7 ms. Two of those milliseconds are the
  session and user lookups every authenticated request performs; the rest is
  the endpoint's own query. RBAC adds nothing measurable once cached.
- `audit/logs` scales with `limit` (7.1 ms at 20, 10.0 ms at 100) — row
  serialisation, not query planning.

---

## 3. Concurrency sweep

Closed loop (no think time): N requests permanently in flight. This finds the
saturation point; it is not how a product is used.

| Concurrency | req/s | p50 | p95 | p99 | 2xx | shed 503 | **5xx** |
|---|---|---|---|---|---|---|---|
| 25 | 352.3 | 42 ms | 175 ms | 220 ms | 100% | 0 | **0** |
| 50 | **406.1** | 52 ms | 378 ms | 438 ms | 100% | 0 | **0** |
| 100 | 355.5 | 198 ms | 631 ms | 760 ms | 99.74% | 15 | **0** |
| 200 | 323.0 | 533 ms | 1397 ms | 2237 ms | 98.22% | 90 | **0** |
| 400 | 296.8 | 845 ms | 3686 ms | 5422 ms | 90.40% | 500 | **0** |

Honest reading:

- The plateau is **406 req/s at concurrency 50**. Past it, latency rises and
  throughput *declines* — 297 req/s at 400, about 27% below plateau.
- That decline is real, not noise. Admission control stops the collapse but
  does not make throughput flat: the shed path still costs work, and queued
  requests occupy capacity before being served. 27% under a 8× overload is a
  very different thing from the 96% collapse this replaced, but it is not
  free.
- p99 reaches 5.4 s at concurrency 400. Those are admitted requests waiting
  behind the queue. 400 in-flight requests against a 406 req/s service is 8×
  the sustainable rate; the correct response to that regime is more capacity,
  not more tuning.
- **Useful operating range: up to ~50 concurrent in-flight requests per
  instance.** Above that, add instances.

### 1000 concurrent users, 3 s think time

The realistic shape — a thousand signed-in users acting intermittently.

| | |
|---|---|
| Offered | 333 req/s |
| Achieved | 295 req/s |
| 2xx | 96.1% |
| Shed 503 | 3.8% |
| 5xx | 0 |
| p50 / p95 / p99 | 130 / 631 / 882 ms |
| CPU | 316% of 400% (79%) |

Per-request cost ≈ **6.8 ms CPU**. That is the figure to scale with.

---

## 4. Memory

| | |
|---|---|
| Per worker, resident | 132.6 MB |
| 4 workers | 530.7 MB |
| Worst-case concurrent Argon2 hashing | +256.0 MB |
| **Peak** | **~790 MB** |

Resident memory did not move measurably between idle and after 400 requests
(132.6 → 132.6 MB), so there is no per-request leak on the read path.

**Sizing:** a 1 GB container leaves ~200 MB of headroom over the peak, which
is thin once the OS, page cache and a traffic spike are accounted for. **2 GB
per instance** at 4 workers. To fit 1 GB, reduce `WEB_CONCURRENCY` or
`TCHUEKAM_PASSWORD_HASH_CONCURRENCY` — the hashing figure is
`slots × memory_cost` and is reserved only while logins are in flight, but it
is reserved all at once when they are.

---

## 5. Boot and shutdown

| | |
|---|---|
| Cold boot to first `/readyz` 200 | 1.15 s (min 1.13, max 1.19) |
| Graceful drain on SIGTERM | 0.97 s |

Tight and consistent, which matters in three places: rolling deploys, restart
after a crash, and autoscale responsiveness.

Boot includes the Python import (§6), the Alembic revision check, the RBAC
seed under its advisory lock, and the Redis subscriber starting. Drain under
1 s means `maxShutdownDelaySeconds: 40` and `graceful_timeout: 25` are
generous — deliberately, since those budgets must cover in-flight requests
under load, not an idle shutdown.

---

## 6. Import time

Measured in a fresh subprocess, since an import only happens once per process.

| Module | median |
|---|---|
| `tchuekam_backend.main` | 942 ms |
| `run_agent` | 681 ms |
| `model_tools` | 570 ms |
| `cli` | 237 ms |

The backend figure is paid once per worker boot and is the bulk of the 1.15 s
cold start. The agent figures are the latency a CLI user feels on **every**
invocation, which is the more interesting target: `model_tools` at 570 ms is
tool discovery, and `run_agent` at 681 ms is the agent core.

---

## 7. Database

Against a realistically-sized dataset — plans on empty tables are meaningless,
because every strategy looks fast on zero rows.

Seeded: 2000 users, 4012 sessions, **50 000 audit logs**, 50 organizations,
2000 memberships, 150 workspaces.

| Hot-path query | time | index-served |
|---|---|---|
| auth: session by primary key | 0.024 ms | yes |
| auth: user by primary key | 0.015 ms | yes |
| signin: user by email | 0.014 ms | yes |
| rbac: roles of a user | 0.032 ms | yes |
| rbac: permissions of a user | 0.244 ms | yes |
| devices: active sessions of a user | 0.031 ms | yes |
| refresh: session by refresh-token hash | 0.020 ms | yes |
| organizations: memberships of a user | 0.030 ms | yes |
| audit: first page | 0.371 ms | yes |

**Verdict: no hot-path query needs an index.** The schema's indexing is
correct, including the composite unique constraints that serve the RBAC joins
as index-only scans.

The harness only flags sequential scans on tables of 1000 rows or more. A seq
scan over the 7-row `roles` table is the *optimal* plan — it fits in one page
— and flagging it would bury the signal under permanent false positives.

### Pagination is the one real cliff

`OFFSET n` makes the engine read and discard n rows:

| Offset | time | rows read then discarded |
|---|---|---|
| 0 | 0.10 ms | 100 |
| 1 000 | 1.32 ms | 1 100 |
| 10 000 | 5.36 ms | 10 100 |
| 40 000 | 18.65 ms | 40 100 |

Linear, at ~0.45 ms per thousand rows skipped. `audit_logs` only ever grows:
at a few million rows — what a thousand users produce in months — one deep
request would hold a pool connection for seconds, and a handful would exhaust
a pool of a few dozen. That is the same starvation mode that caused the
collapse in §3, reachable from a single query parameter.

Two changes followed:

- `offset` on `/api/v1/audit/logs` is capped at 10 000.
- `before` / `after` were added, giving cursor pagination on the indexed
  `created_at`. At the same depth where `OFFSET 40000` costs 15.44 ms reading
  40 100 rows, `before=<that instant>` costs **0.09 ms reading 100 rows** —
  **172× faster**, and flat at any depth. Use it for exports and full history
  walks.

---

## 8. Web bundle

The product served at `/` is `apps/desktop/dist-web` (per `vercel.json`,
everything but `/api/*` and `/docs/*`).

| | |
|---|---|
| Total dist | 32 MB |
| JavaScript | 23.2 MB across 89 chunks |
| **First-load transfer (gzip)** | **381.8 KB** |
| Largest chunk | `vendor-shiki` — 18.1 MB raw, 3.1 MB gzip |

First load is three eager chunks — the entry, the rolldown runtime and
`studio-design-agent` (638 KB raw / 188 KB gzip). **382 KB gzipped for first
paint is healthy** for an app of this size.

Worth attention: `vendor-shiki` is **18.1 MB raw, 3.1 MB gzipped** — 80% of
all JavaScript in one chunk. It is dynamically imported, so it does not block
first paint; it is reached through a preload manifest when a route that needs
syntax highlighting loads. But that is 3.1 MB over the wire for the first user
who opens such a view, and syntax highlighting is core to a chat and code
product, so most sessions will pay it. The usual cause is Shiki bundling every
language grammar and theme; restricting the language and theme set, or using
its fine-grained bundle, is where the win is.

Good already:

- Assets are content-hashed, and `vercel.json` serves `/assets/*` with
  `max-age=31536000, immutable` — so the 3.1 MB is paid once per release.
- 89 chunks means route-level code splitting is working.

Not done: no precompressed `.gz`/`.br` artifacts. Fine on Vercel, which
compresses at the edge; it matters if these files are ever served from
another static host.

---

## 9. What to watch for in a re-run

| Metric | Baseline | Investigate if |
|---|---|---|
| 5xx across the sweep | 0 | **anything above 0** |
| Plateau throughput | 406 req/s @ 50 | below ~350 req/s |
| `users/me` p50 @ concurrency 1 | 5.15 ms | above ~10 ms |
| Cold boot | 1.15 s | above ~3 s |
| Resident per worker | 132.6 MB | above ~200 MB, or idle ≠ post-traffic |
| `needs_an_index` | none | **non-empty** |
| First-load bundle (gzip) | 381.8 KB | above ~600 KB |
