-- Creates ONLY the login role cdr_app (no privileges). Used by the production restore and the restore drill
-- BEFORE pg_restore, because a backup taken on the production stack carries GRANT/REVOKE statements for
-- cdr_app, and restoring them into a database where the role does not exist would fail.
-- The privileges themselves come back with the dump and are re-applied afterwards by create_app_role.sql.
-- Run as the database owner:  psql -v app_password=<PASSWORD> -f create_bare_role.sql
\set ON_ERROR_STOP on

SELECT format('CREATE ROLE cdr_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_password')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cdr_app')
\gexec
