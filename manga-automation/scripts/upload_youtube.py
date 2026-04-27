import os
import sys
import json
import argparse
from typing import Dict, Any

# Add parent dir to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("upload_youtube")

def get_video(video_id: int) -> Dict[str, Any]:
    """Fetch video metadata and ensure it's ready."""
    video = db.execute_one(
        """
        SELECT v.id, v.file_path, v.caption, v.status,
               v.hashtags
        FROM videos v
        WHERE v.id = %s
        """,
        (video_id,)
    )

    if not video:
        logger.error(f"Video id={video_id} not found")
        sys.exit(1)

    return video


def record_result(video_id: int, result: dict):
    """Save the upload result to database."""
    if result.get("success"):
        logger.info(f"Video {video_id} published successfully to YouTube!")
        db.execute(
            "UPDATE videos SET status = 'published' WHERE id = %s",
            (video_id,),
        )
        # Also log to published_videos
        db.execute(
            """
            INSERT INTO published_videos (video_id, platform, account_name, platform_post_id, platform_url)
            VALUES (%s, 'youtube', 'default', %s, %s)
            """,
            (video_id, result.get("video_id"), result.get("youtube_url"))
        )
    else:
        logger.error(f"Upload failed for video {video_id}: {result.get('error')}")


def main(video_id: int) -> dict:
    logger.info(f"Starting YouTube upload sequence for video_id={video_id}")

    try:
        video = get_video(video_id)
        
        # Verify file exists
        if not os.path.exists(video["file_path"]):
            logger.error(f"File not found: {video['file_path']}")
            return {"error": "file_not_found", "success": False}

        # Build paths
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        uploader_path = os.path.abspath(os.path.join(project_root, '..', 'TiktokAutoUploader'))
        if uploader_path not in sys.path:
            sys.path.append(uploader_path)
            
        try:
            import upload_youtube as yt_lib
            get_yt_client = yt_lib.get_youtube_client
            do_yt_upload = yt_lib.upload_short
        except ImportError as e:
            logger.error(f"Could not import upload_youtube from {uploader_path}: {e}")
            return {"error": str(e), "success": False}
        except AttributeError as e:
            logger.error(f"Module found but missing attributes: {e}. Dir: {dir(yt_lib)}")
            return {"error": str(e), "success": False}

        # Auth and Upload
        logger.info("Authenticating with YouTube API...")
        youtube = get_yt_client()
        
        caption = video.get("caption", "") or "Manga clip"
        title = caption.split('\n')[0][:100] if caption else f"Epic Manga Moment #{video_id}"
        
        hashtags_list = []
        if video.get("hashtags"):
            hashtags_list = video["hashtags"]

        logger.info(f"Uploading to YouTube Shorts... Title: {title}")
        url = do_yt_upload(
            youtube=youtube,
            video_path=video["file_path"],
            title=title,
            description=caption,
            tags=hashtags_list
        )
        
        youtube_vid = url.split('/')[-1] if url else None

        result = {
            "video_id": video_id,
            "success": True,
            "youtube_url": url,
            "youtube_video_id": youtube_vid,
            "error": None
        }

        record_result(video_id, result)
        print(json.dumps(result))
        return result

    except Exception as e:
        logger.exception(f"Unexpected error uploading video {video_id}: {e}")
        result = {"video_id": video_id, "success": False, "error": str(e)}
        record_result(video_id, result)
        print(json.dumps(result))
        return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int, required=True, help="ID of the video to upload")
    args = parser.parse_args()
    main(args.video_id)
