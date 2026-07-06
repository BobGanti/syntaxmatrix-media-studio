import os
import webbrowser
from dotenv import load_dotenv
from alibaba import AlibabaVideos

load_dotenv()

REGION = "singapore"
api_key = os.getenv("SINGAPORE_API_KEY")  
WORKSPACE_ID = os.getenv("SINGAPORE_WORKSPACE_ID")

if REGION == "germany":
    api_key = os.getenv("GERMANY_API_KEY")  
    WORKSPACE_ID = os.getenv("GERMANY_WORKSPACE_ID")

base_http_api_url = f'https://{WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/api/v1'

model = "wan2.7-i2v-2026-04-25"

media = [
    {
        "type": "first_frame",
        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250925/wpimhv/rap.png"
    },
    {
        "type": "driving_audio",
        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250925/ozwpvi/rap.mp3"
    }
]

prompt = """
An urban fantasy art scene featuring a dynamic graffiti character. A boy made of spray paint comes to life on a concrete wall. He sings an English rap song at high speed while striking a classic, energetic rapper pose. The scene is set under an urban railway bridge at night, lit by a single street lamp. This creates a cinematic atmosphere with high energy and amazing detail. The video's audio consists entirely of the rap, with no other dialogue or noise.
"""

ali = AlibabaVideos(api_key)
video_url = ali.image2video_lipsync(model, prompt, media, base_http_api_url)

if video_url and video_url.startswith(("http://", "https://")):
    webbrowser.open(video_url)