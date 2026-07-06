import os
import webbrowser
from alibaba import AlibabaImages
from dotenv import load_dotenv


load_dotenv()

REGION = "singapore"
api_key = os.getenv("SINGAPORE_API_KEY")  
WORKSPACE_ID = os.getenv("SINGAPORE_WORKSPACE_ID")

if REGION == "germany":
    api_key = os.getenv("GERMANY_API_KEY")  
    WORKSPACE_ID = os.getenv("GERMANY_WORKSPACE_ID")

base_http_api_url = f'https://{WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/api/v1'


model="qwen-image-edit-plus-2025-12-15"

messages = [
    {
        "role": "user",
        "content": [
            {"image": "uploads/images/meandher.jpeg"},
            {"image": "uploads/images/input2.png"},
            {"image": "uploads/images/white_shoes.png"},
            {"text": """Make the man and the woman from Image 1 wear the white turxido from Image 2 (female fitting for the woman) and also make them both wear the white shoes from Image 3 (female fitting for the woman)."""}
        ]
    }
]

if sum(1 for item in messages[0]["content"] if "image" in item) <= 3:
    ali = AlibabaImages(api_key)
    rti_list = ali.edit2image(model, messages, base_http_api_url)

    # Loop through and print each image URL
    for item in rti_list:
        if "image" in item:
            # print(item["image"])
            webbrowser.open(item["image"])
else:
    print("Too many images: maximum allowed is 3")



