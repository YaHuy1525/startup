import axios from 'axios';
import { z } from 'zod';
import { db, getCached, logger } from './database';

// ─── Types ────────────────────────────────────────────────────────────────────
export interface MangaDexManga {
    id: string;
    title: string;
    description: string;
    coverUrl: string;
    tags: string[];
    status: string;
    followCount: number;
}

export interface MangaDexChapter {
    id: string;
    chapterNumber: string;
    title: string;
    publishedAt: string;
}

export interface ChapterPages {
    baseUrl: string;
    pages: string[];
}

const MANGADEX_BASE = 'https://api.mangadex.org';

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getCoverUrl(manga: any): string {
    const coverRel = manga.relationships?.find((r: any) => r.type === 'cover_art');
    if (!coverRel?.attributes?.fileName) return '';
    return `https://uploads.mangadex.org/covers/${manga.id}/${coverRel.attributes.fileName}.256.jpg`;
}

// ─── Tools ───────────────────────────────────────────────────────────────────

/**
 * Fetch currently popular manga from MangaDex (ordered by follower count).
 */
export const fetchTrendingManga = {
    name: 'fetch_trending_manga',
    description: 'Get currently popular manga from MangaDex sorted by follower count',
    schema: z.object({
        limit: z.number().int().min(1).max(100).default(20)
    }),
    execute: async ({ limit }: { limit: number }): Promise<MangaDexManga[]> => {
        return getCached('mangadex:trending', 3600, async () => {
            const resp = await axios.get(`${MANGADEX_BASE}/manga`, {
                params: {
                    limit,
                    order: { followedCount: 'desc' },
                    includes: ['cover_art', 'author'],
                    contentRating: ['safe', 'suggestive'],
                    availableTranslatedLanguage: ['en']
                }
            });

            return resp.data.data.map((manga: any) => ({
                id: manga.id,
                title: manga.attributes.title?.en ?? Object.values(manga.attributes.title)[0] ?? 'Unknown',
                description: manga.attributes.description?.en ?? '',
                coverUrl: getCoverUrl(manga),
                tags: manga.attributes.tags?.map((t: any) => t.attributes.name.en).filter(Boolean) ?? [],
                status: manga.attributes.status,
                followCount: manga.attributes.followedCount ?? 0
            }));
        });
    }
};

/**
 * Fetch the latest English chapter for a given manga.
 */
export const fetchLatestChapter = {
    name: 'fetch_latest_chapter',
    description: 'Get the latest translated chapter of a manga',
    schema: z.object({
        mangaId: z.string().describe('MangaDex manga UUID')
    }),
    execute: async ({ mangaId }: { mangaId: string }): Promise<MangaDexChapter | null> => {
        const cacheKey = `mangadex:latest-chapter:${mangaId}`;
        return getCached(cacheKey, 1800, async () => {
            const resp = await axios.get(`${MANGADEX_BASE}/manga/${mangaId}/feed`, {
                params: {
                    limit: 1,
                    order: { chapter: 'desc' },
                    translatedLanguage: ['en'],
                    contentRating: ['safe', 'suggestive']
                }
            });

            const ch = resp.data.data?.[0];
            if (!ch) return null;

            return {
                id: ch.id,
                chapterNumber: ch.attributes.chapter ?? '?',
                title: ch.attributes.title ?? '',
                publishedAt: ch.attributes.publishAt
            };
        });
    }
};

/**
 * Fetch page image URLs for a specific chapter via the MangaDex@Home API.
 */
export const fetchChapterPages = {
    name: 'fetch_chapter_pages',
    description: 'Get all page image URLs for a chapter',
    schema: z.object({
        chapterId: z.string().describe('MangaDex chapter UUID')
    }),
    execute: async ({ chapterId }: { chapterId: string }): Promise<ChapterPages> => {
        const cacheKey = `mangadex:pages:${chapterId}`;
        return getCached(cacheKey, 3600, async () => {
            const resp = await axios.get(`${MANGADEX_BASE}/at-home/server/${chapterId}`);
            const { baseUrl, chapter } = resp.data;

            return {
                baseUrl,
                pages: chapter.data.map((img: string) => `${baseUrl}/data/${chapter.hash}/${img}`)
            };
        });
    }
};

/**
 * Save scraped chapter panels to the database.
 */
export const saveMangaChapter = {
    name: 'save_manga_chapter',
    description: 'Persist a chapter and its panel URLs to the database',
    schema: z.object({
        mangaId: z.number().int(),
        chapterNumber: z.string(),
        chapterTitle: z.string().optional(),
        mangadexChapterId: z.string().optional(),
        panelUrls: z.array(z.string())
    }),
    execute: async (params: {
        mangaId: number;
        chapterNumber: string;
        chapterTitle?: string;
        mangadexChapterId?: string;
        panelUrls: string[];
    }): Promise<number> => {
        const result = await db.query(
            `INSERT INTO manga_chapters
         (manga_id, chapter_number, chapter_title, mangadex_id, panel_urls)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (mangadex_id) DO UPDATE SET panel_urls = EXCLUDED.panel_urls
       RETURNING id`,
            [
                params.mangaId,
                params.chapterNumber,
                params.chapterTitle ?? '',
                params.mangadexChapterId ?? null,
                JSON.stringify(params.panelUrls)
            ]
        );
        logger.info('Chapter saved', { id: result.rows[0].id, panels: params.panelUrls.length });
        return result.rows[0].id;
    }
};

/**
 * Fetch AniList trending manga via GraphQL.
 */
export const fetchAniListTrending = {
    name: 'fetch_anilist_trending',
    description: 'Get trending manga from AniList (no API key required)',
    schema: z.object({
        perPage: z.number().int().min(1).max(50).default(20)
    }),
    execute: async ({ perPage }: { perPage: number }) => {
        return getCached('anilist:trending', 3600, async () => {
            const query = `
        query ($perPage: Int) {
          Page(page: 1, perPage: $perPage) {
            media(type: MANGA, sort: TRENDING_DESC, isAdult: false) {
              id
              title { english romaji }
              description
              genres
              trending
              popularity
              siteUrl
            }
          }
        }`;

            const resp = await axios.post('https://graphql.anilist.co', {
                query,
                variables: { perPage }
            }, { headers: { 'Content-Type': 'application/json' } });

            return resp.data.data.Page.media.map((m: any) => ({
                anilistId: m.id,
                title: m.title.english ?? m.title.romaji,
                genres: m.genres,
                trending: m.trending,
                popularity: m.popularity,
                url: m.siteUrl
            }));
        });
    }
};
