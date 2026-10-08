# Rate limits

A limit counts requests in a fixed minute and answers **429 Too Many Requests** for the excess. The number a request is counted against (its "bucket") is the **signed-in person** (a valid, unexpired access token) or, when there is none, the **real caller's address**. Behind the production proxy the real address is the one the proxy appends to `X-Forwarded-For`, never anything the caller wrote (`NETWORK_ACCESS.md`).

| What | Limit | Counted per |
|---|---|---|
| Every route, unless stricter below | 300 a minute | person, or address if not signed in |
| Sign-in | 10 a minute | address |
| Two-step code, set-up and new recovery codes | 10 a minute | address (the code steps carry no access token yet) or person |
| Password-reset request ("Forgot password") | 10 a minute | address |
| Token refresh | 30 a minute | address |
| Integration endpoints (reading, sending) | per key, see `INTEGRATION_ACCESS.md` | API key |

**Why a person and not only an address.** An office behind one address would otherwise share one allowance; ten requests make a dashboard page, so a busy minute of analysts could stop all of them. A person has 300 a minute, about five a second, far above what anyone does by hand.
**Why only a VALID token.** The signature is checked when the bucket is chosen. A request carrying a made-up or expired token is counted against its sender's address, so nobody can spend another person's allowance by naming them.

**Staging and development.** `RATE_LIMIT_ENABLED=false` turns every limit off; staging uses it only for load tests, and the production checker refuses it in `.env.production`. Penetration tests of the limits need it **on** (`PENTEST_CHECKLIST.md`, section 2).

**Changing the numbers.** `GENERAL_LIMIT` in `app/core/rate_limit.py` and the `@limiter.limit(...)` line of the route. The tests in `tests/test_rate_limit_per_user.py` and `tests/test_rate_limit_real_address.py` state the numbers; change them together.
