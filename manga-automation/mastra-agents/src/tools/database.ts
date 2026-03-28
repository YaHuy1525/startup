import { Pool } from 'pg';
import { createClient } from 'redis';
import { createLogger, format, transports } from 'winston';

// ─── Logger ──────────────────────────────────────────────────────────────────
export const logger = createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: format.combine(
        format.timestamp(),
        format.errors({ stack: true }),
        format.json()
    ),
    transports: [
        new transports.Console({
            format: format.combine(format.colorize(), format.simple())
        })
    ]
});

// ─── PostgreSQL ───────────────────────────────────────────────────────────────
// URL-encode '#' in the password portion so Node's URL parser doesn't treat it
// as a fragment delimiter (e.g. Supabase passwords can contain '#').
const _rawDbUrl = process.env.DATABASE_URL || '';
const _safeDbUrl = _rawDbUrl.replace(/:([^:@/]*?)#([^@]*)@/, ':$1%23$2@');

export const db = new Pool({
    connectionString: _safeDbUrl,
    max: 10,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
});

db.on('error', (err) => {
    logger.error('Unexpected DB client error', { error: err.message });
});

// ─── Redis ────────────────────────────────────────────────────────────────────
// reconnectStrategy: false means one attempt only — no retry storm on local dev
export const redis = createClient({
    url: process.env.REDIS_URL || 'redis://localhost:6379',
    socket: {
        reconnectStrategy: false,
        connectTimeout: 2000,
    }
});

let redisAvailable = false;

redis.on('error', () => { /* suppress — already warned at startup */ });

export async function connectDatabases() {
    // Redis is optional. The render/upload pipeline works fine without it.
    try {
        await redis.connect();
        redisAvailable = true;
        logger.info('✅ Redis connected');
    } catch {
        logger.warn('⚠️  Redis unavailable (caching disabled) — continuing without it');
    }

    await db.query('SELECT 1'); // verify PostgreSQL connection
    logger.info('✅ PostgreSQL connected — Manga Agents ready');
}

// ─── Cache helper ─────────────────────────────────────────────────────────────
export async function getCached<T>(key: string, ttlSeconds: number, fn: () => Promise<T>): Promise<T> {
    if (!redisAvailable) return fn();
    try {
        const cached = await redis.get(key);
        if (cached) return JSON.parse(cached) as T;
        const result = await fn();
        await redis.setEx(key, ttlSeconds, JSON.stringify(result));
        return result;
    } catch {
        return fn(); // Redis went away mid-run — fall through
    }
}
