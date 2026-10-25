BEGIN;
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='medtrace_app') THEN
 CREATE ROLE medtrace_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS public.scan_audit (
 pk text NOT NULL, seq int NOT NULL, record jsonb NOT NULL,
 record_hash text NOT NULL, prev_hash text NOT NULL,
 created_at timestamptz DEFAULT now(), PRIMARY KEY(pk,seq)
);
CREATE OR REPLACE FUNCTION public.reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Audit records are immutable'; END $$;
DROP TRIGGER IF EXISTS immutable_audit ON public.scan_audit;
CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE OR TRUNCATE ON public.scan_audit
 FOR EACH STATEMENT EXECUTE FUNCTION public.reject_audit_mutation();
REVOKE ALL ON public.scan_audit FROM PUBLIC, medtrace_app;
GRANT USAGE ON SCHEMA public TO medtrace_app;
GRANT SELECT, INSERT ON public.scan_audit TO medtrace_app;
ALTER TABLE public.scan_audit ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_read ON public.scan_audit;
DROP POLICY IF EXISTS app_insert ON public.scan_audit;
CREATE POLICY app_read ON public.scan_audit FOR SELECT TO medtrace_app USING (true);
CREATE POLICY app_insert ON public.scan_audit FOR INSERT TO medtrace_app WITH CHECK (true);
COMMIT;
