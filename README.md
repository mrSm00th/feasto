# Feasto — Food Delivery Backend

A FastAPI backend with **117 REST endpoints across 15 domain modules**, covering restaurant discovery, ordering, payments, rider dispatch, and earnings — built as a portfolio project to work through real backend engineering problems: geospatial search, concurrency control, payment webhook handling, and real-time tracking.

[![Live API](https://img.shields.io/badge/Live_API-Online-success?style=flat-square)](https://mrsmoothop-feasto.hf.space)
[![Swagger Docs](https://img.shields.io/badge/Docs-OpenAPI-blue?style=flat-square)](https://mrsmoothop-feasto.hf.space/docs)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-PostGIS-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-cache--aside-DC382D?style=flat-square&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)

---

## Engineering decisions worth reading

These are the parts of the build with an actual story behind them — a problem hit, a wrong first attempt, and why the final approach won.

| Decision | Why |
|---|---|
| **Geo search: Haversine → bounding box → PostGIS** | Started by computing Haversine distance in Python after pulling all riders — couldn't use an index, didn't scale. Moved to a SQL bounding-box pre-filter to shrink the candidate set before precise distance math. Final version: `ST_DWithin`/`ST_Distance` on a GIST-indexed `Geography` column — filtering and distance both happen in one indexed query. Redis GEO was evaluated as a potential future optimization for extreme scale, but not built: at this scale, PostGIS handles the load, and Redis GEO would need multiple round-trips to replicate the combined geo + relational filters (cuisine, status, closures) that PostGIS does in one query. |
| **DB trigger for geo sync** | App code only ever writes `lat`/`lon`. A Postgres trigger derives the `Geography` point on every insert/update, so the spatial column can't drift out of sync regardless of which code path writes to the table. |
| **`SELECT FOR UPDATE` on rider assignment & payout batching** | Two riders accepting the same order at once was a real race — first solved by locking the order row so the second request correctly fails. Same pattern reused when sweeping pending earnings into a payout batch, so two batch runs can't double-pay. (There's no inventory/stock concept in this schema — this lock is not used at checkout.) |
| **Append-only earnings ledger** | `RiderEarning`/`RestaurantEarning` rows are inserted as `PENDING` and later swept into a batch as `PAID_OUT` — never edited in place. Corrections happen via a `REVERSED` compensating entry, not by mutating history. Standard pattern for financial audit trails. |
| **Razorpay webhook: signature verification + status-guard idempotency** | HMAC-SHA256 verification on the raw body before parsing, since anyone could otherwise POST to the endpoint pretending to be Razorpay. Razorpay retries webhooks on slow responses, so each handler checks `if payment.status == PAID: return` before applying an update — a retried delivery can't double-process a payment. |
| **Upload-then-write image pipeline with cleanup on failure** | Files are uploaded to S3 first; the DB row is written only after that succeeds. If the DB commit then fails, the uploaded objects are explicitly deleted so storage doesn't accumulate orphaned files pointing at nothing. |
| **Two S3 buckets, split by access policy** | Menu/restaurant images go to a public bucket served as static URLs. Rider KYC documents go to a private bucket, accessible only via short-lived presigned URLs generated for an authorized admin review — PII is never reachable by a public URL. |
| **Square-crop vs. aspect-preserving image resizing** | Profile and menu photos are square-cropped for consistent thumbnails. KYC documents (ID cards, licenses) use bounds-only resizing with no crop — cropping a license photo to a square would risk cutting off the actual content. |
| **Two-tier dispatch radius + one-shot timeout cancellation** | `dispatch_order_to_riders` tries a default search radius, and immediately retries once at a wider radius in the same call if no riders are found — both attempts are synchronous, not scheduled. Separately, a Celery task is scheduled *before* dispatch even runs (so it fires even if dispatch throws) and auto-cancels the order if it's still unassigned after a timeout window. |
| **Cursor-based pagination on the restaurant discovery feed** | Offset pagination breaks under concurrent inserts (skipped/duplicated rows) and slows down as the `OFFSET` grows. The discovery endpoint in the `restaurants` module uses a compound `(sort_value, id)` cursor instead — stable and O(1) regardless of page depth. |
| **Polymorphic reviews with a DB-level invariant** | One `Review` table covers customer→rider, customer→restaurant, and rider→customer reviews, with a `CHECK` constraint guaranteeing exactly one target column is populated, matching `reviewee_type`. |
| **Commission rate snapshotting** | Each `RestaurantEarning` row stores the commission rate that applied *at the time of that order*, not a live reference to the platform's current rate — so historical earnings stay correct even if the commission rate changes later. |

---

## Architecture

![System architecture](assets/feasto_architecture_diagram.svg)

PostgreSQL hosted on Supabase with PostGIS enabled. A DB trigger keeps the `Geography` column in sync with `lat`/`lon` — no application code involved. Migrations via Alembic.

---

## Caching

Cache-aside on high-read, slightly-stale-tolerant endpoints. Soft-failure design: if Redis is unreachable, requests fall back to the database — latency degrades, availability doesn't.

**Cached:** restaurant detail · discovery feed · cuisine list · dish search
**Never cached:** orders · cart · payments — anything financial or live stays uncached by design.

| Key | TTL | Invalidated on |
|---|---|---|
| Restaurant detail | 60s | Update or pause |
| Discovery feed | 30s | Any restaurant state change |
| Cuisine list | 3600s | Admin tag change |
| Reviews | 300s | New review |

The discovery feed gets the shortest TTL despite being the highest-traffic endpoint — deliberately, because it's also the most volatile data (restaurant status, availability) of anything cached here.

**Measured cache performance** (logged via `time.perf_counter()` in the cache layer, restaurant detail endpoint with a seeded dataset):

| | Latency | Breakdown |
|---|---|---|
| Cache miss | ~72ms | DB ~25ms · serialization ~1ms · Redis write ~44ms |
| Cache hit | ~2.5ms | Redis lookup only · zero DB queries |
| **Speedup** | **~28×** | |

Measured locally using a seeded dataset and averaged across repeated runs.

---

## Live order tracking

![Order tracking flow](assets/feasto_live_order_tracking_flow.svg)

Order placed → restaurant accepts → PostGIS dispatches nearest available riders → WebSocket pushes rider location updates → customer sees live map. No polling.

If no rider accepts in time, a Celery task (scheduled at dispatch time, independent of whether dispatch itself succeeds) auto-cancels the unassigned order after a timeout window.

---

## Module overview

117 endpoints across 15 modules:

| Module | What it covers |
|---|---|
| **users** | JWT access/refresh tokens · email OTP · secure-link password reset · RBAC (Customer / Owner / Rider / Admin) |
| **restaurants** | Onboarding state machine `DRAFT → ACTIVE` · pause/resume · planned closures · multi-shift availability · cuisine tags |
| **menus** | Category/item CRUD · archive-before-delete · reordering · Pillow image pipeline (JPEG + thumbnail, square-crop vs. aspect-preserving) |
| **orders** | Full order lifecycle `AWAITING_PAYMENT → DELIVERED` · status transitions · order history |
| **carts** | Cart management, item additions/removals, quantity updates ahead of checkout |
| **payments** | Razorpay Orders API · HMAC-verified webhooks · status-guard idempotency · COD · automatic refunds |
| **riders** | Rider profiles · Fernet-encrypted KYC fields · private S3 storage · PostGIS geo-dispatch · live location updates · append-only earnings ledger · Celery Beat batch payouts |
| **rider_applications** | Multi-step rider onboarding state machine with resumable steps · PII encryption at rest · KYC document upload to private S3 · designed integration seam for third-party verification vendor (webhook-based, not yet wired to a live provider) |
| **partner_applications** | Restaurant partner onboarding flow · `DRAFT → ACTIVE` progression |
| **reviews** | Polymorphic review table (customer↔restaurant, customer↔rider) · `CHECK` constraint enforcing exactly one target column per row |
| **addresses** | Customer address management tied to order delivery |
| **admins** | Platform-level controls · restaurant activation · KYC document review via short-lived presigned URLs |
| **locations** | City/area data backing discovery feed and dispatch radius logic |
| **notifications** | Notification dispatch tied to order and dispatch lifecycle events |
| **realtime** | WebSocket layer for live order status and rider location push to customers |

---

## What's intentionally not built

Two integrations were designed as a seam but not wired to a live vendor — worth saying plainly rather than implying they're complete:

- **KYC verification vendor** — the async-job-plus-webhook shape is designed into the rider onboarding flow, but no live third-party verification provider is connected.
- **RazorpayX payouts** — payout batching computes and records what's owed; actual bank transfer via RazorpayX is not wired up.

---

## Load test results

Tested with [Locust](https://locust.io/) against `localhost:8000` — 100 concurrent users, 60 seconds sustained. 1,150 total requests across all endpoints, **0 failures (0%)**.

| Endpoint | Requests | Median | p95 | RPS |
|---|---|---|---|---|
| `GET /api/orders` | 402 | 37ms | 680ms | 6.9 |
| `GET /api/restaurants/` (discovery) | 235 | 35ms | 480ms | 3.7 |
| `GET /api/restaurants/[id]` | 401 | 32ms | 1200ms | 6.3 |
| `GET /api/restaurants/[id]/menu-categories` | 87 | 28ms | 590ms | 1.7 |
| **Aggregated** | **1,150** | **35ms** | **1400ms** | **18.6** |

**0 failures across all endpoints.**

One honest observation worth noting: `POST /api/users/token` has a median of ~2400ms under load. This is expected — bcrypt hashing is deliberately CPU-intensive by design (that's the point of a password hashing algorithm under concurrent load), and login endpoints are not a throughput target. All data endpoints stay well under 40ms median.

Benchmarked locally on shared hardware — Postgres, Redis, and FastAPI all running on the same machine, competing for the same CPU. Take these as a baseline, not a ceiling.

---

## Project structure

Module-first layout — each domain owns its models, routes, schemas, and services.

```
app/
├── core/              # config, auth, encryption, shared utilities
├── db/                # session, model registry
├── modules/
│   ├── users/         # auth, JWT, roles
│   ├── restaurants/   # onboarding, availability, cuisines
│   ├── menus/         # categories, items, images
│   ├── orders/        # checkout, order lifecycle
│   ├── payments/      # Razorpay, webhooks
│   ├── riders/        # profiles, earnings, payouts
│   ├── realtime/      # WebSocket order tracking
│   └── ...            # remaining modules
└── main.py
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Backend | FastAPI · SQLAlchemy (async) · Alembic · Celery Beat · Pydantic v2 |
| Database | PostgreSQL · PostGIS · GeoAlchemy2 · Supabase |
| Cache | Redis · Upstash |
| Storage | Supabase S3 · boto3 · Pillow |
| Payments & Email | Razorpay · Brevo (SMTP via aiosmtplib) |
| Deploy | Docker · Hugging Face Spaces |

---

## Try it

Three roles available against the live API:

| Role | Email | Password |
|---|---|---|
| Customer | `customer@feasto.dev` | `demo1234` |
| Restaurant Owner | `owner@feasto.dev` | `demo1234` |
| Rider | `rider@feasto.dev` | `demo1234` |

**Authenticate in Swagger:** `POST /api/users/token` with credentials above → copy `access_token` → click **Authorize** → paste as `Bearer {token}`

---

## Run locally

```bash
docker build -t feasto .
docker run --env-file .env -p 8000:8000 feasto
```

Requires PostgreSQL (with PostGIS) and Redis. Docs at `http://localhost:8000/docs`.

<details>
<summary>Environment variables</summary>

```bash
# Database
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname

# Auth
SECRET_KEY=replace-with-a-long-random-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Razorpay
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

# Storage (supports both S3 and S3-compatible providers)
STORAGE_BACKEND=s3
S3_PUBLIC_BUCKET_NAME=feasto-public
S3_PRIVATE_BUCKET_NAME=feasto-private
S3_REGION=ap-south-1
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=

# Redis / Celery
REDIS_URL=redis://localhost:6379/1
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Email (Brevo SMTP via aiosmtplib)
# Fill in your actual credentials
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
BREVO_SMTP_LOGIN=
BREVO_SMTP_PASSWORD=
MAIL_FROM=noreply@yourdomain.com
MAIL_FROM_NAME=Feasto

# PII encryption
PII_ENCRYPTION_KEY=

# Frontend (password-reset links)
FRONTEND_URL=http://localhost:3000
```

Full config with defaults in `app/core/config.py`.
</details>

---

## Author

Built by **Aditya Yadav** as a backend engineering portfolio project focused on system design, geospatial search, caching, payments, and real-time communication.

[![GitHub](https://img.shields.io/badge/GitHub-mrSm00th-181717?style=flat-square&logo=github)](https://github.com/mrSm00th)