# Security Phase 1 manual verification

The browser keeps application access and refresh tokens in `localStorage` in
this phase. This preserves the existing application architecture, but tokens
remain readable by a successful XSS attack. A future phase should move the
refresh token to an HttpOnly, Secure, SameSite cookie.

Before deploying, set `DJANGO_ENV=production`, `DEBUG=False`, `SECRET_KEY`,
`CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS`. Production CORS origins
must be explicit HTTPS origins; wildcards are rejected at startup.

1. Register a student with a new email, then log in and open the dashboard.
2. Try the same email with changed case or surrounding spaces; registration
   must reject it.
3. As that student, request an admin endpoint and confirm HTTP 403.
4. Log in as an admin and confirm the same admin endpoint succeeds.
5. Refresh an active session once; confirm the new refresh token works and the
   original refresh token now fails.
6. Log out, then submit the prior refresh token to `/api/auth/refresh/`; it
   must fail.
7. Change a user's password through the supported Django admin flow; an old
   access token must fail and a new login must succeed.
8. Submit repeated invalid logins from one client and confirm a 429 response.
9. If configured, complete Google authentication for a new user, an existing
   local user, and a removed user.
10. Mark a user removed, then confirm existing protected requests fail.
11. Send an `Origin` header from a configured frontend origin and confirm CORS
    allows it; repeat with an untrusted origin and confirm no allow-origin
    header is returned.
