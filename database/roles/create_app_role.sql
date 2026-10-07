-- Least-privilege runtime role for the CDR backend.  OPT-IN - see docs/DATABASE_OPERATIONS.md.
--
-- Run as the database OWNER (the `postgres` user), AFTER the migrations have run (the tables must
-- exist). Safe to re-run: it creates the role if missing and re-applies the grants and the password.
--
--   docker compose cp database/roles/create_app_role.sql db:/tmp/create_app_role.sql
--   docker compose exec -T db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -v app_password=<PASSWORD> -f /tmp/create_app_role.sql'
--   docker compose exec -T db rm -f /tmp/create_app_role.sql
--
-- Use a password made only of letters and digits (for example 48 hex characters) so that no shell
-- character needs escaping.
--
-- Why: today the backend connects as `postgres`, a superuser. Any flaw in the application - or in
-- anything that reaches it - then has the power to read, change or DROP everything, including the
-- audit trail. The role below can read and write ordinary data, and nothing else:
--   * no superuser, no creating databases or roles, no creating or altering tables;
--   * NO DELETE anywhere: the application issues no SQL DELETE (only file deletions for rejected
--     uploads), so it is simply not granted;
--   * NO UPDATE on audit_logs and risk_advisory_notes, which are append-only by design. Until now
--     "append-only" was only the application's promise; with this role the database enforces it.
-- Schema changes still happen: migrations run as the owner (MIGRATION_DATABASE_URL), not as this role.

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE cdr_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_password')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cdr_app')
\gexec

SELECT format('ALTER ROLE cdr_app PASSWORD %L', :'app_password')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO cdr_app', current_database())
\gexec

GRANT USAGE ON SCHEMA public TO cdr_app;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO cdr_app;
-- Tables created by later migrations (run as this same owner) get the same grants automatically.
-- A future append-only table needs its own REVOKE UPDATE, like the two below.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO cdr_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cdr_app;

REVOKE UPDATE ON audit_logs, risk_advisory_notes FROM cdr_app;
