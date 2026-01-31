# Readers Digest (Next.js)

## Setup

1. Install dependencies:

```bash
cd web
npm install
```

2. Configure environment variables:

```bash
cp .env.example .env.local
```

> If your network is IPv4-only, use the Supabase **Session Pooler** connection string for `DATABASE_URL`.

3. Run Prisma migrations:

```bash
npx prisma migrate deploy
```

4. Start the dev server:

```bash
npm run dev
```

## Supabase auth
- Configure email auth in Supabase.
- Login via `/login` and use email magic link.

## Admins
- Set `ADMIN_EMAILS` (comma-separated) to allow editing the global prompt.

## Cron
- Set `CRON_SECRET` in Vercel and send it as `x-cron-secret` header to `/api/ingest/refresh`.
