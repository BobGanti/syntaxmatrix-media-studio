from http import HTTPStatus
from dashscope import VideoSynthesis
import dashscope
import os
import webbrowser

from dotenv import load_dotenv

from alibaba import AlibabaVideos


load_dotenv()

WORKSPACE_ID = os.getenv("SINGAPORE_WORKSPACE_ID")
API_KEY = os.getenv("SINGAPORE_API_KEY")

base_http_api_url = f'https://{WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/api/v1'
dashscope.base_http_api_url = base_http_api_url
api_key = API_KEY
model='wan2.7-t2v'

def text2video_lipsync(prompt_text, audio_url):
    # Call the sync API and return the result.
    print('Please wait...')
    rsp = VideoSynthesis.call(
        api_key=api_key,
        model=model,
        prompt=prompt_text,
        audio_url=audio_url,
        size='1280*720',
        duration=10,
        negative_prompt="",
        prompt_extend=True,
        watermark=False,
        seed=12345
    )
    if rsp.status_code == HTTPStatus.OK:
        # Access the video_url property from the output object
        video_url = rsp.output.video_url
        return video_url
    else:
        return ('Failed. Status code: %s, code: %s, message: %s' %
              (rsp.status_code, rsp.code, rsp.message))

prompt_text = """
Shot from a low angle, in a medium close-up, with warm tones, mixed lighting (the practical light from the desk lamp blends with the overcast light from the window), side lighting, and a central composition. 
In a classic detective office, wooden bookshelves are filled with old case files and ashtrays. A green desk lamp illuminates a case file spread out in the center of the desk. 
A dog, wearing a dark brown trench coat and a light gray fedora, sits in a leather chair, its fur crimson, its tail resting lightly on the edge, its fingers slowly turning yellowed pages. 
Outside, a steady drizzle falls beneath a blue sky, streaking the glass with meandering streaks. 
It slowly raises its head, its ears twitching slightly, its amber eyes gazing directly at the camera, its mouth clearly moving as it speaks in a smooth, cynical voice: 'The case was cold, colder than a fish in winter. But every chicken has its secrets, and I, for one, intended to find them.'
"""

audio_url = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250929/stjqnq/%E7%8B%90%E7%8B%B8.mp3"

ali = AlibabaVideos(api_key=api_key, base_http_api_url=base_http_api_url)
video_url = ali.text2video_lipsync(model='wan2.7-t2v', prompt=prompt_text, audio_url=audio_url)

if video_url and video_url.startswith(("http://", "https://")):
    webbrowser.open(video_url)
else:
    print(video_url)