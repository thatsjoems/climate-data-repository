# Account recovery (from the server)

Two commands, both run on the server inside the backend container. They are the Bank's own control: they need access to the server, which a web session does not give.

| Situation | Command |
|---|---|
| An administrator forgot their password and there is no second administrator to reset it | `scripts/reset_password.py --username NAME` |
| An administrator lost the authenticator app and the recovery codes | `scripts/reset_mfa.py --username NAME` |
| Nobody can sign in as an administrator at all and a new one is needed | `scripts/create_admin.py --allow-additional ...` |

Production example (type the password at the hidden prompt, twice, the same both times):

    docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/reset_password.py --username admin

What `reset_password.py` does: checks the password against the password policy (at least 12 characters for the Bank's staff and 8 for institution users, a letter, a digit and a special character, not a common password, and not containing the username: see `PASSWORDS.md`); stores it hashed; unlocks the account and clears its
count of failed sign-ins; ends every session the account already had; requires the person to choose their own password at the next sign-in (`--no-forced-change` turns that off); and records
`PASSWORD_RESET_CLI` in the audit log (who: the command line; the password is never recorded). It does not touch the two-step sign-in.

The password is never a command-line option, so it does not land in the shell history or the process list. When one administrator forgot a password and another administrator exists, use the application
instead (the "Forgot password" request, approved under System Administration): that leaves the same audit trail without server access.
