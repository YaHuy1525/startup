import os
import sys
import subprocess
import logging
from scripts.utils.database import execute_returning, execute_one

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def upload_arbitrage(asset_id: int):
    """
    Uploads a YouTube asset to TikTok using TiktokAutoUploader.
    """
    logger.info(f"Starting upload for asset {asset_id}")

    asset = execute_one(
        """
        SELECT id, youtube_url, video_title, local_path
        FROM youtube_assets
        WHERE id = %s
        """,
        (asset_id,)
    )

    if not asset:
        logger.error(f"Asset {asset_id} not found.")
        return False

    tiktok_account = execute_one(
        "SELECT id, username FROM tiktok_accounts WHERE account_status = 'active' ORDER BY RANDOM() LIMIT 1",
        ()
    )

    if not tiktok_account:
         logger.error("No active TikTok accounts found.")
         return False

    account_username = tiktok_account['username']
    account_id = tiktok_account['id']

    # Update status to processing
    execute_returning(
        "UPDATE youtube_assets SET status = 'processing' WHERE id = %s RETURNING id",
        (asset_id,)
    )

    uploader_dir = os.environ.get('TIKTOK_UPLOADER_DIR', '/TiktokAutoUploader')
    cli_path = os.path.join(uploader_dir, 'cli.py')

    # We use the local path if it was downloaded via Apify, or fallback to the YouTube URL feature
    local_path = asset.get('local_path')
    youtube_url = asset.get('youtube_url')
    caption = f"{asset.get('video_title')} #fyp #manga #anime"

    command = [
        "python3", cli_path, "upload",
        "--user", account_username,
        "-t", caption
    ]

    if local_path and os.path.exists(local_path):
        command.extend(["-v", local_path])
    elif youtube_url:
        command.extend(["-yt", youtube_url])
    else:
        logger.error(f"Asset {asset_id} has neither a valid local_path nor youtube_url.")
        execute_returning(
             "UPDATE youtube_assets SET status = 'failed' WHERE id = %s RETURNING id",
             (asset_id,)
        )
        return False

    logger.info(f"Executing command: {' '.join(command)}")

    try:
        # Run TiktokAutoUploader
        result = subprocess.run(command, cwd=uploader_dir, capture_output=True, text=True, check=True)
        logger.info(f"Upload output: {result.stdout}")

        # Determine success (a basic check, might need to be refined based on actual CLI output)
        if "successfully" in result.stdout.lower() or "uploaded" in result.stdout.lower():
            logger.info("Upload appears successful.")

            execute_returning(
                "UPDATE youtube_assets SET status = 'uploaded' WHERE id = %s RETURNING id",
                (asset_id,)
            )

            execute_returning(
                """
                INSERT INTO arbitrage_uploads (asset_id, tiktok_account_id, success)
                VALUES (%s, %s, TRUE) RETURNING id
                """,
                (asset_id, account_id)
            )
            return True
        else:
             raise subprocess.CalledProcessError(1, command, output=result.stdout, stderr=result.stderr)

    except subprocess.CalledProcessError as e:
        logger.error(f"Upload failed: {e.stderr or e.output}")
        execute_returning(
            "UPDATE youtube_assets SET status = 'downloaded' WHERE id = %s RETURNING id",
            (asset_id,)
        )
        execute_returning(
            """
            INSERT INTO arbitrage_uploads (asset_id, tiktok_account_id, success, error_log)
            VALUES (%s, %s, FALSE, %s) RETURNING id
            """,
            (asset_id, account_id, str(e.stderr or e.output))
        )
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Upload YouTube asset to TikTok")
    parser.add_argument("--asset-id", type=int, required=True, help="Database ID of the youtube_asset")
    args = parser.parse_args()

    upload_arbitrage(args.asset_id)