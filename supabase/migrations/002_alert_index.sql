-- Speeds up GET /alerts (newest clone-suspected scans across all packs).
CREATE INDEX IF NOT EXISTS scan_audit_alerts_idx
  ON public.scan_audit (created_at DESC)
  WHERE (record->>'clone_suspected') = 'true';
