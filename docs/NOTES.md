# DSA Tracker — Technical Notes

This document explains **every algorithm, pattern, and technique** used in this
project, why it was chosen, and where to find it in the code. Read this before
a scrum call, a code review, or if you're picking the project back up later.

---

## 1. Authentication & Security

### 1.1 Password Hashing — PBKDF2-SHA256
**Where:** `backend/core/serializers.py` → `RegisterSerializer.create()` (calls `User.objects.create_user()`)

We never store or compare raw passwords. Django's `create_user()` runs the
password through **PBKDF2 with a SHA-256 HMAC**, salted with a random value
per user, iterated 600,000+ times by default. This makes brute-force and
rainbow-table attacks computationally expensive. We never reimplement this
ourselves — rolling your own password hashing is one of the most common
security mistakes in web apps.

### 1.2 JWT (JSON Web Token) Authentication
**Where:** `backend/dsatracker/settings.py` (`SIMPLE_JWT` config), `backend/core/urls.py`

Instead of session cookies, the API issues two signed tokens on login:
- **Access token** (30 min lifetime) — sent on every request in the
  `Authorization: Bearer <token>` header. Stateless: the server verifies the
  signature and reads the payload (user id, expiry) without a DB lookup.
- **Refresh token** (7 day lifetime) — used only to mint new access tokens.

**Why JWT over server-side sessions:** JWTs are stateless (no session table
to query on every request) and work naturally with a decoupled
frontend/backend architecture where the API might later be called from a
mobile app too.

> **Note on the PRD's Google OAuth requirement:** the PRD specifies Google
> OAuth via Supabase. That needs a live Supabase project + registered OAuth
> redirect URI, which can't exist in an offline build. JWT auth is a
> drop-in local substitute — see `README.md` for exactly what changes when
> you wire up real Supabase/Google OAuth later.

### 1.3 Silent Token Refresh + Request Queueing
**Where:** `frontend/src/api/axios.js`

This is one of the more subtle pieces of the project. When an access token
expires mid-session:

1. The API responds `401 Unauthorized`.
2. An **axios response interceptor** catches it.
3. The interceptor calls `/auth/refresh/` with the stored refresh token to
   silently get a new access token — the user never sees a login screen.
4. The **original failed request is retried** with the new token.

**The queueing problem:** if 3 API calls fire in parallel and all get 401 at
the same moment, without safeguards you'd trigger 3 simultaneous refresh
calls. We use an `isRefreshing` flag + a `pendingQueue` array (a form of the
**promise queue / mutex pattern**): the first 401 triggers the refresh; any
other 401s that arrive while a refresh is already in flight just push a
`{resolve, reject}` pair onto the queue and wait. When the refresh
completes, `flushQueue()` resolves everyone waiting with the new token.

### 1.4 Role-Based Access Control (RBAC)
**Where:** `backend/core/permissions.py`

Three composable DRF permission classes instead of `if/else` role checks
scattered through every view:

- `IsAdmin` — object-independent gate; blocks the whole view for non-admins.
- `IsAdminOrReadOnly` — anyone authenticated can `GET`; only Admins can
  `POST/PUT/PATCH/DELETE`. Uses DRF's `SAFE_METHODS` constant
  (`GET, HEAD, OPTIONS`).
- `IsOwnerOrAdmin` — **object-level** permission: a student can only
  mutate *their own* assignment row; an Admin can view (not silently edit)
  another student's row.

This is the **Guard Clause / Strategy pattern** applied to authorization:
each permission class is a single-purpose, testable unit that DRF checks
*before* the view method body ever runs.

---

## 2. Database Design & Query Techniques

### 2.1 Schema — Three Entities, One Join Table
**Where:** `backend/core/models.py`

- `Profile` — 1:1 extension of Django's built-in `User` (rather than
  forking Django's auth system). Holds the `role` field (`admin`/`user`).
- `Question` — the DSA problems catalog.
- `Assignment` — the **many-to-many join table** connecting Users ↔
  Questions, carrying extra fields (`status`, `assigned_at`) that a plain
  `ManyToManyField` can't hold. This is the standard "through model"
  pattern for M2M relationships that need metadata.

### 2.2 Database-Level Uniqueness Constraint (Race-Condition Safety)
**Where:** `Assignment.Meta.constraints` — `UniqueConstraint(fields=["user", "question"])`

A student can't assign the same question twice. We enforce this **in the
database itself**, not just in application code. If we only checked
"does an assignment already exist?" in Python before inserting, two
simultaneous requests (e.g. a user double-clicking "Assign") could both
pass the check before either insert commits — a **race condition**. The DB
constraint makes the second `INSERT` fail atomically, and
`AssignmentCreateSerializer.validate()` catches the ordinary (non-race)
case early with a friendly error message.

### 2.3 Soft Deletes
**Where:** `Question.is_active` field; `QuestionViewSet.perform_destroy()`

"Deleting" a question sets `is_active = False` instead of removing the row.
Real deletion would either cascade-delete every student's historical
assignment of that question (destroying their activity history) or throw a
foreign-key error. Soft deletes preserve **referential integrity and audit
history** while removing the question from active listings
(`get_queryset()` filters `is_active=True`).

### 2.4 Avoiding N+1 Queries
**Where:** `QuestionViewSet.get_queryset()` / `get_serializer_context()`, `AssignmentViewSet.get_queryset()`

The classic **N+1 query problem**: fetching 20 questions, then running 1
extra query *per question* to count its assignments = 21 queries instead
of 2. Fixed two ways here:

- **`.annotate(assignment_count=Count("assignments"))`** — folds the count
  into the *original* query using a SQL `GROUP BY`/`COUNT`, so it's one
  query total, not one-per-row.
- **`select_related("question", "user")`** on `Assignment` querysets — a
  SQL `JOIN` that fetches the related `Question`/`User` row in the same
  query instead of lazily querying for it when the serializer accesses
  `assignment.question.title`.
- **Prefetched lookup set** for `is_assigned_to_me`: rather than asking
  "is this question assigned to me?" with a DB query *per question row* in
  the serializer, we fetch the requesting user's assignment IDs **once**
  into a Python `set()` in `get_serializer_context()`, then each row does
  an O(1) in-memory `set` membership check instead of a query.

### 2.5 Single-Query Aggregation for Analytics
**Where:** `backend/core/views.py` → `build_breakdown()`, `build_status_breakdown()`

The "Easy: 10, Medium: 9, Hard: 6" style breakdown could be computed with
three separate `.filter(difficulty="easy").count()` calls — three
round-trips to the database. Instead we use **one `.aggregate()` call with
conditional `Count` expressions**:

```python
queryset.aggregate(
    easy=Count("id", filter=Q(question__difficulty="easy")),
    medium=Count("id", filter=Q(question__difficulty="medium")),
    hard=Count("id", filter=Q(question__difficulty="hard")),
)
```

This compiles to a single SQL statement using conditional aggregation
(the same idea as SQL's `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`), so the
database does the counting in one pass instead of the app looping and
querying three times.

`build_status_breakdown()` uses a related technique — `.values("status")
.annotate(count=Count("id"))` — which is Django's equivalent of SQL's
`GROUP BY status`.

### 2.6 Time-Window Filtering ("Last 7 / 30 Days")
**Where:** `backend/core/views.py` → `get_period_start()`

Rather than storing a separate "week" or "month" field, we compute the
cutoff **on read**: `timezone.now() - timedelta(days=N)`, then
`.filter(assigned_at__gte=cutoff)`. This is O(1) to compute and stays
correct forever (no batch job needs to "roll over" a week boundary). It
relies on `assigned_at` being **indexed** (see §2.7) so the range filter
is fast even as the assignments table grows.

### 2.7 Database Indexing Strategy
**Where:** `Meta.indexes` in `models.py`

Indexes were added on columns that are *frequently filtered or sorted on*:
- `Question.difficulty` + `is_active` (composite) — every question list
  request filters by these.
- `Assignment.user` + `status` (composite) — "my assignments filtered by
  status" is a hot path.
- `Assignment.assigned_at` — powers the 7/30-day range filters.
- `Profile.role` — used to distinguish admins from students in queries.

Composite indexes are ordered so the most commonly-filtered field comes
first, since a B-tree index can efficiently use a *prefix* of its columns.

---

## 3. Backend Architecture Patterns

### 3.1 Signal-Based Profile Creation (Observer Pattern)
**Where:** `backend/core/signals.py`

Rather than manually creating a `Profile` in every place a `User` might be
created (register endpoint, Django admin, a future management command,
a Google OAuth callback...), we hook Django's `post_save` signal on
`User`. This is the **Observer pattern**: the `User` model doesn't know or
care that a `Profile` gets created — the signal handler observes user
creation events and reacts, keeping the two concerns decoupled and
guaranteeing there's exactly **one source of truth** for "how does a
Profile get created."

### 3.2 Declarative Filtering (django-filter)
**Where:** `backend/core/filters.py`

Instead of manually parsing `request.GET.get("difficulty")` and building
`.filter()` chains by hand inside every view, `FilterSet` classes declare
"this query param maps to this ORM lookup" once, and DRF's
`DjangoFilterBackend` applies it automatically. This is the same idea as a
**declarative routing table** — you describe the mapping, not the
imperative parsing logic.

### 3.3 Serializer Context Injection
**Where:** `QuestionViewSet.get_serializer_context()`, `AssignmentCreateSerializer.validate()`

DRF serializers can receive extra data via `context` beyond just the model
instance being serialized — e.g. the current `request`, or a precomputed
`my_assignment_ids` set. This keeps **request-scoped, cross-cutting data**
(like "who is asking?") available to serializer methods without smuggling
it through global state or re-fetching it per row.

### 3.4 Separation of Concerns (Layered Architecture)
**Where:** overall `backend/core/` structure

Each file has exactly one job:
`models.py` (data shape) → `serializers.py` (data ↔ JSON translation +
validation) → `permissions.py` (who's allowed) → `filters.py` (which
subset) → `views.py` (orchestration: wire the above together per
endpoint). This mirrors the PRD's explicit "Separation of Concerns"
non-functional requirement (§19.5) and makes each layer independently
testable.

---

## 4. Frontend Architecture Patterns

### 4.1 Context API for Global Auth State
**Where:** `frontend/src/context/AuthContext.jsx`

Rather than passing `user`, `login()`, `logout()` down through props at
every level ("prop drilling"), `AuthContext` + `useAuth()` makes auth state
available to any component in the tree with `const { user } = useAuth()`.
On mount, it calls `/auth/me/` once to hydrate the session from a stored
token, so a page refresh doesn't log the user out.

### 4.2 Declarative Route Guards
**Where:** `frontend/src/routes/ProtectedRoute.jsx`

`<RequireAuth>` and `<RequireAdmin>` are wrapper routes using React
Router's `<Outlet />` — they render their nested child route only if the
guard condition passes, otherwise they issue a `<Navigate>` redirect. This
keeps "is the user allowed here?" logic in **one place** instead of an
`if (!user) navigate("/login")` check duplicated inside every page
component.

### 4.3 Optimistic UI Updates
**Where:** `frontend/src/pages/UserDashboard.jsx` → `handleStatusChange()`, `handleUnassign()`

When a student changes an assignment's status or unassigns a question, the
UI updates **immediately** (before the server confirms), then quietly
syncs with the API in the background. If the request fails, we roll back
to the previous state (`setAssignments(prev)`). This makes the app feel
instant rather than waiting on network round-trips for every click — a
standard technique in modern SPAs (used by apps like Trello, Linear, etc.).

### 4.4 Debounced Search
**Where:** `frontend/src/pages/UserDashboard.jsx` → `BrowseQuestions` component

Typing in the question search box doesn't fire an API call on every
keystroke. A `setTimeout(fetchQuestions, 300)` is reset on every
keystroke (`useEffect` cleanup clears the previous timer), so the request
only fires 300ms after the user *stops* typing. This is the standard
**debounce** technique — it cuts a 10-character search from 10 API calls
down to 1.

### 4.5 Lifted State for Shared Filters
**Where:** `frontend/src/components/Filters.jsx` (`DifficultyFilter`, `PeriodSelect`)

These are intentionally "dumb" (stateless) components — they receive
`value` and `onChange` as props and render UI, but the *parent* page
component owns the actual filter state. This is React's standard
**"lift state up"** pattern: it lets `DifficultyFilter` be reused
identically on both the student's "Browse Questions" tab and the admin's
"Student Activity" tab without duplicating state logic.

### 4.6 Component Composition over Duplication
**Where:** `AssignmentRow.jsx`, `ActivityStats.jsx`, `Badges.jsx`

The same `AssignmentRow` component renders a row in "My Assigned
Questions", "My Activity", and the admin's "Student Activity" view — just
with different callback props (some are no-ops where editing isn't
allowed, e.g. an admin viewing a student's read-only history). `Badges.jsx`
centralizes difficulty/status → color mapping in one place so a color
scheme change is a one-line edit, not a find-and-replace across the app.

### 4.7 Data Visualization
**Where:** `frontend/src/components/ActivityStats.jsx` (uses `recharts`)

The difficulty breakdown renders as a bar chart via `recharts`'
`<BarChart>`/`<Bar>` components. Crucially, **all counting happens on the
backend** (see §2.5) — the chart component only visualizes numbers it's
handed; it does zero client-side aggregation, keeping the "source of
truth" for counts in exactly one place.

---

## 5. API Design

### 5.1 RESTful Resource Modeling
**Where:** `backend/core/urls.py`, DRF `ModelViewSet`s

`QuestionViewSet` and `AssignmentViewSet` use DRF's `ModelViewSet` +
`DefaultRouter`, which auto-generates the full REST convention for free:

| Method | URL                          | Action           |
|--------|-------------------------------|-------------------|
| GET    | /api/questions/                | list              |
| POST   | /api/questions/                | create            |
| GET    | /api/questions/{id}/            | retrieve          |
| PUT    | /api/questions/{id}/            | update            |
| DELETE | /api/questions/{id}/            | destroy (soft)    |

Custom, non-CRUD actions (like updating just an assignment's status) use
DRF's `@action(detail=True, methods=["patch"])` decorator, which extends
the router with `POST/PATCH /assignments/{id}/status_update/` — this
avoids overloading the generic `update()` method with special-case logic.

### 5.2 Pagination
**Where:** `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]` in `settings.py`

All list endpoints use DRF's `PageNumberPagination` (20 items/page) rather
than returning the entire table in one response — necessary once the
question bank or a student's history grows large. The frontend defensively
reads `data.results ?? data` to handle both paginated and (during tests)
non-paginated shapes.

---

## 6. What Would Change for Production

| Area | Dev (this build) | Production |
|---|---|---|
| Database | SQLite | Postgres (Supabase or otherwise) — models are already portable |
| Auth | JWT email/password | Google OAuth via Supabase Auth (or verify Google ID tokens directly) |
| Secret key | Hardcoded in settings.py | Environment variable / secrets manager |
| CORS | `CORS_ALLOW_ALL_ORIGINS = True` | Restrict to the deployed frontend origin |
| Debug | `DEBUG = True` | `DEBUG = False` + proper `ALLOWED_HOSTS` |
| Static/media | Django dev server | Whitenoise / S3 / CDN |
| WSGI server | `manage.py runserver` | gunicorn/uvicorn behind nginx |
