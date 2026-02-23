-- =============================================================================
-- SDC Prioritizer – PostgreSQL Schema - PostgreSQL keeps Metadata & Report
-- =============================================================================
-- TABLES:
    -- test_suites holds metadata for existence check
    -- prioritizations:
    -- evaluations:
-- =============================================================================

CREATE TABLE IF NOT EXISTS test_suites (
    suite_id        VARCHAR(255) PRIMARY KEY,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    test_count      INTEGER      NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_history (
    evaluation_id       SERIAL          PRIMARY KEY,
    suite_id            VARCHAR(255)    NOT NULL REFERENCES test_suites(suite_id) ON DELETE CASCADE,
    strategy            VARCHAR(255)    NOT NULL,
    test_count          INTEGER         NOT NULL,
    failures_detected   INTEGER         NOT NULL,
    execution_cost      INTEGER         NOT NULL,
    score               DOUBLE PRECISION NOT NULL,
    duration_ms         INTEGER         NOT NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_history_suite
    ON evaluation_history(suite_id);