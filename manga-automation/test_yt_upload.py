import os
import sys
from dotenv import load_dotenv

# Add parent dir to path for imports
sys.path.append(os.getcwd())

load_dotenv()

from scripts.utils.logger import setup_logger
logger = setup_logger("test_yt_upload")

def test_upload():
    # Use one of the existing videos
    video_path = os.path.abspath("data/videos/Kage_no_Jitsuryokusha_ni_Naritakute__ch79.1_2026-03-26T07-13-40.mp4")
    
    if not os.path.exists(video_path):
        print(f"❌ Video file not found at {video_path}")
        return

    # Mock the uploader import as in upload_youtube.py
    uploader_path = os.path.abspath(os.path.join(os.getcwd(), '..', 'TiktokAutoUploader'))
    if uploader_path not in sys.path:
        sys.path.append(uploader_path)
        
    try:
        import upload_youtube as yt_lib
        get_yt_client = yt_lib.get_youtube_client
        do_yt_upload = yt_lib.upload_short
        
        logger.info("Authenticating with YouTube API...")
        youtube = get_yt_client()
        
        title = "Test Manga Upload"
        caption = "Testing new YouTube refresh token implementation."
        hashtags = ["manga", "test", "automation"]
        
        logger.info(f"Uploading to YouTube Shorts... Title: {title}")
        url = do_yt_upload(
            youtube=youtube,
            video_path=video_path,
            title=title,
            description=caption,
            tags=hashtags
        )
        
        if url:
            print(f"✅ SUCCESS! YouTube URL: {url}")
        else:
            print("❌ Upload failed (no URL returned)")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_upload()
