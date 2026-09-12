# DSA Tracker

A full-stack web app to manage DSA (Data Structures & Algorithms) practice questions
and track student progress — built from the PRD, end-to-end.

- **Frontend:** React + Vite + Tailwind CSS
- **Backend:** Django + Django REST Framework
- **Database:** SQLite (dev) — schema is Postgres/Supabase-compatible
- **Auth:** Existing Django JWT username/password login plus Google OAuth through Supabase Auth

Read **`docs/NOTES.md`** for a full explanation of every algorithm, pattern, and
technique used in this project — that's the file to read before your scrum call
or a code review.

---

## Quick Start

### 1. Backend (Django)

```bash
cd backend
pip install -r requirements.txt --break-system-packages   # or use a venv
python manage.py migrate
python manage.py seed_demo        # optional: creates demo admin + 3 students + 9 questions
python manage.py runserver 127.0.0.1:8000
```

Demo accounts created by `seed_demo`:

| Role    | Username          | Password        |
|---------|-------------------|-----------------|
| Admin   | saikrishnathumma  | Saikkrrcb123#   |
| Student | rahul             | Student@123     |
| Student | priya             | Student@123     |
| Student | arjun             | Student@123     |

> Only **one** admin account is allowed. New signups always get `role=user`.

### Proof of work flow

1. Admin creates questions with **Title, Description, Examples, Pre-requisites, Difficulty** (no problem link).
2. Students solve locally, post on LinkedIn, and submit the LinkedIn post URL from **My Assigned Questions**.
3. Admin opens **Proof Validation**, reviews the LinkedIn post, and clicks **Validate**.
4. The student dashboard shows **YOUR SOLUTION HAS BEEN VALIDATED** with a Validated badge.

### 2. Frontend (React)

```bash
cd frontend
npm install
cp .env.example .env      # points the frontend at http://127.0.0.1:8000/api
npm run dev
```

Open the printed local URL (usually `http://localhost:5173`).

---

## Project Structure

```
dsa-tracker/
├── backend/
│   ├── dsatracker/          # Django project (settings, urls, wsgi)
│   ├── core/                 # The single Django app
│   │   ├── models.py          # Profile, Question, Assignment
│   │   ├── serializers.py     # DRF serializers incl. analytics payloads
│   │   ├── views.py           # ViewSets + analytics APIViews
│   │   ├── permissions.py     # RBAC permission classes
│   │   ├── filters.py         # django-filter FilterSets
│   │   ├── signals.py         # auto-create Profile on User creation
│   │   ├── admin.py           # Django admin registration
│   │   └── management/commands/seed_demo.py
│   └── manage.py
├── frontend/
│   └── src/
│       ├── api/axios.js       # axios instance + JWT auto-refresh interceptor
│       ├── context/AuthContext.jsx
│       ├── routes/ProtectedRoute.jsx
│       ├── components/        # Navbar, QuestionCard, Badges, ActivityStats, ...
│       └── pages/              # Login, Register, UserDashboard, AdminDashboard
└── docs/
    └── NOTES.md               # Detailed algorithm/technique explanations
```

## Google OAuth via Supabase

The login page retains the existing username/password form and adds
**Continue with Google**. The browser uses Supabase Auth with the public
publishable/anon key, then sends its Supabase access token to Django. Django
verifies that token directly with Supabase before it links the verified email
to an existing user or creates a new student account. Django then issues the
same application JWTs used by password login.

Roles never come from React, Google, or Supabase user metadata. They stay in
the server-side `Profile.role` field. A new Google user is always a student;
an existing admin retains admin access only because their existing Django
profile is already an admin. Removed students are retained as inactive local
profiles and cannot re-enter through Google with the same email or linked
Supabase identity.

Copy the example environment files, fill in the Supabase publishable key in
both environments, and register `/auth/callback` in Supabase Auth. See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the exact variables and Google
Cloud/Supabase redirect settings.

## Deployment

See [the production deployment guide](docs/DEPLOYMENT.md) for Supabase
PostgreSQL, Render, and Vercel configuration.

## Automated tests

Backend API tests use Django's automatically-created test database and mock
OpenRouter/Wandbox at their boundaries:

The optional AI question agent is server-side only. Configure
`OPENROUTER_API_KEY_1` through `OPENROUTER_API_KEY_5` in `backend/.env` for
local work or in the deployment's secret store; key 1 is tried first and later
configured keys are used only for bounded fallback. `OPENROUTER_MODEL` defaults to
`openai/gpt-oss-20b`. The agent returns candidate test inputs only. It does
not generate or supply authoritative judge expected outputs; an admin must
enter and verify those before publishing an exact-match testcase.

```bash
cd backend
python manage.py test core.tests --verbosity 2
```

Browser E2E tests use Playwright. They create and reset only
`backend/e2e.sqlite3`, seed `e2e-admin` and `e2e-student`, and use a
deterministic test-only executor. They never call Wandbox or OpenRouter and
never use `backend/db.sqlite3`.

```bash
cd frontend
npm install
npx playwright install chromium
npm run test:e2e
```

The E2E suite starts Django on port 8001 and Vite on port 5173. Ensure a
Python interpreter is available on `PATH` as `python` before running it.
