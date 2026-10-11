# Dependency security

Checked on 11 October 2026 (second scan after the upgrade: one new finding, below) with `pip-audit -r requirements.txt` and `npm audit --omit=dev` (the commands are in `docs/PENTEST_CHECKLIST.md`, G8). The pipeline (`.github/workflows/ci.yml`, job "Dependency audit") now repeats the check on every push.

## What the first scan found, and what was done
72 findings (many are repeats) in 7 Python packages and 2 in the web page's packages.

| Package | Was | Now | Note |
|---|---|---|---|
| fastapi | 0.115.0 | 0.143.0 | Needed to be able to use a safe Starlette |
| starlette | 0.38.6 (through fastapi) | 1.7.0, pinned in `requirements.txt` | Fixes are in 1.3.1 and later; before, it moved with FastAPI without being written down |
| python-jose | 3.3.0 | 3.5.0 | Sign-in and two-step tokens |
| python-multipart | 0.0.9 | 0.0.32 | File uploads |
| Pillow | 10.4.0 | 12.3.0 | Report images |
| python-dotenv | 1.0.1 | 1.2.4 | |
| pytest | 8.3.3 | 9.1.1 | Tests only |

The versions were chosen by letting `pip` resolve the newest set that fit together (run in a throwaway container), then pinned. After the change the full backend and frontend test suites must pass (they cover uploads, sign-in, two-step sign-in, reports and exports).

## What the upgrade exposed
The full test run after the upgrade found that the **general rate limit (300 requests a minute per person) was no longer applied**: slowapi's middleware finds a route by walking the route list, and FastAPI 0.143 keeps included routers as one object without an `endpoint`, so the middleware found nothing and let everything through (limits written on single routes, such as sign-in, still worked). `test_people_in_one_office_have_an_allowance_each` caught it. The general limit is now applied by a dependency of the whole application (`enforce_general_limit` in `app/core/rate_limit.py`), which runs after the route is known; `limits` is pinned because the code now uses it directly. Lesson: never upgrade FastAPI or Starlette without running the rate-limit tests.

## Accepted, with the reason
* **python-jose 3.5.0 (CVE-2026-85394)**, found by the second scan: an algorithm-confusion flaw, where a token signed with HS256 using a service's *public* key as the secret is accepted when the accepted algorithms are not restricted. It does not apply here: every token is signed and checked with one secret (`SECRET_KEY`) and `jwt.decode(..., algorithms=["HS256"])` names the only accepted algorithm (`app/core/security.py`, `app/core/mfa.py`); no public key is ever used to check a token. Review when python-jose publishes a fixed version, and keep `algorithms=` explicit in any new token check.
* **ecdsa 0.19.2 (PYSEC-2026-1325) and python-jose PYSEC-2025-185**: no fixed version exists. They concern elliptic-curve signatures (and jose's ECDSA support); the system signs tokens with HS256 only and never uses ECDSA keys. The audit step lists them as ignored so any new finding still fails the build. Review when a fix is published.
* **react-router 6 (two moderate findings)**: an open redirect when a link's target comes from user input, and an SSR hydration issue. Every `navigate`/`Link`/`Navigate` target in the application is a fixed path and there is no server-side rendering, so neither can be reached. The fix is a major version (7) with breaking changes; do it as a planned change, not as a side effect. The audit step fails only on high or critical findings.

## Keeping it current
Read the "Dependency audit" job after each push; update and re-run the tests when it fails. Container images (`python:3.12-slim`, `postgres:16-alpine`, `nginx:alpine`) should also be rebuilt regularly to pick up fixes in the base system.
