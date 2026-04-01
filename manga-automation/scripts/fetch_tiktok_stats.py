#!/usr/bin/env python3
"""
Fetch post-upload engagement metrics (views, likes, comments) for published TikTok videos.
In a production scenario, this script uses Playwright or an unofficial API to scrape the video URL.
For now, this serves as the foundational script to populate the `video_analytics` table.
"""

import sys
import random
from dotenv import load_dotenv

load_dotenv()
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("fetch_tiktok_stats")

def fetch_stats_for_video(platform_url: str) -> dict:
    """
    Mock implementation of scraping TikTok video stats.
    Replace with actual Playwright/BS4 scraping logic.
    """
    logger.info(f"Scraping stats for {platform_url}")
    # Simulating a network request delay and random stats
    return {
        "views": random.randint(1000, 50000),
        "likes": random.randint(100, 5000),
        "comments": random.randint(10, 500),
        "shares": random.randint(5, 200)
    }

def main():
    logger.info("Starting TikTok stats fetcher...")
    
    # Get all successfully published videos that need analytics updates (last 30 days)
    published_videos = db.execute_all(
        """
        SELECT pv.id, pv.platform_url
        FROM published_videos pv
        WHERE pv.platform = 'tiktok'
          AND pv.platform_url IS NOT NULL
          AND pv.published_at >= NOW() - INTERVAL '30 days'
        """
    )
    
    if not published_videos:
        logger.info("No published videos found to track.")
        return

    logger.info(f"Found {len(published_videos)} videos to track.")
    
    for video in published_videos:
        pv_id = video["id"]
        url = video["platform_url"]
        
        stats = fetch_stats_for_video(url)
        
        # Insert analytics snapshot
        db.execute(
            """
            INSERT INTO video_analytics 
                (published_video_id, views, likes, comments, shares, scraped_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (pv_id, stats["views"], stats["likes"], stats["comments"], stats["shares"])
        )
        logger.info(f"Updated stats for PV ID {pv_id}")

    logger.info("Finished tracking Analytics.")

if __name__ == "__main__":
    main()
