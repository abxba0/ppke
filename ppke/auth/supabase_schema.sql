-- Supabase schema for PPKE
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)
--
-- This creates a `profiles` table (linked to auth.users) and all the
-- application tables.  Row-Level Security (RLS) policies are included
-- so Supabase's PostgREST respects user context.

-- ────────────────────────────────────────────────────────────────────
-- 1. Profiles — mirrors auth.users with app-specific fields
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS profiles (
    id          TEXT PRIMARY KEY,  -- same as auth.users.id
    email       TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL DEFAULT '',
    oauth_provider TEXT DEFAULT NULL,
    oauth_id    TEXT DEFAULT NULL,
    role        TEXT NOT NULL DEFAULT 'user',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TEXT NOT NULL DEFAULT now()::text,
    updated_at  TEXT NOT NULL DEFAULT now()::text
);

-- Auto-create profile row when a user signs up via Supabase Auth
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
    INSERT INTO public.profiles (id, email, name, oauth_provider, oauth_id, created_at, updated_at)
    VALUES (
        NEW.id::text,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        NEW.raw_app_meta_data->>'provider',
        NEW.id::text,
        now()::text,
        now()::text
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ────────────────────────────────────────────────────────────────────
-- 2. Application tables
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS workspaces (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE NOT NULL,
    owner_id    TEXT NOT NULL REFERENCES profiles(id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_members (
    id          TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'viewer',
    invited_by  TEXT REFERENCES profiles(id),
    created_at  TEXT NOT NULL,
    UNIQUE(workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS shared_books (
    id          TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    book_folder TEXT NOT NULL,
    shared_by   TEXT NOT NULL REFERENCES profiles(id),
    permissions TEXT NOT NULL DEFAULT 'view',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    book_folder TEXT NOT NULL,
    paragraph_id TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    annotation_type TEXT NOT NULL DEFAULT 'note',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    workspace_id TEXT REFERENCES workspaces(id),
    action      TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT '',
    target_id   TEXT NOT NULL DEFAULT '',
    details     TEXT DEFAULT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    provider    TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    workspace_id TEXT REFERENCES workspaces(id),
    action      TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL NOT NULL DEFAULT 0.0,
    provider    TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    book_folder TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_invites (
    id          TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'viewer',
    invited_by  TEXT NOT NULL REFERENCES profiles(id),
    status      TEXT NOT NULL DEFAULT 'pending',
    token       TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    accepted_at TEXT DEFAULT NULL,
    UNIQUE(workspace_id, email)
);


-- ────────────────────────────────────────────────────────────────────
-- 3. Indexes
-- ────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_wm_workspace ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_wm_user ON workspace_members(user_id);
CREATE INDEX IF NOT EXISTS idx_annotations_book ON annotations(book_folder);
CREATE INDEX IF NOT EXISTS idx_annotations_user ON annotations(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_workspace ON activity_log(workspace_id);
CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_records(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_book ON usage_records(book_folder);
CREATE INDEX IF NOT EXISTS idx_shared_books_ws ON shared_books(workspace_id);
CREATE INDEX IF NOT EXISTS idx_invites_email ON workspace_invites(email);
CREATE INDEX IF NOT EXISTS idx_invites_token ON workspace_invites(token);
CREATE INDEX IF NOT EXISTS idx_invites_ws ON workspace_invites(workspace_id);


-- ────────────────────────────────────────────────────────────────────
-- 4. Row-Level Security (RLS)
-- ────────────────────────────────────────────────────────────────────

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared_books ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_invites ENABLE ROW LEVEL SECURITY;

-- Profiles: users see their own row; service role sees all
CREATE POLICY "Users read own profile" ON profiles
    FOR SELECT USING (auth.uid()::text = id);
CREATE POLICY "Users update own profile" ON profiles
    FOR UPDATE USING (auth.uid()::text = id);
CREATE POLICY "Service inserts profiles" ON profiles
    FOR INSERT WITH CHECK (true);

-- Workspaces: members can see their workspaces
CREATE POLICY "Members see workspaces" ON workspaces
    FOR SELECT USING (
        id IN (SELECT workspace_id FROM workspace_members WHERE user_id = auth.uid()::text)
    );
CREATE POLICY "Anyone creates workspace" ON workspaces
    FOR INSERT WITH CHECK (owner_id = auth.uid()::text);

-- Workspace members
CREATE POLICY "Members see members" ON workspace_members
    FOR SELECT USING (
        workspace_id IN (SELECT workspace_id FROM workspace_members wm2 WHERE wm2.user_id = auth.uid()::text)
    );
CREATE POLICY "Admins manage members" ON workspace_members
    FOR ALL USING (
        workspace_id IN (
            SELECT workspace_id FROM workspace_members wm2
            WHERE wm2.user_id = auth.uid()::text AND wm2.role = 'admin'
        )
    );

-- API keys: only owner
CREATE POLICY "Own api keys" ON api_keys
    FOR ALL USING (user_id = auth.uid()::text);

-- Usage records: only owner
CREATE POLICY "Own usage" ON usage_records
    FOR ALL USING (user_id = auth.uid()::text);

-- Activity: workspace members or own
CREATE POLICY "Activity read" ON activity_log
    FOR SELECT USING (
        user_id = auth.uid()::text
        OR workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = auth.uid()::text)
    );
CREATE POLICY "Activity insert" ON activity_log
    FOR INSERT WITH CHECK (user_id = auth.uid()::text);

-- Annotations: own or workspace members
CREATE POLICY "Annotations read" ON annotations
    FOR SELECT USING (
        user_id = auth.uid()::text
        OR workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = auth.uid()::text)
    );
CREATE POLICY "Annotations write own" ON annotations
    FOR INSERT WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY "Annotations delete own" ON annotations
    FOR DELETE USING (user_id = auth.uid()::text);

-- Shared books: workspace members
CREATE POLICY "Shared books read" ON shared_books
    FOR SELECT USING (
        workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = auth.uid()::text)
    );
CREATE POLICY "Shared books write" ON shared_books
    FOR INSERT WITH CHECK (
        workspace_id IN (
            SELECT workspace_id FROM workspace_members
            WHERE user_id = auth.uid()::text AND role IN ('admin', 'editor')
        )
    );

-- Invites: workspace members see invites; invited email can see own
CREATE POLICY "Invites read" ON workspace_invites
    FOR SELECT USING (
        email = (SELECT email FROM profiles WHERE id = auth.uid()::text)
        OR workspace_id IN (SELECT workspace_id FROM workspace_members WHERE user_id = auth.uid()::text)
    );
CREATE POLICY "Invites create" ON workspace_invites
    FOR INSERT WITH CHECK (
        workspace_id IN (
            SELECT workspace_id FROM workspace_members
            WHERE user_id = auth.uid()::text AND role IN ('admin', 'editor')
        )
    );
CREATE POLICY "Invites update" ON workspace_invites
    FOR UPDATE USING (
        email = (SELECT email FROM profiles WHERE id = auth.uid()::text)
        OR workspace_id IN (
            SELECT workspace_id FROM workspace_members
            WHERE user_id = auth.uid()::text AND role IN ('admin', 'editor')
        )
    );
