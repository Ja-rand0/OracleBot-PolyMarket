from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import config
from data.models import Bet, ComboResults, Market, Wallet, WalletRelationship

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _ts(dt: datetime) -> str:
    return dt.strftime(_ISO)


def _dt(s: str) -> datetime:
    return datetime.strptime(s, _ISO)


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------
def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS markets (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            end_date TEXT,
            resolved BOOLEAN DEFAULT 0,
            outcome TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            wallet TEXT,
            side TEXT,
            amount REAL,
            odds REAL,
            timestamp TEXT,
            FOREIGN KEY (market_id) REFERENCES markets(id)
        );

        CREATE TABLE IF NOT EXISTS wallets (
            address TEXT PRIMARY KEY,
            first_seen TEXT,
            total_bets INTEGER DEFAULT 0,
            total_volume REAL DEFAULT 0,
            win_rate REAL DEFAULT 0,
            rationality_score REAL DEFAULT 0,
            flagged_suspicious BOOLEAN DEFAULT 0,
            flagged_sandpit BOOLEAN DEFAULT 0,
            yes_bet_ratio REAL DEFAULT 0.5
        );

        CREATE TABLE IF NOT EXISTS wallet_relationships (
            wallet_a TEXT,
            wallet_b TEXT,
            relationship_type TEXT,
            confidence REAL,
            PRIMARY KEY (wallet_a, wallet_b)
        );

        CREATE TABLE IF NOT EXISTS method_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            combo_id TEXT UNIQUE,
            methods_used TEXT,
            accuracy REAL,
            edge_vs_market REAL,
            false_positive_rate REAL,
            complexity INTEGER,
            fitness_score REAL,
            tested_at TEXT
        );

        CREATE TABLE IF NOT EXISTS holdout_validation (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            validated_at    TEXT NOT NULL,
            combo_id        TEXT NOT NULL,
            train_markets   INTEGER,
            holdout_markets INTEGER,
            train_fitness   REAL,
            holdout_fitness REAL,
            train_accuracy  REAL,
            holdout_accuracy REAL,
            train_edge      REAL,
            holdout_edge    REAL,
            train_fpr       REAL,
            holdout_fpr     REAL
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            predicted_at TEXT NOT NULL,
            predicted_side TEXT NOT NULL,
            market_price_at_prediction REAL,
            bot_signal REAL,
            bot_confidence REAL,
            bot_edge REAL,
            combo_id TEXT,
            resolved_at TEXT,
            actual_outcome TEXT,
            correct INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_bets_market ON bets(market_id);
        CREATE INDEX IF NOT EXISTS idx_bets_wallet ON bets(wallet);
        CREATE INDEX IF NOT EXISTS idx_bets_timestamp ON bets(timestamp);
        CREATE INDEX IF NOT EXISTS idx_predictions_market ON predictions(market_id);
        """
    )
    conn.commit()

    # Ensure unique index on bets — deduplicate existing rows first
    has_idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_bets_unique'"
    ).fetchone()
    if not has_idx:
        dupes = conn.execute(
            """DELETE FROM bets WHERE id NOT IN (
                   SELECT MIN(id) FROM bets
                   GROUP BY market_id, wallet, side, amount, timestamp
               )"""
        ).rowcount
        if dupes:
            log.info("Removed %d duplicate bets", dupes)
        conn.execute(
            """CREATE UNIQUE INDEX idx_bets_unique
               ON bets(market_id, wallet, side, amount, timestamp)"""
        )
        conn.commit()

    # Ensure unique constraint on method_results.combo_id
    has_mr_idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_mr_combo_unique'"
    ).fetchone()
    if not has_mr_idx:
        # Keep only the best fitness per combo_id
        conn.execute(
            """DELETE FROM method_results WHERE id NOT IN (
                   SELECT id FROM (
                       SELECT id, ROW_NUMBER() OVER (
                           PARTITION BY combo_id ORDER BY fitness_score DESC
                       ) AS rn FROM method_results
                   ) WHERE rn = 1
               )"""
        )
        conn.execute(
            "CREATE UNIQUE INDEX idx_mr_combo_unique ON method_results(combo_id)"
        )
        conn.commit()

    # Migration: add yes_bet_ratio column to existing databases
    try:
        conn.execute("ALTER TABLE wallets ADD COLUMN yes_bet_ratio REAL DEFAULT 0.5")
        conn.commit()
        log.info("Migration: added yes_bet_ratio column to wallets")
    except sqlite3.OperationalError:
        pass  # column already exists

    log.info("Database schema initialised")


# ---------------------------------------------------------------------------
# Market CRUD
# ---------------------------------------------------------------------------
def upsert_market(conn: sqlite3.Connection, m: Market) -> None:
    conn.execute(
        """
        INSERT INTO markets (id, title, description, end_date, resolved, outcome, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            description=excluded.description,
            end_date=excluded.end_date,
            resolved=excluded.resolved,
            outcome=excluded.outcome
        """,
        (m.id, m.title, m.description, _ts(m.end_date), m.resolved, m.outcome, _ts(m.created_at)),
    )


def get_market(conn: sqlite3.Connection, market_id: str) -> Optional[Market]:
    row = conn.execute("SELECT * FROM markets WHERE id = ?", (market_id,)).fetchone()
    if row is None:
        return None
    return Market(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        end_date=_dt(row["end_date"]),
        resolved=bool(row["resolved"]),
        outcome=row["outcome"],
        created_at=_dt(row["created_at"]),
    )


def get_all_markets(conn: sqlite3.Connection, resolved_only: bool = False) -> list[Market]:
    q = "SELECT * FROM markets"
    if resolved_only:
        q += " WHERE resolved = 1"
    rows = conn.execute(q).fetchall()
    return [
        Market(
            id=r["id"], title=r["title"], description=r["description"],
            end_date=_dt(r["end_date"]), resolved=bool(r["resolved"]),
            outcome=r["outcome"], created_at=_dt(r["created_at"]),
        )
        for r in rows
    ]


def get_resolved_markets_needing_backfill(
    conn: sqlite3.Connection,
    min_bets: int = 5,
    limit: int = 100,
    min_end_date: datetime | None = None,
) -> list[Market]:
    """Return resolved markets in the DB that have fewer than min_bets bets.

    Ordered by end_date DESC so we prioritise recent markets (more likely to
    still have trade data available via the Data API).

    min_end_date: skip markets that resolved before this date (Data API likely dry).
    """
    if min_end_date is not None:
        cutoff = min_end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = conn.execute(
            """
            SELECT m.*
            FROM markets m
            WHERE m.resolved = 1
              AND m.end_date >= ?
              AND (SELECT COUNT(*) FROM bets b WHERE b.market_id = m.id) < ?
            ORDER BY m.end_date DESC
            LIMIT ?
            """,
            (cutoff, min_bets, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT m.*
            FROM markets m
            WHERE m.resolved = 1
              AND (SELECT COUNT(*) FROM bets b WHERE b.market_id = m.id) < ?
            ORDER BY m.end_date DESC
            LIMIT ?
            """,
            (min_bets, limit),
        ).fetchall()
    return [
        Market(
            id=r["id"], title=r["title"], description=r["description"],
            end_date=_dt(r["end_date"]), resolved=bool(r["resolved"]),
            outcome=r["outcome"], created_at=_dt(r["created_at"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Bet CRUD
# ---------------------------------------------------------------------------
def insert_bet(conn: sqlite3.Connection, b: Bet) -> None:
    conn.execute(
        """
        INSERT INTO bets (market_id, wallet, side, amount, odds, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (b.market_id, b.wallet, b.side, b.amount, b.odds, _ts(b.timestamp)),
    )
    conn.commit()


def insert_bets_bulk(conn: sqlite3.Connection, bets: list[Bet]) -> int:
    if not bets:
        return 0
    conn.executemany(
        """
        INSERT OR IGNORE INTO bets (market_id, wallet, side, amount, odds, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(b.market_id, b.wallet, b.side, b.amount, b.odds, _ts(b.timestamp)) for b in bets],
    )
    conn.commit()
    return len(bets)


def get_bets_for_market(conn: sqlite3.Connection, market_id: str) -> list[Bet]:
    rows = conn.execute(
        "SELECT * FROM bets WHERE market_id = ? ORDER BY timestamp", (market_id,)
    ).fetchall()
    return [
        Bet(
            id=r["id"], market_id=r["market_id"], wallet=r["wallet"],
            side=r["side"], amount=r["amount"], odds=r["odds"],
            timestamp=_dt(r["timestamp"]),
        )
        for r in rows
    ]


def get_bets_for_wallet(conn: sqlite3.Connection, wallet: str) -> list[Bet]:
    rows = conn.execute(
        "SELECT * FROM bets WHERE wallet = ? ORDER BY timestamp", (wallet,)
    ).fetchall()
    return [
        Bet(
            id=r["id"], market_id=r["market_id"], wallet=r["wallet"],
            side=r["side"], amount=r["amount"], odds=r["odds"],
            timestamp=_dt(r["timestamp"]),
        )
        for r in rows
    ]


def get_latest_bet_timestamp(conn: sqlite3.Connection, market_id: str) -> Optional[datetime]:
    row = conn.execute(
        "SELECT MAX(timestamp) AS ts FROM bets WHERE market_id = ?", (market_id,)
    ).fetchone()
    if row and row["ts"]:
        return _dt(row["ts"])
    return None


# ---------------------------------------------------------------------------
# Wallet CRUD
# ---------------------------------------------------------------------------
def upsert_wallet(conn: sqlite3.Connection, w: Wallet) -> None:
    conn.execute(
        """
        INSERT INTO wallets (address, first_seen, total_bets, total_volume,
                             win_rate, rationality_score, flagged_suspicious, flagged_sandpit,
                             yes_bet_ratio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(address) DO UPDATE SET
            total_bets=excluded.total_bets,
            total_volume=excluded.total_volume,
            win_rate=excluded.win_rate,
            rationality_score=excluded.rationality_score,
            flagged_suspicious=excluded.flagged_suspicious,
            flagged_sandpit=excluded.flagged_sandpit,
            yes_bet_ratio=excluded.yes_bet_ratio
        """,
        (w.address, _ts(w.first_seen), w.total_bets, w.total_volume,
         w.win_rate, w.rationality_score, w.flagged_suspicious, w.flagged_sandpit,
         w.yes_bet_ratio),
    )
    conn.commit()


def seed_wallets_batch(conn: sqlite3.Connection, wallet_entries: list[dict]) -> int:
    """Insert new wallets from leaderboard data without overwriting existing records.

    wallet_entries: list of {"address": str, "volume": float, "pnl": float}
    Returns count of newly inserted rows.
    """
    now = _ts(datetime.now(timezone.utc).replace(tzinfo=None))
    rows = [
        (e["address"], now, 0, float(e.get("volume") or 0), 0.0, 0.5, 0, 0, 0.5)
        for e in wallet_entries
        if e.get("address")
    ]
    if not rows:
        return 0
    cur = conn.executemany(
        """
        INSERT OR IGNORE INTO wallets
            (address, first_seen, total_bets, total_volume,
             win_rate, rationality_score, flagged_suspicious, flagged_sandpit,
             yes_bet_ratio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return cur.rowcount


def get_wallet(conn: sqlite3.Connection, address: str) -> Optional[Wallet]:
    row = conn.execute("SELECT * FROM wallets WHERE address = ?", (address,)).fetchone()
    if row is None:
        return None
    return Wallet(
        address=row["address"], first_seen=_dt(row["first_seen"]),
        total_bets=row["total_bets"], total_volume=row["total_volume"],
        win_rate=row["win_rate"], rationality_score=row["rationality_score"],
        flagged_suspicious=bool(row["flagged_suspicious"]),
        flagged_sandpit=bool(row["flagged_sandpit"]),
        yes_bet_ratio=float(row["yes_bet_ratio"] or 0.5),
    )


def get_all_wallets(conn: sqlite3.Connection) -> dict[str, Wallet]:
    rows = conn.execute("SELECT * FROM wallets").fetchall()
    return {
        r["address"]: Wallet(
            address=r["address"], first_seen=_dt(r["first_seen"]),
            total_bets=r["total_bets"], total_volume=r["total_volume"],
            win_rate=r["win_rate"], rationality_score=r["rationality_score"],
            flagged_suspicious=bool(r["flagged_suspicious"]),
            flagged_sandpit=bool(r["flagged_sandpit"]),
            yes_bet_ratio=float(r["yes_bet_ratio"] or 0.5),
        )
        for r in rows
    }


# ---------------------------------------------------------------------------
# Wallet Relationships
# ---------------------------------------------------------------------------
def upsert_relationship(conn: sqlite3.Connection, rel: WalletRelationship) -> None:
    conn.execute(
        """
        INSERT INTO wallet_relationships (wallet_a, wallet_b, relationship_type, confidence)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(wallet_a, wallet_b) DO UPDATE SET
            relationship_type=excluded.relationship_type,
            confidence=excluded.confidence
        """,
        (rel.wallet_a, rel.wallet_b, rel.relationship_type, rel.confidence),
    )


def upsert_relationships_batch(conn: sqlite3.Connection, rels: list) -> None:
    conn.executemany(
        """
        INSERT INTO wallet_relationships (wallet_a, wallet_b, relationship_type, confidence)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(wallet_a, wallet_b) DO UPDATE SET
            relationship_type=excluded.relationship_type,
            confidence=MAX(confidence, excluded.confidence)
        """,
        [(r.wallet_a, r.wallet_b, r.relationship_type, r.confidence) for r in rels],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Method Results
# ---------------------------------------------------------------------------
def insert_method_result(conn: sqlite3.Connection, cr: ComboResults) -> None:
    conn.execute(
        """
        INSERT INTO method_results (combo_id, methods_used, accuracy, edge_vs_market,
                                    false_positive_rate, complexity, fitness_score, tested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(combo_id) DO UPDATE SET
            accuracy=excluded.accuracy,
            edge_vs_market=excluded.edge_vs_market,
            false_positive_rate=excluded.false_positive_rate,
            complexity=excluded.complexity,
            fitness_score=excluded.fitness_score,
            tested_at=excluded.tested_at
        WHERE excluded.fitness_score >= method_results.fitness_score
        """,
        (cr.combo_id, json.dumps(cr.methods_used), cr.accuracy, cr.edge_vs_market,
         cr.false_positive_rate, cr.complexity, cr.fitness_score, _ts(cr.tested_at)),
    )


def flush_method_results(conn: sqlite3.Connection) -> None:
    """Commit any pending method result inserts."""
    conn.commit()


def prune_method_results(conn: sqlite3.Connection, keep: int = 50) -> int:
    """Delete all but the top N results by fitness. Returns rows deleted."""
    deleted = conn.execute(
        """DELETE FROM method_results WHERE id NOT IN (
               SELECT id FROM method_results ORDER BY fitness_score DESC LIMIT ?
           )""",
        (keep,),
    ).rowcount
    conn.commit()
    return deleted


def insert_holdout_result(
    conn: sqlite3.Connection,
    combo_id: str,
    train_cr: ComboResults,
    holdout_cr: ComboResults,
    train_n: int,
    holdout_n: int,
) -> None:
    conn.execute(
        """
        INSERT INTO holdout_validation
        (validated_at, combo_id, train_markets, holdout_markets,
         train_fitness, holdout_fitness, train_accuracy, holdout_accuracy,
         train_edge, holdout_edge, train_fpr, holdout_fpr)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), combo_id, train_n, holdout_n,
            train_cr.fitness_score, holdout_cr.fitness_score,
            train_cr.accuracy, holdout_cr.accuracy,
            train_cr.edge_vs_market, holdout_cr.edge_vs_market,
            train_cr.false_positive_rate, holdout_cr.false_positive_rate,
        ),
    )


def get_latest_holdout_results(conn: sqlite3.Connection, limit: int = 3) -> list:
    """Get the most recent holdout validation rows ordered by validated_at."""
    return conn.execute(
        """
        SELECT combo_id, train_markets, holdout_markets,
               train_fitness, holdout_fitness,
               train_accuracy, holdout_accuracy,
               train_edge, holdout_edge
        FROM holdout_validation
        ORDER BY validated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Predictions CRUD
# ---------------------------------------------------------------------------
def insert_prediction(
    conn: sqlite3.Connection,
    market_id: str,
    predicted_at: str,
    predicted_side: str,
    market_price: float,
    bot_signal: float,
    bot_confidence: float,
    bot_edge: float,
    combo_id: str,
) -> None:
    """Log a pick at report generation time. resolved_at/actual_outcome/correct filled later."""
    conn.execute(
        """
        INSERT INTO predictions
            (market_id, predicted_at, predicted_side, market_price_at_prediction,
             bot_signal, bot_confidence, bot_edge, combo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (market_id, predicted_at, predicted_side, market_price,
         bot_signal, bot_confidence, bot_edge, combo_id),
    )


def update_prediction_outcomes(conn: sqlite3.Connection) -> int:
    """Fill in actual_outcome + correct for any predictions whose market has since resolved.

    Returns the number of rows updated.
    """
    cur = conn.execute(
        """
        UPDATE predictions
        SET
            actual_outcome = (
                SELECT m.outcome FROM markets m WHERE m.id = predictions.market_id
            ),
            resolved_at = (
                SELECT m.end_date FROM markets m WHERE m.id = predictions.market_id
            ),
            correct = CASE
                WHEN (SELECT m.outcome FROM markets m WHERE m.id = predictions.market_id)
                     = predictions.predicted_side
                THEN 1 ELSE 0
            END
        WHERE correct IS NULL
          AND EXISTS (
              SELECT 1 FROM markets m
              WHERE m.id = predictions.market_id
                AND m.resolved = 1
                AND m.outcome IS NOT NULL
          )
        """
    )
    conn.commit()
    return cur.rowcount


def get_top_combos(conn: sqlite3.Connection, limit: int = 10) -> list[ComboResults]:
    rows = conn.execute(
        "SELECT * FROM method_results ORDER BY fitness_score DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        ComboResults(
            combo_id=r["combo_id"],
            methods_used=json.loads(r["methods_used"]),
            accuracy=r["accuracy"],
            edge_vs_market=r["edge_vs_market"],
            false_positive_rate=r["false_positive_rate"],
            complexity=r["complexity"],
            fitness_score=r["fitness_score"],
            tested_at=_dt(r["tested_at"]),
        )
        for r in rows
    ]
