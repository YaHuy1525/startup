// Shared types for the control dashboard.

export type SourceType = 'video' | 'arbitrage';

export interface PublishRef {
    platform: string;
    url?: string | null;
    status?: string | null;
    published_at?: string | null;
}

export interface Clip {
    id: number;
    source_type: SourceType;
    title: string;
    local_path: string | null;
    thumbnail_path: string | null;
    duration_secs: number | null;
    file_size_mb: number | null;
    status: string;
    source_url: string | null;
    created_at: string | null;
    published: PublishRef[];
}

export interface Account {
    id: string;
    type: string;      // platform e.g. tiktok, youtube
    account: string;   // display name/handle
}

export interface PublishRequest {
    clip_id: number;
    source_type: SourceType;
    channels: string[];
    selected_accounts?: Record<string, string[]>;
    account_ids?: string[];
    title?: string;
    desc?: string;
    caption?: string;
    hashtags?: string[];
    topics?: string[];
    cover_url?: string;
    publish_time?: string;
    yt_privacy?: 'public' | 'unlisted' | 'private';
}

export interface PublishResultRow {
    platform: string;
    account_id?: string;
    account?: string;
    success: boolean;
    flow_id?: string;
    verification?: string;
    error?: string;
}

export interface PublishResult {
    success?: boolean;
    result?: {
        published_count?: number;
        failed_count?: number;
        confirmed_count?: number;
        unverified_count?: number;
        results?: PublishResultRow[];
        channels?: Record<string, { success: number; failed: number }>;
    };
    media?: { public_url?: string; uploaded?: boolean };
    error?: string;
}
