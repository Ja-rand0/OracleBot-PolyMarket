import os

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
API_MAX_RETRIES = 3
API_RETRY_BACKOFF = 2          # exponential base: 2^attempt seconds
API_REQUEST_TIMEOUT = 30       # seconds

GAMMA_BASE_URL            = "https://gamma-api.polymarket.com"
GAMMA_MARKETS_ENDPOINT    = "https://gamma-api.polymarket.com/markets"
POLYMARKET_BASE_URL       = "https://clob.polymarket.com"
POLYMARKET_MARKETS_ENDPOINT = "https://clob.polymarket.com/markets"
POLYGONSCAN_BASE_URL      = "https://api.polygonscan.com/api"
POLYGONSCAN_API_KEY       = os.getenv("POLYGONSCAN_API_KEY", "")

MARKETS_PAGE_SIZE = 100
TRADES_PAGE_SIZE  = 500

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# Fitness weights: accuracy * W_ACCURACY + edge * W_EDGE - FPR * W_FALSE_POS
#                  - (complexity / TOTAL_METHODS) * W_COMPLEXITY
#
# These weights are PROVISIONAL — set by engineering intuition, not grid search.
# Rationale for current values:
#   - Accuracy and edge share equal weight (0.35 each) because both matter:
#     a combo that's right often but never beats the market is useless, and
#     vice versa.
#   - FPR penalised at 0.20: high-confidence wrong predictions are costly
#     (real money), but not penalised as much as being correct is rewarded.
#   - Complexity penalised at 0.10: Occam's razor — prefer simpler combos
#     that generalise, but not so aggressively that single-method combos always win.
#
# To empirically validate, run a grid search over weight space with 500+ resolved
# markets and compare out-of-sample accuracy of the resulting top combos.
# Until then, treat these as reasonable priors, not ground truth.
FITNESS_W_ACCURACY    = 0.35
FITNESS_W_EDGE        = 0.35
FITNESS_W_FALSE_POS   = 0.20
FITNESS_W_COMPLEXITY  = 0.10

BACKTEST_CUTOFF_FRACTION  = 0.70   # use first 70% of market lifespan
TIER1_TOP_PER_CATEGORY    = 5
TIER2_TOP_OVERALL         = 10
SCRAPE_INTERVAL_MINUTES   = 30
ANALYZE_INTERVAL_HOURS    = 6
TOTAL_METHODS             = 25
BACKFILL_MAX_AGE_DAYS     = 365    # skip resolved markets older than this (Data API likely dry)
HOLDOUT_FRACTION          = 0.20   # 20% of resolved markets held out for validation

DB_PATH = "polymarket.db"

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
REPORT_PRICE_RECENT_TRADES = 10
REPORT_PRICE_MIN_TRADES    = 3

# ---------------------------------------------------------------------------
# Method thresholds — S (Suspicious Wallet)
# ---------------------------------------------------------------------------
S1_MIN_RESOLVED_BETS   = 10
S1_STDDEV_THRESHOLD    = 2.0

S3_TIME_WINDOW_MINUTES = 10
S3_MIN_CO_MARKETS      = 2      # min co-occurrences per graph edge
S3_MIN_CLUSTER_SIZE    = 3

S4_SANDPIT_MIN_BETS      = 10
S4_SANDPIT_MAX_WIN_RATE  = 0.25
S4_SANDPIT_MIN_VOLUME    = 5000.0
S4_NEW_WALLET_MAX_BETS   = 3
S4_NEW_WALLET_LARGE_BET  = 2000.0

# ---------------------------------------------------------------------------
# Method thresholds — D (Discrete Math)
# ---------------------------------------------------------------------------
D7_MIN_BETS = 5

# ---------------------------------------------------------------------------
# Method thresholds — E (Emotional Bias)
# ---------------------------------------------------------------------------
E10_MIN_MARKETS             = 3
E10_CONSISTENCY_THRESHOLD   = 0.85

E12_WINDOW_HOURS            = 24

E13_VOLUME_SPIKE_MULTIPLIER = 3.0

E14_LOW_CORRELATION_THRESHOLD = 0.3

E15_ROUND_DIVISOR           = 50

E16_KL_THRESHOLD            = 0.5

# ---------------------------------------------------------------------------
# Method thresholds — T (Statistical)
# ---------------------------------------------------------------------------
T17_PRIOR_WEIGHT        = 1.0
T17_AMOUNT_NORMALIZER   = 50.0   # was 1000.0, +0.005 fitness (M3 tuning 2026-02-23)
T17_UPDATE_STEP         = 0.80   # was 0.10, +0.005 fitness (M3 tuning 2026-02-23)
T17_RATIONALITY_CUTOFF  = 0.58   # was 0.40, +0.022 fitness (M3 tuning 2026-02-23)

T18_CHI_SQUARED_PVALUE  = 0.05

T19_ZSCORE_THRESHOLD    = 2.5

# ---------------------------------------------------------------------------
# Method thresholds — P (Psychological)
# ---------------------------------------------------------------------------
P20_DEVIATION_THRESHOLD = 0.02   # was 0.10, +0.023 fitness (M3 tuning 2026-02-23)

P21_LOW_PROB  = 0.15
P21_HIGH_PROB = 0.85

P22_MIN_HERD_SIZE       = 10
P22_TIME_WINDOW_MINUTES = 60

P23_ANCHOR_MIN_AMOUNT   = 500.0

P24_LOW_RATIO  = 0.30
P24_HIGH_RATIO = 0.70

# ---------------------------------------------------------------------------
# Method thresholds — M (Markov Chain)
# ---------------------------------------------------------------------------
M26_NUM_WINDOWS       = 5
M26_LOW_THRESHOLD     = 0.35
M26_HIGH_THRESHOLD    = 0.65
M26_TRENDING_THRESHOLD = 0.33   # was 0.60, +0.039 to +0.047 fitness (M3 tuning 2026-02-23)

M27_NUM_WINDOWS        = 5
M27_FLOW_THRESHOLD     = 0.5
M27_MOMENTUM_THRESHOLD = 0.60

M28_SMART_THRESHOLD    = 0.6
M28_RETAIL_THRESHOLD   = 0.4
M28_NUM_WINDOWS        = 5
M28_MIN_SMART_WALLETS  = 3
M28_MIN_RETAIL_WALLETS = 3
