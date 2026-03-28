import puppeteer from 'puppeteer';
import axios from 'axios';
import * as fs from 'fs/promises';
import * as path from 'path';
import { z } from 'zod';
import { logger } from './database';

const PANELS_DIR = process.env.PANELS_DIR ?? '/data/panels';

// ─── Puppeteer scraper (for sites without APIs) ───────────────────────────────

export const scrapeChapterPanels = {
    name: 'scrape_chapter_panels',
    description: 'Scrape manga panel images from a URL using Puppeteer',
    schema: z.object({
        url: z.string().url(),
        siteName: z.enum(['mangakakalot', 'webtoons', 'generic']).default('generic')
    }),
    execute: async ({ url, siteName }: { url: string; siteName: string }): Promise<string[]> => {
        const browser = await puppeteer.launch({
            headless: true,
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        });

        try {
            const page = await browser.newPage();

            // Block heavy resources for speed
            await page.setRequestInterception(true);
            page.on('request', (req) => {
                if (['stylesheet', 'font', 'media'].includes(req.resourceType())) {
                    req.abort();
                } else {
                    req.continue();
                }
            });

            await page.goto(url, { waitUntil: 'networkidle0', timeout: 30000 });

            // Selector map per site
            const selectorMap: Record<string, string> = {
                mangakakalot: '.container-chapter-reader img',
                webtoons: '._3HZ6D img',
                generic: '.chapter-img, .manga-panel, [class*="panel"] img, article img'
            };

            const selector = selectorMap[siteName] ?? selectorMap.generic;
            await page.waitForSelector(selector, { timeout: 10000 }).catch(() => null);

            const panels = await page.evaluate((sel: string) => {
                const imgs = Array.from(document.querySelectorAll<HTMLImageElement>(sel));
                return imgs.map(img => img.src || img.dataset.src || '').filter(Boolean);
            }, selector);

            logger.info(`Scraped ${panels.length} panels from ${url}`);
            return panels;
        } finally {
            await browser.close();
        }
    }
};

// ─── Image downloader ─────────────────────────────────────────────────────────

export const downloadPanels = {
    name: 'download_panels',
    description: 'Download panel images locally for processing',
    schema: z.object({
        panelUrls: z.array(z.string()),
        mangaTitle: z.string(),
        chapterNumber: z.string()
    }),
    execute: async (params: {
        panelUrls: string[];
        mangaTitle: string;
        chapterNumber: string;
    }): Promise<string[]> => {
        const safeTitle = params.mangaTitle.replace(/[^a-z0-9]/gi, '_').toLowerCase();
        const safeChapter = params.chapterNumber.replace(/[^a-z0-9]/gi, '_');
        const chapterDir = path.join(PANELS_DIR, safeTitle, `ch_${safeChapter}`);

        await fs.mkdir(chapterDir, { recursive: true });

        const localPaths: string[] = [];

        for (let i = 0; i < params.panelUrls.length; i++) {
            const url = params.panelUrls[i];
            const ext = url.split('.').pop()?.split('?')[0] ?? 'jpg';
            const filename = `panel_${String(i + 1).padStart(3, '0')}.${ext}`;
            const localPath = path.join(chapterDir, filename);

            try {
                const resp = await axios.get(url, {
                    responseType: 'arraybuffer',
                    timeout: 15000,
                    headers: {
                        'User-Agent': 'Mozilla/5.0',
                        Referer: new URL(url).origin
                    }
                });
                await fs.writeFile(localPath, Buffer.from(resp.data));
                localPaths.push(localPath);
            } catch (err: any) {
                logger.warn(`Failed to download panel ${i + 1}: ${err.message}`);
            }
        }

        logger.info(`Downloaded ${localPaths.length}/${params.panelUrls.length} panels`, { dir: chapterDir });
        return localPaths;
    }
};

// ─── Panel image → base64 (for Claude Vision) ────────────────────────────────

export const panelToBase64 = {
    name: 'panel_to_base64',
    description: 'Convert a panel image (URL or local path) to base64 for AI analysis',
    schema: z.object({
        source: z.string().describe('URL or absolute local file path')
    }),
    execute: async ({ source }: { source: string }): Promise<{ base64: string; mediaType: string }> => {
        let buffer: Buffer;

        if (source.startsWith('http')) {
            const resp = await axios.get(source, {
                responseType: 'arraybuffer',
                timeout: 15000,
                headers: { 'User-Agent': 'Mozilla/5.0' }
            });
            buffer = Buffer.from(resp.data);
        } else {
            buffer = await fs.readFile(source);
        }

        const ext = source.split('.').pop()?.toLowerCase() ?? 'jpg';
        const mediaType = ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg';

        return { base64: buffer.toString('base64'), mediaType };
    }
};
