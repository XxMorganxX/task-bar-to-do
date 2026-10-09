-- ============================================================================
-- to-do_app schema. Run once in the Supabase SQL Editor.
-- ============================================================================

-- Todos: one row per todo, scoped by user_id (TODO_USER in .env).
CREATE TABLE IF NOT EXISTS todos (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT,
    due_at TIMESTAMPTZ,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    source_type TEXT NOT NULL,                          -- manual, claude_code, calendar, voice, discord
    source_id TEXT,
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb, -- category (todo_group), calendar links, reminders
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_todos_user_completed_due ON todos(user_id, completed, due_at);
CREATE INDEX IF NOT EXISTS idx_todos_created_at ON todos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_todos_source ON todos(user_id, source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_todos_source_metadata ON todos USING gin (source_metadata);
CREATE INDEX IF NOT EXISTS idx_todos_group_name ON todos ((source_metadata->>'todo_group'));

-- Briefing announcements: after every todo change the app queues "todo digest" rows here
-- (what's due, what's overdue) for a voice assistant or chat bot to deliver. The app only
-- writes them; nothing in this repo reads them. The table must exist even if unused.
CREATE TABLE IF NOT EXISTS briefing_announcements (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content JSONB NOT NULL,            -- { message, llm_instructions?, active_from?, meta? }
    opener_text TEXT,
    priority TEXT DEFAULT 'normal',    -- high | normal | low
    status TEXT DEFAULT 'pending',     -- pending | dismissed | skipped | cancelled | expired
    discord_status TEXT NOT NULL DEFAULT 'pending',
    discord_sent_at TIMESTAMPTZ,
    voice_status TEXT NOT NULL DEFAULT 'pending',
    voice_read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_briefings_user_status ON briefing_announcements(user_id, status);
CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefing_announcements(created_at DESC);
