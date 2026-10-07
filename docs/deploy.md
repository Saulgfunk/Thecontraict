# Putting TheContrAIct online (free)

This sets up a real, public copy of the app using free plans. No credit card is needed for
any of them. You sign up to each service with your GitHub account and copy a few values
from one to the other. Allow about 30–45 minutes the first time.

| Piece                | Service                                  | Free plan notes                                                     |
| -------------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| Sign-in (accounts)   | [Clerk](https://clerk.com)               | Up to 10,000 users a month                                          |
| Database (and files) | [Neon](https://neon.tech)                | 0.5 GB: thousands of contracts                                      |
| API (the "engine")   | [Render](https://render.com)             | Sleeps after 15 minutes unused; the next visit takes up to a minute |
| Website              | [Vercel](https://vercel.com)             | Fast, always on                                                     |
| Hourly reminders     | GitHub Actions (already in your account) | Runs the reminders every hour                                       |

> **Never paste keys or passwords into a chat.** Each value below goes straight from one
> service's dashboard into another's settings.

Keep a scratch note open (on your own computer) to hold the values as you go:
`CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_ISSUER`, `DATABASE_URL`, `API_URL`,
`APP_URL`, `CRON_SECRET`.

---

## Step 0 — Choose the branch

The deploys build from GitHub. Either merge the work into `main` first (recommended: the
hourly reminders only run from the default branch), or pick the branch
`claude/adoring-gates-62sotg` wherever a service asks for a branch.

## Step 1 — Clerk (sign-in)

1. Go to [clerk.com](https://clerk.com) → **Sign up** (with GitHub).
2. **Create application**. Name: `TheContrAIct`. Sign-in options: **Email** (and
   **Google** if you like). → **Create application**.
3. You land on a page showing two keys. Copy them to your note:
   - **Publishable key** (starts `pk_test_`) → `CLERK_PUBLISHABLE_KEY`
   - **Secret key** (starts `sk_test_`) → `CLERK_SECRET_KEY`
4. Open **Configure → API keys** (or **Domains**) and copy the **Frontend API URL**
   (looks like `https://something-something-12.clerk.accounts.dev`) → `CLERK_ISSUER`.
5. Open **Configure → Sessions → Customize session token → Edit**, paste exactly this, and
   **Save**:

   ```json
   {
     "email": "{{user.primary_email_address}}",
     "name": "{{user.full_name}}"
   }
   ```

   (The app needs the email in the sign-in token to know who is calling.)

## Step 2 — Neon (database)

1. Go to [neon.tech](https://neon.tech) → **Sign up** (with GitHub).
2. **Create project**. Name: `thecontraict`. Postgres version: the newest offered. Region:
   pick the one closest to your users (e.g. **AWS Europe Central (Frankfurt)**).
3. On the project dashboard click **Connect**. Make sure **Connection pooling** is
   **off**, then copy the connection string (starts `postgresql://`, ends
   `sslmode=require…`) → `DATABASE_URL`.

## Step 3 — Render (API)

1. Go to [render.com](https://render.com) → **Get started** (with GitHub). Allow it access
   to the `thecontraict` repository.
2. **New → Blueprint** → choose the repository (and the branch from Step 0).
3. Render reads `render.yaml` and asks for three values:
   - `DATABASE_URL` → from your note
   - `CLERK_ISSUER` → from your note
   - `APP_URL` → `https://thecontraict.vercel.app` (the website address you will get in
     Step 4; if Vercel gives you a different one, change it here afterwards)
4. **Apply**. The first build takes 5–10 minutes. When it says **Live**, copy the service's
   address at the top (like `https://thecontraict-api.onrender.com`) → `API_URL`.
5. Check it: open `API_URL/health` in your browser. It should show `{"status":"ok"}`.
6. In the service's **Environment** tab, reveal **CRON_SECRET** and copy it →
   `CRON_SECRET`.

If the log says _"The database role bypasses Row-Level Security"_, the database user cannot
keep organizations' data apart safely; the app refuses to run rather than risk it. Tell
Claude and it will help you fix it.

## Step 4 — Vercel (website)

1. Go to [vercel.com](https://vercel.com) → **Sign up** (with GitHub, Hobby plan).
2. **Add New… → Project** → **Import** the `thecontraict` repository.
3. **Project Name**: `thecontraict`. **Root Directory**: click **Edit** and choose
   `apps/web`. Framework: Next.js (detected).
4. Open **Environment Variables** and add these four:

   | Name                                | Value                |
   | ----------------------------------- | -------------------- |
   | `NEXT_PUBLIC_API_URL`               | your `API_URL`       |
   | `NEXT_PUBLIC_AUTH_MODE`             | `clerk`              |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | your publishable key |
   | `CLERK_SECRET_KEY`                  | your secret key      |

5. **Deploy**. When it finishes, copy the address (like `https://thecontraict.vercel.app`)
   → `APP_URL`. If you used the branch rather than `main`, set it under **Settings → Git →
   Production Branch** and redeploy.
6. If `APP_URL` is not exactly what you typed in Render in Step 3, update it in Render
   (**Environment** → `APP_URL` → **Save**; Render redeploys by itself).

## Step 5 — Hourly reminders (GitHub)

1. On GitHub, open the repository → **Settings → Secrets and variables → Actions**.
2. **Variables** tab → **New repository variable**: Name `API_URL`, value your `API_URL`.
3. **Secrets** tab → **New repository secret**: Name `CRON_SECRET`, value your
   `CRON_SECRET`.
4. Test it: **Actions** tab → **Scheduled jobs** → **Run workflow**. It should finish
   green with `{"sent":…}` in the log.

## Step 6 — Try it

Open your `APP_URL`, click **Open the app**, **Sign up** with your email, create your
organization, and add a contract (or the sample).

## What to know

- **First visit after a quiet spell is slow** (up to a minute) because the free API
  sleeps. The app shows "Starting up…" meanwhile. A paid Render plan ($7/month) removes this.
- **Emails are not sent yet**: reminders appear in the app (bell icon). To send emails,
  add an email service later (e.g. Resend or Postmark) and set `EMAIL_BACKEND` and its
  keys in Render.
- **AI is off** until you add `ANTHROPIC_API_KEY` in Render's environment.
- **Clerk shows a small "Development mode" badge** on the sign-in box. That goes away when
  you switch Clerk to a production instance, which needs your own domain name
  (e.g. `app.yourfirm.com`).
- **Updates deploy themselves**: every push to the branch rebuilds the API and website.
