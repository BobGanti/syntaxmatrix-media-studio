import dashscope
from dashscope import VideoSynthesis
from http import HTTPStatus
import webbrowser
import os
from alibaba import AlibabaVideos
from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("SINGAPORE_API_KEY")  
WORKSPACE_ID = os.getenv("SINGAPORE_WORKSPACE_ID")
base_http_api_url = f'https://{WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/api/v1'

media = [
    {
        "type": "first_frame", 
        "url": "uploads/images/image1_1782829475605_Generated_Image_August_27_2025_-_2_48PM.jpeg"
    },
    {
        "type": "driving_audio", 
        "url": "voices/sources/bobga_M.wav"
    }
]

prompt = "Create a video of the man speaking. Do not zoom-in or zoom-out"
model="wan2.7-i2v-2026-04-25"

ali = AlibabaVideos(api_key)
video_url = ali.image2video_lipsync(model, prompt, media, base_http_api_url)

if video_url and video_url.startswith(("http://", "https://")):
    webbrowser.open(video_url)
