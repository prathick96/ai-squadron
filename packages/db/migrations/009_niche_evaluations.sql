-- AI Squadron — Migration 009: Niche evaluation memory
-- Prevents the CEO from re-evaluating failed niches.
-- Stores scoring history and feeds outcomes back for portfolio learning.

CREATE TABLE IF NOT EXISTS niche_evaluations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    niche               TEXT NOT NULL,
    venture_type        TEXT NOT NULL DEFAULT 'MICRO_SAAS'
                        CHECK (venture_type IN ('MICRO_SAAS', 'MEDIA_CHANNEL', 'AFFILIATE_SITE')),

    -- 4-dimension CEO scoring rubric (0-25 each, 100 total)
    tam_score           INTEGER DEFAULT 0 CHECK (tam_score BETWEEN 0 AND 25),
    competition_gap     INTEGER DEFAULT 0 CHECK (competition_gap BETWEEN 0 AND 25),
    build_score         INTEGER DEFAULT 0 CHECK (build_score BETWEEN 0 AND 25),
    revenue_velocity    INTEGER DEFAULT 0 CHECK (revenue_velocity BETWEEN 0 AND 25),
    confidence_score    INTEGER GENERATED ALWAYS AS (tam_score + competition_gap + build_score + revenue_velocity) STORED,

    -- Scout reports summary
    trend_summary       TEXT,
    skeptic_argument    TEXT,           -- the strongest rejection argument
    audience_persona    TEXT,           -- named buyer, specific pain
    build_estimate_days INTEGER,        -- sprint estimate from Builder scout

    -- Decision and outcome
    go_decision         BOOLEAN DEFAULT FALSE,
    go_rationale        TEXT,
    outcome             TEXT DEFAULT 'PENDING'
                        CHECK (outcome IN ('PENDING', 'BUILT', 'KILL', 'SCALE')),
    outcome_reason      TEXT,           -- WHY it was killed (execution? market? build?)
    venture_id          VARCHAR(64),    -- FK when a venture was actually built
    run_id              VARCHAR(64),    -- pipeline run that produced this evaluation

    -- Shortlist siblings (niches ranked #2 and #3 from the same run)
    niche_rank          INTEGER DEFAULT 1 CHECK (niche_rank BETWEEN 1 AND 3),
    run_shortlist_id    UUID,           -- groups the 3 niches from one run together

    evaluated_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_niche_eval_niche   ON niche_evaluations(niche);
CREATE INDEX IF NOT EXISTS idx_niche_eval_outcome ON niche_evaluations(outcome);
CREATE INDEX IF NOT EXISTS idx_niche_eval_score   ON niche_evaluations(confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_niche_eval_venture ON niche_evaluations(venture_id);

-- Unique on (niche, venture_type) — don't evaluate the same combo twice
CREATE UNIQUE INDEX IF NOT EXISTS idx_niche_eval_unique
    ON niche_evaluations(lower(niche), venture_type)
    WHERE outcome != 'PENDING';

CREATE TRIGGER niche_eval_updated_at
    BEFORE UPDATE ON niche_evaluations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Convenience view: niches to avoid on future runs
CREATE OR REPLACE VIEW exhausted_niches AS
SELECT DISTINCT lower(niche) AS niche_lower, niche, venture_type, outcome, confidence_score
FROM niche_evaluations
WHERE outcome IN ('KILL', 'SCALE', 'BUILT')
   OR (outcome = 'PENDING' AND evaluated_at > NOW() - INTERVAL '7 days');
