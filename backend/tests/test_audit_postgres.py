import os
from pathlib import Path
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
from medtrace.audit import ChainConflict, verify_chain
from medtrace.audit_postgres import AuditLog


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    container = None
    if not url:
        try:
            import docker

            docker.from_env().ping()
        except Exception:
            pytest.skip("Docker unavailable; set TEST_DATABASE_URL")
        from testcontainers.postgres import PostgresContainer

        try:
            container = PostgresContainer("postgres:16")
            container.start()
            url = container.get_connection_url().replace(
                "postgresql+psycopg2", "postgresql"
            )
        except Exception:
            pytest.skip("Postgres container unavailable")
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(
            (
                Path(__file__).resolve().parents[2]
                / "supabase/migrations/001_scan_audit.sql"
            ).read_text()
        )
    yield url
    if container:
        container.stop()


def test_postgres(database):
    import uuid

    log = AuditLog(database)
    pk = str(uuid.uuid4())
    try:
        first = log.append(
            pk, None, {"number": Decimal("1.2345"), "location": {"lat": 8.54}}
        )

        def append():
            try:
                return log.append(pk, first, {"n": 2})
            except ChainConflict:
                return None

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: append(), range(2)))
        assert sum(x is not None for x in results) == 1
        records, truncated = log.full_history(pk)
        assert verify_chain(records)["valid"] and not truncated
        assert log.recent(pk, 1)[0]["seq"] == 2
        records[0]["number"] = 99
        assert not verify_chain(records)["valid"]
        for statement in [
            "UPDATE scan_audit SET seq=seq WHERE pk=%s",
            "DELETE FROM scan_audit WHERE pk=%s",
        ]:
            with psycopg.connect(database) as c:
                with pytest.raises(psycopg.errors.RaiseException):
                    c.execute(statement, (pk,))
    finally:
        log.pool.close()


def test_app_role_permissions(database):
    import uuid

    pk = str(uuid.uuid4())
    with psycopg.connect(database) as conn:
        conn.execute("SET ROLE medtrace_app")
        conn.execute(
            "INSERT INTO scan_audit(pk,seq,record,record_hash,prev_hash) VALUES (%s,1,'{}','a','b')",
            (pk,),
        )
        assert (
            conn.execute("SELECT pk FROM scan_audit WHERE pk=%s", (pk,)).fetchone()[0]
            == pk
        )
    with psycopg.connect(database) as conn:
        conn.execute("SET ROLE medtrace_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM scan_audit WHERE pk=%s", (pk,))


def test_recent_alerts_newest_first_with_cursor(database):
    import uuid

    with psycopg.connect(database, autocommit=True) as c:
        c.execute(
            (Path(__file__).resolve().parents[2] / "supabase/migrations/002_alert_index.sql").read_text()
        )
    log = AuditLog(database)
    try:
        tag = uuid.uuid4().hex
        pks = [f"{tag}-{i}" for i in range(3)]
        for i, pk in enumerate(pks):
            log.append(pk, None, {"clone_suspected": i != 1, "site_id": f"S{i}"})
        newest, cursor = log.recent_alerts(1)
        assert [r["pk"] for r in newest] == [pks[2]] and cursor
        older, _ = log.recent_alerts(50, cursor)
        mine = [r["pk"] for r in older if r["pk"].startswith(tag)]
        assert mine == [pks[0]]  # the non-clone record is never listed
    finally:
        log.pool.close()
