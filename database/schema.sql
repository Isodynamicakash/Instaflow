-- InstaFlow — Full Database Schema (for Supabase Phase 2)

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ig_user_id TEXT UNIQUE NOT NULL,
    ig_username TEXT NOT NULL DEFAULT '',
    access_token TEXT NOT NULL,
    whatsapp_number TEXT DEFAULT '',
    onboarding_data JSONB DEFAULT '{}',
    brand_voice TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ig_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    ig_media_id TEXT UNIQUE NOT NULL,
    media_type TEXT DEFAULT 'IMAGE',
    caption TEXT DEFAULT '',
    hashtags TEXT[] DEFAULT '{}',
    permalink TEXT DEFAULT '',
    timestamp TIMESTAMPTZ
);

CREATE TABLE ig_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id TEXT NOT NULL,
    impressions INT DEFAULT 0,
    reach INT DEFAULT 0,
    saved INT DEFAULT 0,
    shares INT DEFAULT 0,
    likes_count INT DEFAULT 0,
    comments_count INT DEFAULT 0,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE engagement_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    trigger_keywords TEXT[] DEFAULT '{}',
    comment_reply TEXT DEFAULT 'Check your DMs! 📩',
    dm_template TEXT DEFAULT '',
    dm_payload JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE engagement_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    rule_id UUID REFERENCES engagement_rules(id),
    action_type TEXT NOT NULL,
    ig_sender_username TEXT DEFAULT '',
    message_sent TEXT DEFAULT '',
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE content_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    generated_captions JSONB DEFAULT '[]',
    selected_index INT,
    status TEXT DEFAULT 'pending',
    scheduled_for TIMESTAMPTZ,
    posted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE posting_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    day_of_week INT,
    hour_of_day INT,
    avg_reach FLOAT DEFAULT 0,
    avg_engagement FLOAT DEFAULT 0,
    sample_count INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_posts_user ON ig_posts(user_id);
CREATE INDEX idx_metrics_post ON ig_metrics(post_id);
CREATE INDEX idx_rules_user ON engagement_rules(user_id);
CREATE INDEX idx_log_user ON engagement_log(user_id);
CREATE INDEX idx_log_created ON engagement_log(created_at DESC);
CREATE INDEX idx_content_user ON content_queue(user_id);
