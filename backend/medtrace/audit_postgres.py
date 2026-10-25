"""Postgres implementation of the append-only audit interface."""

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from .audit import ChainConflict, GENESIS_HASH, SEQ_WIDTH, record_hash, _canonical


class AuditLog:
    def __init__(self, url):
        self.pool = ConnectionPool(
            url,
            min_size=1,
            open=True,
            max_size=4,
            kwargs={"prepare_threshold": None},
            timeout=10,
        )

    def recent(self, pk, limit):
        with self.pool.connection() as conn:
            return [
                r[0]
                for r in conn.execute(
                    "SELECT record FROM scan_audit WHERE pk=%s ORDER BY seq DESC LIMIT %s",
                    (pk, limit),
                )
            ]

    def full_history(self, pk, max_items=500):
        with self.pool.connection() as conn:
            rows = [
                r[0]
                for r in conn.execute(
                    "SELECT record FROM scan_audit WHERE pk=%s ORDER BY seq LIMIT %s",
                    (pk, max_items + 1),
                )
            ]
        return rows[:max_items], len(rows) > max_items

    def append(self, pk, head, fields):
        seq = int(head["seq"]) + 1 if head else 1
        item = _canonical(
            {
                **fields,
                "pk": pk,
                "sk": str(seq).zfill(SEQ_WIDTH),
                "seq": seq,
                "prev_hash": head["record_hash"] if head else GENESIS_HASH,
            }
        )
        item["record_hash"] = record_hash(item)
        try:
            with self.pool.connection() as conn:
                conn.execute(
                    "INSERT INTO scan_audit(pk,seq,record,record_hash,prev_hash) VALUES (%s,%s,%s,%s,%s)",
                    (pk, seq, Jsonb(item), item["record_hash"], item["prev_hash"]),
                )
        except UniqueViolation as exc:
            raise ChainConflict(pk) from exc
        return item

    def recent_alerts(self, limit, before=None):
        """Newest clone-suspected records across all packs.

        Returns (records, next_before): pass next_before back as `before` for
        the next page; it is None on the last page.
        """
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT record, created_at FROM scan_audit"
                " WHERE record->>'clone_suspected' = 'true'"
                " AND (%(before)s::timestamptz IS NULL OR created_at < %(before)s::timestamptz)"
                " ORDER BY created_at DESC, pk, seq LIMIT %(limit)s",
                {"before": before, "limit": limit + 1},
            ).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        return [r[0] for r in rows], rows[-1][1].isoformat() if more else None
