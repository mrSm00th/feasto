# Feasto — Production-Grade Food Delivery Backend

117 endpoints across 15 domain modules, featuring PostGIS-powered restaurant discovery, Redis caching, Razorpay payments, WebSocket live tracking, and Celery-based background processing.

[![Live API](https://img.shields.io/badge/Live_API-Online-success?style=flat-square)](https://mrsmoothop-feasto.hf.space)
[![Swagger Docs](https://img.shields.io/badge/Docs-OpenAPI-blue?style=flat-square)](https://mrsmoothop-feasto.hf.space/docs)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-PostGIS-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-cache--aside-DC382D?style=flat-square&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)

---

## At a glance

| | |
|---|---|
| **117 endpoints** across 15 domain modules | **0% failures** — 100 concurrent users, 60s sustained (Locust) |
| **28× faster** on cache hit (72ms → 2.5ms via Redis) | **~3ms** PostGIS geo query on 10k-restaurant dataset |

---

## What makes this interesting (engineering decisions)

Most of these choices came from hitting a real problem, not applying a pattern upfront.

| Decision | Why |
|---|---|
| **PostGIS over Redis GEO** | `ST_DWithin` on a GIST index runs ~3ms and supports `JOIN` filters (cuisine, status, closures) in one query. Redis GEO can't join — that's multiple round trips. |
| **`SELECT FOR UPDATE` on checkout** | Two users checking out simultaneously would oversell. Row-level lock at the DB enforces correctness — not hoped for at the app layer. |
| **Append-only earnings ledger** | `RiderEarning` rows are never updated or deleted, only inserted. Audit trail stays complete. No race condition risk on financial writes. |
| **DB trigger for geo sync** | App never writes the `Geography` column directly. A trigger derives it from `lat`/`lon` on every write — can't drift out of sync across routes or migrations. |
| **Idempotency keys on webhooks** | Razorpay retries on slow responses. Each event is checked against a processed-events table before any status update — retries can't double-credit an order. |
| **Two-phase image upload** | Earlier version wrote the DB row before S3 upload finished — left menu items pointing at missing files. Now: upload verified first, DB row written only after object exists in storage. |
| **Two S3 buckets** | Menu/restaurant images → public bucket, static CDN URLs. KYC docs → private bucket, short-lived presigned URLs only. PII never accidentally public. |
| **Fallback dispatch tiers** | No timeout meant orders could sit unassigned. Celery Beat widens search radius after 30s and re-broadcasts — keeps widening until a rider accepts. |

---

## Architecture

![System architecture](assets/feasto_architecture_diagram.svg)

> PostgreSQL hosted on Supabase with PostGIS enabled. A DB trigger keeps the `Geography` column in sync with `lat`/`lon` — no application code involved. Migrations via Alembic.

---

## Caching

![Cache benchmark](assets/feasto_redis_cache_benchmark.svg)

Cache-aside on high-read endpoints. Soft failure design — Redis down means latency degrades, not availability.

| | Latency | Detail |
|---|---|---|
| Cache miss | ~72ms | DB ~28ms · serialize ~1ms · Redis write ~44ms |
| Cache hit | ~2.5ms | Redis lookup only · zero DB queries |
| **Speedup** | **28.8×** | |

**Cached:** restaurant detail · discovery feed · cuisine list · dish search  
**Never cached:** orders · cart · payments

| Key | TTL | Invalidated on |
|---|---|---|
| Restaurant detail | 60s | Update or pause |
| Discovery feed | 30s | Any restaurant state change |
| Cuisine list | 3600s | Admin tag change |
| Reviews | 300s | New review |

---

## Live order tracking

![Order tracking flow](assets/feasto_live_order_tracking_flow.svg)

Order placed → restaurant accepts → PostGIS dispatches nearest rider → WebSocket pushes rider location every 3–5s → customer sees live map. No polling, no page refresh.

Fallback: if no rider accepts within 30s, Celery Beat widens the search radius and re-broadcasts. Repeats until assigned.

---

## Module overview

117 endpoints distributed across these modules:

| Module | What it covers |
|---|---|
| **Auth & Users** | JWT access/refresh tokens · email OTP · secure-link password reset · RBAC (Customer / Owner / Rider / Admin) |
| **Restaurants** | Onboarding state machine `DRAFT → ACTIVE` · pause/resume · planned closures · multi-shift availability · cuisine tags |
| **Menus** | Category/item CRUD · archive-before-delete · reordering · Pillow image pipeline (JPEG + thumbnail) |
| **Orders & Carts** | Full lifecycle `AWAITING_PAYMENT → DELIVERED` · cart management · `SELECT FOR UPDATE` at checkout |
| **Payments** | Razorpay Orders API · signature-verified webhooks · COD · automatic refunds · idempotent processing |
| **Riders & Dispatch** | PII-encrypted KYC · private S3 storage · PostGIS geo-dispatch · live location · Celery Beat fallback tiers |
| **Discovery** | `ST_DWithin` geo feed · cursor pagination · cuisine filtering · city fallback · Redis 30s TTL |
| **Earnings & Payouts** | Append-only ledger · weekly Celery Beat batch payouts · per-restaurant commission rate |

15 modules total — the remaining 7 cover addresses, admins, locations, notifications, partner applications, reviews, and realtime WebSocket.

---

## Performance

Load tested with 100 concurrent users for 60 seconds using [Locust](https://locust.io/), sustaining 0% failures.

| Endpoint | RPS | p50 | Note |
|---|---|---|---|
| `GET /restaurants/{id}` | 6.3 | 32ms | Redis cache hit |
| `GET /restaurants/` | 3.7 | 35ms | Geo-discovery feed |
| `GET /orders` | 6.9 | 37ms | Authenticated |
| `GET /menu-categories` | 1.7 | 28ms | Public |

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
│   └── ...            # 8 more modules
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
| Payments & Email | Razorpay · Resend |

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

# Storage (Supabase S3-compatible)
STORAGE_BACKEND=local
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

# Email
RESEND_API_KEY=
MAIL_FROM=onboarding@resend.dev
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

Built by **Aditya Yadav** as a backend engineering portfolio project focused on system design, distributed systems concepts, geospatial search, caching, payments, and real-time communication.

[![GitHub](https://img.shields.io/badge/GitHub-mrSm00th-181717?style=flat-square&logo=github)](https://github.com/mrSm00th)