-- Initialize PostgreSQL for Triage Agent

-- Create pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS pgvector;

-- Create pgcrypto extension for UUID and crypto functions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Create triage_app role with limited privileges
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_user WHERE usename = 'triage_app') THEN
    CREATE ROLE triage_app WITH LOGIN NOINHERIT NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

-- Grant basic privileges
GRANT CONNECT ON DATABASE triage TO triage_app;

-- Create a schema for the application
CREATE SCHEMA IF NOT EXISTS triage;
GRANT USAGE ON SCHEMA triage TO triage_app;

-- Set search_path for triage_app role
ALTER ROLE triage_app SET search_path = triage, public;
