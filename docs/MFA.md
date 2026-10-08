# Two-step sign-in (MFA)

After the password, staff enter a 6-digit code from an authenticator app on their phone. A stolen or guessed password is then not enough.

## Who must use it
* **In production** the Bank's staff roles, **BOT analyst and System Administrator**, must (`MFA_REQUIRED=true`, the default of `docker-compose.prod.yml`). Institution users are not asked.
* **In development** it is off (`MFA_REQUIRED` defaults to false), so the demonstration accounts and the tests are unchanged.
* **Anyone who has set it up always uses it**, even if the requirement is later switched off.

## First sign-in (what the person sees)
1. Sign in with the username and password. Staff who have not set it up are taken to **Set up two-step sign-in**; they get no access before finishing it.
2. Install an authenticator app on the phone (Google Authenticator, Microsoft Authenticator, FreeOTP, or similar).
3. In the app, add an account: **scan the picture**, or choose "enter a setup key" and type the key shown (time based).
4. Type the 6-digit code the app shows. If it is right, two-step sign-in is on.
5. **Save the 10 recovery codes.** They are shown once. Each works one time, for a lost phone. Copy them or download the file, tick the box, continue.

## Every sign-in afterwards
Password, then the 6-digit code (it changes every 30 seconds). A code works once. A wrong code counts towards the **same lock-out as a wrong password**.

## Lost phone
1. **Recovery code**: on the code screen choose "I lost my phone: use a recovery code". The person is told in the system that one was used, and how many remain.
2. **Another administrator resets it**: Administration, Users, **Reset two-step** (shown for people who have it on, never for your own row). The person's sessions end, they are told, and they set it up again at their next sign-in. The event is audited (`MFA_RESET`). The administrator never sees a secret or a code.
3. **From the server** (an administrator who lost both phone and codes, because nobody may reset their own through the application):
   ```
   docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/reset_mfa.py --username <name>
   ```

**Before the first production sign-in, create a second administrator**, so one lost phone never leaves nobody able to reset.

## Emergency: nobody can get in
If enrolment cannot be completed for staff (for example the phones show the wrong time), set `MFA_REQUIRED=false` in `.env.production`, run `scripts/prod_up.ps1` (or `.sh`), fix the cause, then set it back to `true` and run it again. People who already set it up are still asked for a code. Do not leave it off.

## What is protected, and how
* The shared secret is stored **encrypted** (Fernet, key derived from `SECRET_KEY`): a copy of the database alone cannot produce codes. Recovery codes are stored only as **keyed hashes**.
* A code is accepted within one 30-second step either side of now, and **each step only once**; an older or reused code is refused (no replay).
* The step between the password and the code uses a 5-minute **step token** with a purpose. It is not an access token: `get_current_user` refuses it, and a code token cannot start enrolment or the other way round.
* Wrong codes are rate-limited (10 a minute) and lock the account like wrong passwords. Every refusal gives the same message.
* The database refuses an account marked as enrolled without a secret (`ck_users_mfa_enabled_has_secret`).
* Audited: `MFA_ENABLED`, `MFA_FAILED`, `MFA_RECOVERY_CODE_USED`, `MFA_RECOVERY_CODES_REGENERATED`, `MFA_RESET`, and the usual `LOGIN` after the second step.

## Changing `SECRET_KEY`
The encryption key comes from `SECRET_KEY`. If it is changed, the stored secrets can no longer be read and nobody can pass the second step: every enrolled person must be reset (one by one, or with `reset_mfa.py`). Plan a key change for a quiet moment, together with the reset.

## Endpoints
| Endpoint | Use |
|---|---|
| `POST /api/auth/login` | Answers with tokens, or `mfa_required` (enter the code), or `mfa_setup_required` (set up first), plus a short `mfa_token` |
| `POST /api/auth/mfa/verify` | `mfa_token` plus `code` or `recovery_code`; answers with tokens |
| `POST /api/auth/mfa/setup/begin` | New secret, address and QR picture to add to the app (changes nothing until confirmed) |
| `POST /api/auth/mfa/setup/confirm` | The first code; turns it on; answers with tokens and the recovery codes (once) |
| `POST /api/auth/mfa/recovery-codes` | New recovery codes (needs the current code and a signed-in session); the old ones stop working |
| `POST /api/users/{id}/mfa/reset` | Administrator only; not your own |

## Limits (stated plainly)
* One authenticator per person; no SMS, e-mail or push codes; standard TOTP (RFC 6238, SHA-1, which every authenticator app supports).
* A phone whose clock is more than about 30 seconds wrong fails: use automatic time.
* The web page has no button to make new recovery codes yet (the endpoint exists).
* API keys for external systems are a separate mechanism and are not asked for a code.
* The QR picture is a convenience: if it cannot be drawn, the typed key always works.

## What was verified
The code algorithm against the **RFC 6238 test vectors**, the encryption, recovery codes and step tokens by tests, and the QR picture by decoding it with QR readers (300 of 300 keys with one reader, 298 of 300 with another). The sign-in, enrolment, lock-out, reset and database tests are in `tests/test_mfa_login.py` and run with the rest of the suite.


## If you did not save your recovery codes

The ten recovery codes are shown once, when two-step sign-in is set up. If they were not saved, sign in as usual (the authenticator still works) and open **Change Password** in the menu on the left. Under the password form, the card **Two-step sign-in: recovery codes** makes ten new ones: type the 6-digit code your authenticator shows now, and the new codes appear (Copy all, Download as a file). **The old codes stop working at that moment.** A wrong code is counted like a wrong code at sign-in (the same lock-out), and the action is recorded in the audit log (`MFA_RECOVERY_CODES_REGENERATED`). The card is shown only to people who use two-step sign-in, and not while a temporary password still has to be replaced.
If the authenticator itself is lost and no recovery code is left, a second administrator can remove the two-step sign-in in System Administration, or from the server: `scripts/reset_mfa.py --username NAME` (`ACCOUNT_RECOVERY.md`).
