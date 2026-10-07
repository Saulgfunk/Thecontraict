-- The application role must NOT be a superuser: superusers bypass Row-Level Security.
-- CREATEROLE lets the migrations create the restricted "contraict_app" role the API
-- switches to (as on hosted Postgres, whose login users often may bypass RLS).
CREATE ROLE contraict WITH LOGIN PASSWORD 'contraict' CREATEDB CREATEROLE;
CREATE DATABASE contraict OWNER contraict;
CREATE DATABASE contraict_test OWNER contraict;
