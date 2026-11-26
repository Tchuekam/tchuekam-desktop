# TchueKAM SaaS backend — capacity, tuning and runbook

How the backend behaves under load, what the knobs do, and how they constrain
each other. Every number below was measured on this codebase, not estimated;
the method is at the bottom so you can re-run it on your own instance size.

---

## 1. The one calculation that matters

Each gunicorn worker opens its **own** SQLAlchemy connection pool. So:

```
connections per instance = (TCHUEKAM_DB_POOL_SIZE + TCHUEKAM_DB_MAX_OVERFLOW) × WEB_CONCURRENCY
total connections        = connections per instance × number of instances
```

That total must stay under the Postgres server's `max_connections`, minus
headroom for migrations, backups and admin sessions (reserve ~10).

With the defaults (`10 + 10`, 4 workers), **one instance opens up to 80
connections**. Entry-level managed Postgres plans allow 100, so the defaults
fit exactly one instance. Scaling out requires one of:

| Option | When to use it |
|---|---|
| Raise the Postgres plan's `max_connections` | Simplest; most managed plans scale it with instance size |
| Lower `TCHUEKAM_DB_POOL_SIZE` / `MAX_OVERFLOW` per instance | Cheapest; costs per-instance throughput |
| Put **PgBouncer** in transaction mode in front | The real answer past ~4 instances |

`gunicorn.conf.py` logs the computed total at startup so nobody has to redo
this arithmetic:

```
TchueKAM API | workers=4 | connexions DB max pour cette instance = (20 par worker) × 4 = 80
```

### Worked examples

| Instances | Workers | Pool+overflow | Total conns | Fits `max_connections=100`? |
|---|---|---|---|---|
| 1 | 4 | 10+10 | 80 | yes (20 spare) |
| 2 | 4 | 10+10 | 160 | **no** — lower the pool or raise the plan |
| 2 | 4 | 5+5 | 80 | yes |
| 2 | 2 | 10+10 | 80 | yes |
| 4 | 4 | 10+10 | 320 | only with PgBouncer, or `max_connections≥350` |

---

## 2. Measured results

Hardware: 4 vCPU, 16 GB. Postgres 16, Redis 7, 4 gunicorn workers.

**The load generator ran on the same 4 vCPUs as the server** and consumed
~50% of one core. Server-side capacity on a dedicated instance is therefore
higher than the figures below. Treat these as a floor and re-measure on your
target instance (§6).

### 1000 concurrent users, 3 s think time

| Metric | Result |
|---|---|
| Offered load | 333 req/s |
| Achieved | **295 req/s** |
| Requests | 19 241 |
| Success (2xx) | **96.1%** |
| Shed (503) | 3.8% — fast rejection, see §4 |
| Server errors (5xx) | **0** |
| p50 / p95 / p99 | **130 ms / 631 ms / 882 ms** |
| CPU | 316% of 400% (79%) — server 202%, generator 50%, Postgres 23% |

Per-request cost is ≈ **6.8 ms of CPU**. That is the number to scale with:
333 req/s needs ≈ 2.3 vCPU of application CPU, so a dedicated 4-vCPU instance
carries 1000 users at this think time with headroom, and two instances give
both headroom and failover.

**Memory: 2 GB per instance** at 4 workers. Measured 132.6 MB resident per
worker (531 MB for four) plus up to 256 MB reserved by concurrent Argon2
hashing — about 790 MB peak. A 1 GB container leaves too little headroom once
the OS and a traffic spike are counted. Full figures in `docs/BENCHMARKS.md`.

**Useful operating range: ~50 concurrent in-flight requests per instance.**
That is where throughput peaks (406 req/s); beyond it latency climbs and
throughput slowly declines. Add instances rather than pushing one harder.

### Deliberate overload — 1000 users, no think time

1000 requests permanently in flight against a service with 80 slots. Nobody
uses a product this way; it is the shape of a traffic spike or a retry storm.

| Metric | Result |
|---|---|
| Served (2xx) | 8 429 (243 req/s of useful work) |
| Shed (503) | 1 232 |
| Server errors (5xx) | **0** |

The service keeps doing useful work and rejects the surplus. It does not
collapse (§4).

### Login path, measured separately

`/auth/signin` verifies Argon2id: ~100 ms CPU and 64 MiB **per in-flight
verification**.

| Concurrent logins | Throughput | p50 |
|---|---|---|
| 40 | 17.8 req/s | 2 117 ms |

This is the expected cost of a deliberately expensive function, and it is why
concurrent hashing is bounded (§5). Do not size the service for 1000
*simultaneous* logins — size it for 1000 *signed-in* users.

---

## 3. Why throughput used to collapse

Before this work, throughput peaked and then fell as concurrency rose:

| Concurrency | Throughput | p50 | Success |
|---|---|---|---|
| 10 | 182 req/s | 24 ms | 100% |
| 25 | 363 req/s | 31 ms | 100% |
| 50 | 311 req/s | 130 ms | 100% |
| 100 | 223 req/s | 157 ms | 98.5% |
| 200 | **15 req/s** | **10 s** | **55.8%** |

At 200 concurrent the service returned 500s while **the CPU was idle and no
SQL was executing**. A sampling profiler showed all 40 AnyIO worker threads
parked in `QueuePool._do_get`, waiting for a database connection.

The cause was two queues of different widths in series:

- FastAPI runs every `def` endpoint in the **AnyIO thread pool**, default
  width **40**.
- Each of those threads needs a **connection**, and the pool offered **20**.

Twenty threads were therefore guaranteed to wait, each burning the full
`pool_timeout` (10 s) before raising `TimeoutError` → HTTP 500. Meanwhile the
client had long given up, so the work was wasted and the slot had served
nobody. That is congestion collapse.

The trap: gunicorn's `threads` setting **does not apply to
`UvicornWorker`** — it is silently ignored. Setting it looked like a fix and
changed nothing. The AnyIO limiter can only be set from inside the process,
which `core/concurrency.py` now does during `lifespan`:

```
Pool de threads ajusté de 40 à 20 pour correspondre au pool de connexions
```

After aligning the two widths and adding admission control:

| Concurrency | Before | After |
|---|---|---|
| 100 | 223 req/s, 98.5% | 290 req/s, 99.97% |
| 200 | **15 req/s, 55.8%** | **373 req/s, 99.3%** |
| 400 | (collapse) | 481 req/s, surplus shed as 503 |

`test_thread_limit_does_not_exceed_connection_pool` pins this invariant.

---

## 4. Load shedding

`core/admission.py` admits at most `max_concurrent` requests, lets at most
`max_queued` more wait for at most `queue_timeout`, and returns **503** to the
rest without touching the database or the thread pool.

A service cannot process more than its capacity. It can only make the surplus
wait or refuse it. Waiting helps only while it is short; past that, refusing
*immediately* is strictly better — the caller can retry or degrade, and the
capacity stays available to admitted requests, whose latency does not rot.

- **503, not 429.** 429 means "you exceeded *your* quota". Here the caller did
  nothing wrong: the service is full. The distinction tells a client whether to
  slow down or simply retry.
- `queue_timeout` (3 s) is deliberately well under `pool_timeout` (10 s), so a
  request is refused *before* it can tie up a slot for ten seconds.
- Probe paths (`/health`, `/readyz`, `/livez`, `/metrics`) are exempt.
  Throttling probes would pull a healthy instance out of rotation exactly when
  it is busiest.

---

## 5. Login bursts

Argon2id reserves its memory cost per in-flight verification, so N concurrent
logins reserve N × 64 MiB. Neither existing protection bounds that: the
brute-force limiter is keyed **per email** (5 per 5 min) and the global quota
is **per IP**. A login burst spread across many addresses — a deploy, or
distributed credential stuffing — would saturate CPU and memory and starve
every other endpoint.

`core/security.py` therefore bounds concurrent hashing with a semaphore
(default: CPU count, capped at 8). Worst-case resident memory is
`slots × memory_cost`, which the default keeps at 256 MiB. On saturation it
raises `PasswordHashingBusy`, which is mapped to **503 + Retry-After**, never
to "wrong password" — reporting load as a credential failure would lock out
legitimate users and send them to reset a password that was correct.

---

## 6. Re-measuring on your instance

```bash
python scripts/loadtest.py --base-url https://api.example.com \
  --users 1000 --processes 4 --duration 60 --think-time 3
```

Use **`--processes`**. One Python process is GIL-bound to a single core and
saturates at a few hundred connections, at which point you are measuring the
client. The symptom is unambiguous: high latency while the *server* shows idle
CPU and no SQL in flight.

Two readings of "1000 concurrent users", both worth measuring:

- **1000 sessions** (`--think-time 3`) — a thousand signed-in users acting
  intermittently. This is a real product's load.
- **1000 in-flight requests** (`--think-time 0`) — nobody behaves this way,
  but it locates the saturation point and is what you size against.

Confusing the two leads to either under-provisioning or paying ten times over.

To find the plateau, sweep and watch for the point where throughput stops
rising:

```bash
for u in 25 50 100 200 400; do
  python scripts/loadtest.py --users $u --processes 4 --duration 20 --think-time 0
done
```

---

## 7. Reading the symptoms

| Symptom | Likely cause | Check |
|---|---|---|
| 500s with `QueuePool limit ... reached` | Thread pool wider than connection pool, or pool too small | `tchuekam_db_pool_connections{state="checked_out"}` at `pool_size+max_overflow` |
| One endpoint slow and holding connections, others fine | Deep `OFFSET` pagination — cost grows with the offset | `docs/BENCHMARKS.md` §7; use `before=` cursor pagination |
| 503 `SERVICE_OVERLOADED` | Admission control shedding — working as designed | `tchuekam_rate_limit_rejected_total{scope="admission_*"}`; add capacity |
| 503 on `/auth/signin` only | Hashing slots saturated | §5; raise `TCHUEKAM_PASSWORD_HASH_CONCURRENCY` only if RAM allows |
| 429 | Per-client quota | `RATE_LIMIT_GLOBAL_PER_MINUTE` |
| High latency, **idle CPU, no SQL running** | Serialisation, not saturation | `py-spy dump --pid <worker>`; see §3 |
| Quota ~N× too permissive | No Redis — each worker has its own counters | `/readyz` → `redis.available`; startup logs a warning |
| WebSocket events reach only some clients | No Redis pub/sub backplane | same as above |
| `/metrics` numbers look like a fraction of traffic | `PROMETHEUS_MULTIPROC_DIR` unset | One worker's view; `gunicorn.conf.py` sets it |
| Worker killed, `Worker ... tué après Ns` | Pool starvation or a blocking call in the event loop | `/readyz`, then `py-spy` |

---

## 8. Environment variables

### Sizing

| Variable | Default | Notes |
|---|---|---|
| `WEB_CONCURRENCY` | `min(2×cores+1, 8)` | Set by most PaaS. Multiplies connection use |
| `TCHUEKAM_DB_POOL_SIZE` | `10` | Per worker |
| `TCHUEKAM_DB_MAX_OVERFLOW` | `10` | Per worker, on top of pool size |
| `TCHUEKAM_DB_POOL_TIMEOUT` | `10` | Seconds. SQLAlchemy's 30 s default outlives the client |
| `TCHUEKAM_DB_POOL_RECYCLE` | `1800` | Below PgBouncer/Postgres idle timeouts |
| `TCHUEKAM_WORKER_THREADS` | pool+overflow | **Keep ≤ pool+overflow** (§3) |
| `TCHUEKAM_MAX_CONCURRENT_REQUESTS` | thread limit | Admitted at once, per worker |
| `TCHUEKAM_MAX_QUEUED_REQUESTS` | 2× concurrent | Allowed to wait |
| `TCHUEKAM_QUEUE_TIMEOUT_SECONDS` | `3.0` | Keep below `pool_timeout` |

### Required in production

| Variable | Notes |
|---|---|
| `ENVIRONMENT` | `production`. Enables JSON logs, disables docs, requires the JWT secret |
| `TCHUEKAM_DATABASE_URL` | `postgres://…` is normalised, driver named explicitly |
| `TCHUEKAM_JWT_SECRET_KEY` | ≥32 chars. Startup **fails** without it |
| `ALLOWED_ORIGINS` | Explicit list. `*` with credentials lets any site read authenticated responses |
| `REDIS_URL` | Without it quotas, revocation, cache and WebSocket fan-out are per-worker |
| `TCHUEKAM_TRUSTED_PROXY_COUNT` | `1` behind one LB. `0` (default) ignores `X-Forwarded-For`, which is client-controlled |

### Behaviour

| Variable | Default | Notes |
|---|---|---|
| `TCHUEKAM_RATE_LIMIT_ENABLED` | on in production | |
| `RATE_LIMIT_GLOBAL_PER_MINUTE` | `120` | Per client identity |
| `TCHUEKAM_ADMISSION_ENABLED` | on | Disabling restores collapse under overload |
| `TCHUEKAM_RBAC_CACHE_TTL` | `30` | Seconds. `0` disables; bounds staleness of a revoked permission |
| `TCHUEKAM_PASSWORD_HASH_CONCURRENCY` | `min(cores, 8)` | × `memory_cost` = worst-case RAM |
| `TCHUEKAM_ARGON2_MEMORY_KIB` | `65536` | Lower only knowingly; weakens hashing |
| `TCHUEKAM_WS_MAX_CONNECTIONS_PER_USER` | `10` | |
| `TCHUEKAM_WS_MAX_CONNECTIONS_TOTAL` | `5000` | Per worker |
| `TCHUEKAM_LOG_LEVEL` | `INFO` | |
| `TCHUEKAM_SQL_ECHO` | off | Logs every statement **and its parameters** — personal data in logs |
| `ENABLE_API_DOCS` | off in production | Exposes every route and schema unauthenticated |
| `TCHUEKAM_METRICS_ENABLED` | on | |

---

## 9. Deploy checklist

1. **Migrations run before the server.** `python scripts/db_migrate.py` takes a
   Postgres advisory lock, so running it from every instance's start command is
   safe: one migrates, the others wait and boot on the migrated schema. In
   production the app refuses to create tables itself — N workers racing on
   `CREATE TABLE` would, and it would mask a forgotten migration.
2. **`/readyz` as the health check, not `/health`.** It fails while starting,
   while draining, and when the database is unreachable — the three cases where
   traffic should go elsewhere. `/livez` deliberately ignores the database: a
   liveness probe that failed on a database incident would restart every worker,
   which repairs nothing and deepens the outage with a reconnect storm.
3. **Shutdown grace > `graceful_timeout` (25 s).** Render's
   `maxShutdownDelaySeconds`, Kubernetes' `terminationGracePeriodSeconds`. Too
   short and in-flight requests are killed mid-response.
4. **`REDIS_URL` set.** Without it the startup log warns, and quotas,
   revocation, cache invalidation and WebSocket fan-out are all per-worker.
5. **`TCHUEKAM_TRUSTED_PROXY_COUNT` matches your topology.** Too low and every
   client shares one quota bucket (the load balancer's address); too high and
   callers can spoof their address via `X-Forwarded-For` and bypass the quota.
6. **Check the arithmetic in §1** against your Postgres plan before raising
   `WEB_CONCURRENCY` or the instance count.
