# Passwords

## The rules (enforced whenever a person sets a password)

| Rule | Bank's staff (BOT analysts, System Administrators) | Institution users |
|---|---|---|
| Minimum length | **12** characters | **8** characters |
| Character mix | at least one letter, one digit and one special character | the same |
| Common passwords | refused | refused |
| The username inside the password (username of 4 or more characters) | refused | refused |

An account whose role is unknown gets the stricter rule.

**Common passwords.** A password such as `Admin1234!` or `P@ssw0rd2026` has a letter, a digit and a symbol, and is among the first things anyone tries. The check cuts the digits and symbols added in front of or behind the password, undoes look-alike characters inside it (0 for o, 1 for i, 3 for e, 4 for a, 5 for s, 7 for t, @ for a, $ for s), and refuses the password when what is left is a well-known password or word (for example password, admin, welcome, qwerty, bank, tanzania, cdr, and a few Swahili ones) or that word with "my", "the" or "new" in front, and when no more than 8 characters were added. It also refuses a password made of four or fewer different characters. Phrases of several unrelated words are not affected: `lantern-river-orange-road-72` is accepted.

**Where it applies.** Creating an account (System Administration), Change Password, the first administrator made with `scripts/create_admin.py`, and a password set from the server with `scripts/reset_password.py`. Temporary passwords made by the application are random, 12 characters, and are checked against the strictest rule.

**Existing passwords.** Nobody is locked out by a new rule: a password already in use keeps working until its owner changes it. Where it matters, an administrator can require a change at the next sign-in by resetting the password.

## What a person is told
The page explains the rule for their role while they type, and if the server refuses the password it names every rule that was not met ("Your new password must be at least 12 characters long; not be a common password ...").

## Choosing a good password
A long phrase of unrelated words, with a number, is easy to remember and hard to guess: `lantern-river-orange-road-72`. Keep it in a password manager (for example KeePassXC); do not write it in a message, a file in the project folder or a shell command.

## Changing the numbers
`app/core/password_policy.py`: `MIN_LENGTH` (institution users), `STAFF_MIN_LENGTH` (staff) and the word list `_COMMON_BASES`. Add a test in `tests/test_password_policy.py` for any change.
