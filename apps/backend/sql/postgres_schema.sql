CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL DEFAULT 'system',
    owner_user_id TEXT,
    owner_username TEXT,
    name TEXT NOT NULL,
    genre TEXT NOT NULL,
    genres JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    style_rules TEXT NOT NULL,
    world_template TEXT NOT NULL,
    character_template TEXT NOT NULL,
    outline_template TEXT NOT NULL,
    status TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE templates ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS genres JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS usage_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE templates ADD COLUMN IF NOT EXISTS owner_username TEXT;

CREATE TABLE IF NOT EXISTS genre_configs (
    value TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    required_any JSONB NOT NULL DEFAULT '[]'::jsonb,
    forbidden_any JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS membership_plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    free_chapter_quota INTEGER NOT NULL CHECK (free_chapter_quota >= 0),
    monthly_quota INTEGER NOT NULL CHECK (monthly_quota >= 0),
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS app_state (
    id TEXT PRIMARY KEY,
    active_plan_id TEXT NOT NULL REFERENCES membership_plans(id),
    free_remaining INTEGER NOT NULL CHECK (free_remaining >= 0),
    monthly_remaining INTEGER NOT NULL CHECK (monthly_remaining >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES membership_plans(id),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS safety_policies (
    id TEXT PRIMARY KEY,
    blocked_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    copyright_notice TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    title TEXT NOT NULL,
    genre TEXT NOT NULL,
    genres JSONB NOT NULL DEFAULT '[]'::jsonb,
    length_type TEXT NOT NULL,
    template_id TEXT,
    mode_default TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS foundation_tasks (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL
);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS genres JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE projects ALTER COLUMN template_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS project_memories (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    global_outline TEXT NOT NULL,
    character_cards JSONB NOT NULL DEFAULT '[]'::jsonb,
    character_profiles JSONB NOT NULL DEFAULT '[]'::jsonb,
    relationship_states JSONB NOT NULL DEFAULT '[]'::jsonb,
    world_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    event_summary JSONB NOT NULL DEFAULT '[]'::jsonb,
    story_beats JSONB NOT NULL DEFAULT '[]'::jsonb,
    active_phase JSONB NOT NULL DEFAULT '{}'::jsonb,
    chapter_summaries JSONB NOT NULL DEFAULT '[]'::jsonb,
    timeline_nodes JSONB NOT NULL DEFAULT '[]'::jsonb,
    foreshadow_threads JSONB NOT NULL DEFAULT '[]'::jsonb,
    major_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    fact_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    latest_chapter_index INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS character_profiles JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS relationship_states JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS chapter_summaries JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS timeline_nodes JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS foreshadow_threads JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS major_events JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS fact_records JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS story_beats JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE project_memories ADD COLUMN IF NOT EXISTS active_phase JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS chapter_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    start_chapter_index INTEGER NOT NULL CHECK (start_chapter_index >= 1),
    requested_chapter_count INTEGER NOT NULL CHECK (requested_chapter_count BETWEEN 1 AND 10),
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    current_chapter_index INTEGER NOT NULL,
    quota_cost INTEGER NOT NULL DEFAULT 0,
    chapter_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    selected_option_id TEXT,
    final_draft_id TEXT,
    needs_manual_review BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_by_user BOOLEAN NOT NULL DEFAULT FALSE,
    rewrite_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, chapter_index)
);

CREATE TABLE IF NOT EXISTS outline_options (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    option_no INTEGER NOT NULL CHECK (option_no BETWEEN 1 AND 3),
    content TEXT NOT NULL,
    core_conflict TEXT NOT NULL,
    key_event TEXT NOT NULL,
    ending_hook TEXT NOT NULL,
    score_plot NUMERIC(4, 2) NOT NULL,
    score_consistency NUMERIC(4, 2) NOT NULL,
    score_hook NUMERIC(4, 2) NOT NULL,
    score_phase_fit NUMERIC(4, 2) NOT NULL DEFAULT 0,
    phase_fit_hits JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_score NUMERIC(4, 2) NOT NULL,
    editor_comment TEXT NOT NULL,
    selected BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS chapter_drafts (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
    content TEXT NOT NULL,
    score_readability NUMERIC(4, 2) NOT NULL,
    score_tension NUMERIC(4, 2) NOT NULL,
    score_consistency NUMERIC(4, 2) NOT NULL,
    final_score NUMERIC(4, 2) NOT NULL,
    issue_summary TEXT NOT NULL,
    conflict_alerts JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE chapter_drafts ADD COLUMN IF NOT EXISTS conflict_alerts JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE outline_options ADD COLUMN IF NOT EXISTS score_phase_fit NUMERIC(4, 2) NOT NULL DEFAULT 0;
ALTER TABLE outline_options ADD COLUMN IF NOT EXISTS phase_fit_hits JSONB NOT NULL DEFAULT '[]'::jsonb;
