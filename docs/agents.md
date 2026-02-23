# Agent Full Specifications

> Routing table, guidelines, and agent reference: root `CLAUDE.md`
> This file contains full specs for active agents and stub activation specs.

---

## Backtest Analyst — Full Specification

**Model:** opus (needs reasoning for nuanced interpretation)

**Purpose:** Interprets combinator optimization results to answer: what's working, what's not, and what to change next. This is the feedback loop between "run the optimizer" and "make the bot better."

**Capabilities:**
1. **Combo diagnosis** — Given a combo's fitness breakdown (accuracy, edge, FPR, complexity), explain why it scores the way it does. Identify which methods contribute signal vs. which add noise.
2. **Method contribution** — Across all tested combos, rank methods by how often they appear in top-N results. Flag methods that never appear (candidates for removal or threshold adjustment).
3. **Category synergy** — Identify which cross-category pairings produce the best Tier 2 results. E.g., "S+M combos consistently outperform S+E combos."
4. **Fitness trend** — Compare current optimization run to previous runs. Is fitness improving? Plateauing? Degrading?
5. **Edge analysis** — For top picks, break down where the edge comes from: is it the bot disagreeing with the market, or is it high confidence on an already-likely outcome?
6. **False positive diagnosis** — When FPR is high, trace which methods are producing the false signals and on which market types.

**Data access:** Read-only SQLite queries on `method_results`, `markets`, `bets`, `wallets` tables. Same safety hook as `data-analyst` (`scripts/validate_readonly_query.py`).

**Input format:** Overseer provides context like "analyze the latest optimization run" or "compare M-category methods against the baseline."

**Output format:** Structured markdown with:
- Summary (2-3 key findings)
- Tables (method rankings, combo breakdowns)
- Recommendations (specific next steps: adjust threshold X, drop method Y, investigate market type Z)

**Example queries:**
- "Analyze the top 10 combos from the latest run — do any M methods appear?"
- "Which methods have the highest marginal fitness contribution?"
- "Why does combo [S1,E13,M27] have high accuracy but negative edge?"
- "Compare fitness distribution before and after adding Markov methods"

---

## Debug Doctor — Full Specification

**Model:** sonnet (fast enough for log parsing, smart enough for root cause analysis)

**Purpose:** The testing, debugging, and documentation agent. Reads all output the bot produces — logs, reports, test results — and maintains a clear picture of system health. After any code change, this agent validates the integration, catches regressions, and documents issues.

**Data sources (read-only):**
1. `bot.log` — Main runtime log. Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s` (ISO 8601 UTC). Contains INFO, WARNING, ERROR, and EXCEPTION entries with full stack traces.
2. `caretaker.log` — Watchdog process log. Format: `%(asctime)s [CARETAKER] %(message)s`. Tracks dashboard launches, crashes, restart counts, exit codes.
3. `reports/report_YYYY-MM-DD.md` — Daily markdown reports. Contains top picks, exploitable markets table, suspicious wallet activity, sandpit alerts, and method combo performance (top 5 by fitness).
4. `test_pipeline.py` output — 4-step pipeline test (fetch resolved markets → fetch trades → build wallet profiles → backtest combos).
5. `docs/PROCESS_LOG.md` Bug Tracking section — Resolved bugs (B-series), known issues (P-series), areas needing review.

**Capabilities:**

1. **Log analysis** — Parse `bot.log` for patterns:
   - Count errors/warnings per module per time window
   - Extract stack traces and group by root cause
   - Detect new error types that weren't present before a code change
   - Flag log growth anomalies (sudden burst of warnings = something broke)
   - Check for silent failures: methods returning `signal=0, confidence=0` with reason metadata

2. **Test execution & interpretation** — Run `test_pipeline.py` and interpret results:
   - Verify all 4 steps complete without exceptions
   - Check that new methods (M25-M28) execute during backtest step
   - Compare combo fitness scores against previous runs (regression detection)
   - Validate that method registration is correct: 28 methods, 6 categories

3. **Report validation** — Read latest report from `reports/` and check:
   - Are picks being generated? (empty picks = signal pipeline broken)
   - Are edge values reasonable? (negative edge or edge > 0.5 = suspicious)
   - Does the combo performance table include new methods?
   - Are madness ratios computed correctly? (NaN or 0.0 on all markets = bug)
   - Compare against previous reports: did quality degrade after a change?

4. **Regression detection** — After any code change:
   - Run the import smoke test: `from methods import CATEGORIES, METHODS; assert len(METHODS) == expected`
   - Verify no existing methods broke by checking for new exceptions in log
   - Compare method_results table: did previously-good combos lose fitness?
   - Check for import errors, missing config constants, type mismatches

5. **Bug documentation** — When an issue is found:
   - Assign the next available bug ID (B-series for resolved, P-series for known)
   - Document in the format matching PROCESS_LOG.md Bug Tracking tables
   - Include: module, risk level, description, and proposed fix
   - Cross-reference with existing known issues

6. **Caretaker health** — Read `caretaker.log` to check:
   - How many restarts occurred? (frequent restarts = unstable dashboard)
   - What were the exit codes? (non-zero = crash, not graceful shutdown)
   - Time between restarts (decreasing interval = cascading failure)

**Safety:** Read-only access to all files. Same `validate_readonly_query.py` hook applies for any database queries. Cannot modify source code — reports findings to overseer for action.

**Input format:** Overseer provides context like:
- "Validate the M25-M28 integration" (post-change validation)
- "Check bot.log for errors in the last 24 hours" (routine health check)
- "Compare today's report against last week's" (quality tracking)
- "Run test_pipeline.py and report results" (full pipeline test)

**Output format:** Structured markdown:
- **Status:** PASS / WARN / FAIL (overall assessment)
- **Findings:** Numbered list of issues with severity (critical/warning/info)
- **Log excerpts:** Relevant error/warning lines with timestamps
- **Report comparison:** Side-by-side metrics if comparing runs
- **Bug entries:** Pre-formatted rows for PROCESS_LOG.md Bug Tracking tables if new issues found
- **Recommendations:** Specific next steps for the overseer

**Example queries:**
- "We just added M25-M28. Validate everything still works."
- "Parse bot.log — any new errors since the last commit?"
- "Read the latest daily report. Are picks reasonable?"
- "Run test_pipeline and tell me if M methods show up in backtest results."
- "Check if caretaker has been restarting the dashboard excessively."
- "Compare reports from Feb 7, 10, and 11 — is quality trending up or down?"

**Post-change validation checklist** (run after any code modification):
1. Import test: `python -c "from methods import METHODS; print(len(METHODS))"`
2. Config test: `python -c "import config; print(config.TOTAL_METHODS)"`
3. Parse last 50 lines of `bot.log` for new ERROR/EXCEPTION entries
4. Read latest report in `reports/` — verify structure and non-empty picks
5. If methods changed: run `test_pipeline.py` step 4 (backtest) to verify execution
6. Report findings with PASS/WARN/FAIL status

---

## Task Decomposer — Full Specification

**Model:** sonnet

**Purpose:** Translates user intent into an executable work plan. Has two phases that may run sequentially within a single invocation:

- **Phase 0 — Requirements Clarification** (runs when input is vague, ambiguous, or in diagram/extended-context form): Reads the raw input and produces a written specification — a clear statement of what is wanted, acceptance criteria, and constraints. Output of Phase 0 is the input to Phase 1.
- **Phase 1 — Decomposition**: Given a clear specification, breaks work into ordered subtasks with explicit dependencies. Each subtask names the agent (or "direct") responsible, the input it receives, and the output it produces.

**When to run Phase 0 vs. skip to Phase 1:**
- Skip Phase 0 if the requirement is expressible in one clear sentence with no ambiguity.
- Run Phase 0 if the input includes: a diagram, extended technical context, a vague goal ("make the bot better at X"), conflicting constraints, or a requirement referencing things not yet defined in the codebase.

**Output format (Phase 0):**
- Restated requirement (1-3 sentences — Claude's interpretation)
- Assumptions made (bulleted — things inferred, not stated)
- Open questions (if any must be answered before planning proceeds)
- Constraints identified (performance, safety, backwards-compatibility)

**Output format (Phase 1):**
- Ordered task list with IDs (T1, T2, ...)
- Each task: agent/direct, input, output, depends-on
- Estimated complexity (tiny/medium/large)
- Risks flagged (irreversible steps, unknown dependencies)

**Example queries:**
- "Here is a data flow diagram for the new WebSocket integration. Plan the implementation." (Phase 0 + Phase 1)
- "Plan the implementation of the leaderboard wallet seeding feature." (Phase 1 only — requirement is clear)
- "The user wants to 'make the sharp signal more aggressive.' Interpret and plan." (Phase 0 + Phase 1)

---

## Stub Agents — Specs for Future Activation

### `method-auditor` (activate at M2: stable top-10 combos)
- Computes pairwise correlation between method signals across all tested markets
- Flags method pairs with correlation > 0.7 (redundant in combos)
- Validates each method's implementation matches its `methods/CLAUDE.md` algorithm description
- Reports methods that never appear in top-50 combos (dead weight)
- Suggests category rebalancing if one category dominates or is absent from winners

### `threshold-tuner` (activate at M3: method-auditor identifies threshold sensitivity)
- For each config constant, runs sensitivity analysis: what happens to top combo fitness if the threshold shifts +/-10%, +/-25%?
- Identifies constants with high sensitivity (small change = big fitness impact) vs. low sensitivity (can be simplified)
- Proposes concrete value changes with expected fitness delta
- Respects constraints: thresholds must remain physically meaningful (e.g., probability thresholds stay in 0-1)

### `api-health-checker` (activate at M4: source data APIs integrated)
- Pings all configured endpoints, reports HTTP status and response time
- Validates response JSON schemas match expected structure (catches silent API changes)
- Tracks rate limit headers where available, warns at 80% consumption
- Checks data freshness: last trade timestamp vs. now, flags stale markets
- Runs on haiku (cheapest model — this is mechanical work, not reasoning)

### `wallet-profiler` (activate at M5: leaderboard wallet seeding implemented)
- Given a wallet address, pulls full trade history from `bets` table
- Computes per-market performance: win/loss, timing relative to market lifecycle, size patterns
- Runs M25 wallet regime analysis on the wallet's history across markets
- Cross-references with S1 (is this wallet flagged as sharp?), S4 (sandpit?)
- Validates rationality_score against actual behavior patterns
- Output: wallet profile card with key stats, flags, and recommendation (track/ignore/investigate)
