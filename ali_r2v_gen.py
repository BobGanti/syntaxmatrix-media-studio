import json, os
import urllib.request
import urllib.error
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




model = "wan2.7-r2v"

prompt='Video 1 holds Image 3, plays a soothing country folk song on the chair from Image 4, and says, "The sunshine is so nice today." Image 1, holding Image 2, walks past Video 1, places Image 2 on the table next to it, and says, "That sounds lovely. Can you sing it again?"',
media=[
    {
        "type": "reference_image",
        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260408/sjuytr/wan-r2v-object-girl.jpg",
        "reference_voice": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260408/gbqewz/wan-r2v-girl-voice.mp3"
    },
    {
        "type": "reference_video",
        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260129/qigswt/wan-r2v-role2.mp4",
        "reference_voice": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260408/isllrq/wan-r2v-boy-voice.mp3"
    },
    {
        "type": "reference_image",
        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260129/rtjeqf/wan-r2v-object3.png"
    },
    {
        "type": "reference_image",
        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260129/qpzxps/wan-r2v-object4.png"
    },
    {
        "type": "reference_image",
        "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260129/wfjikw/wan-r2v-backgroud5.png"
    }
],
