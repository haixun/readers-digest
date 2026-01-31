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

3. Run Prisma migrations:

```bash
npx prisma migrate dev --name init
```

4. Start the dev server:

```bash
npm run dev
```

## Supabase auth
- Configure email auth in Supabase.
- Login via `/login` and use email magic link.
