import json, time, sys, os, traceback
sys.path.insert(0, '/app')
sys.path.insert(0, '/TiktokUploader')
os.chdir('/TiktokUploader')
os.environ['TIKTOK_UPLOADER_V2_DIR'] = '/TiktokUploader'

# Start Xvfb for non-headless
import subprocess
xvfb = subprocess.Popen(
    ['Xvfb', ':99', '-screen', '0', '1280x900x24'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(2)
os.environ['DISPLAY'] = ':99'

from tiktokautouploader import upload_tiktok

try:
    result = upload_tiktok(
        video='/app/data/videos/test_anime.mp4',
        description='This anime moment is INSANE',
        accountname='nuggerchicken433',
        hashtags=['anime', 'fyp', 'manga'],
        headless=False,
        stealth=True,
        suppressprint=False,
    )
    print('RESULT:', result)
except SystemExit as e:
    print('SYS EXIT:', e)
except Exception as e:
    traceback.print_exc()
    print('ERROR:', e)
finally:
    xvfb.terminate()
