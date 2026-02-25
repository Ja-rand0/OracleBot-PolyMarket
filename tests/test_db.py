import pytest
import sqlite3
import data.db as db
from data.models import ComboResults
from datetime import datetime


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    db.init_db(conn)
    yield conn
    conn.close()


def _make_cr(combo_id, fitness, accuracy=0.6, edge=0.05, fpr=0.1):
    cr = ComboResults(combo_id=combo_id, methods_used=[combo_id],
                      accuracy=accuracy, edge_vs_market=edge,
                      false_positive_rate=fpr, complexity=1,
                      tested_at=datetime.utcnow())
    cr.fitness_score = fitness
    return cr


def test_holdout_table_created(mem_conn):
    tables = [r[0] for r in mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "holdout_validation" in tables


def test_insert_and_query_holdout(mem_conn):
    train = _make_cr("E15", 0.40)
    holdout = _make_cr("E15", 0.35)
    db.insert_holdout_result(mem_conn, "E15", train, holdout, 80, 20)
    mem_conn.commit()
    rows = db.get_latest_holdout_results(mem_conn, limit=1)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "E15"           # combo_id
    assert row[1] == 80              # train_markets
    assert row[2] == 20              # holdout_markets
    assert abs(row[3] - 0.40) < 0.001   # train_fitness
    assert abs(row[4] - 0.35) < 0.001   # holdout_fitness


def test_get_latest_respects_limit(mem_conn):
    for i in range(5):
        cr = _make_cr(f"M{i}", 0.40 + i * 0.01)
        hcr = _make_cr(f"M{i}", 0.35)
        db.insert_holdout_result(mem_conn, f"M{i}", cr, hcr, 80, 20)
    mem_conn.commit()
    rows = db.get_latest_holdout_results(mem_conn, limit=3)
    assert len(rows) == 3
