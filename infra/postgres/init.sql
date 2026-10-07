-- The application role must NOT be a superuser: superusers bypass Row-Level Security.
CREATE ROLE contraict WITH LOGIN PASSWORD 'contraict' CREATEDB;
CREATE DATABASE contraict OWNER contraict;
CREATE DATABASE contraict_test OWNER contraict;
