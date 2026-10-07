# TheContrAIct web app

Next.js 16 (App Router) + TypeScript + Tailwind CSS. Talks to the FastAPI service via
the typed client in `packages/api-client`.

```bash
cp .env.example .env.local
pnpm dev            # http://localhost:3000
```

Auth modes (`NEXT_PUBLIC_AUTH_MODE`):

- `dev` — sign in with any email; the API must also run with `AUTH_MODE=dev`.
- `clerk` — real sign-in with Clerk. Set the Clerk keys here and `AUTH_MODE=clerk`,
  `CLERK_ISSUER`, `CLERK_JWKS_URL` on the API. Add `email` and `name` claims to the
  Clerk session token (see `services/api/app/auth.py`).
