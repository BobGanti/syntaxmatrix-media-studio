import os
from alibaba import AlibabaImages
import webbrowser
from dotenv import load_dotenv


load_dotenv()

REGION = "singapore"
api_key = os.getenv("SINGAPORE_API_KEY")  
WORKSPACE_ID = os.getenv("SINGAPORE_WORKSPACE_ID")

if REGION == "germany":
    api_key = os.getenv("GERMANY_API_KEY")  
    WORKSPACE_ID = os.getenv("GERMANY_WORKSPACE_ID")

base_http_api_url = f'https://{WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/api/v1'

model = "qwen-image-plus-2026-01-09"


def t2i(messages):
    prompt = [
            {
                "role": "user",
                "content": [
                    {
                        "text": messages,
                    },
                ]
            }
        ]
    
    ali = AlibabaImages(api_key)
    image_url = ali.text2image(model, messages, base_http_api_url)
    
    print(image_url)

    if image_url and image_url.startswith(("http://", "https://")):
        print("\nOpening image in browser...")
        webbrowser.open(image_url)
        return image_url

# elif image_url:
#     print("\nImage returned, but not as http/https URL.")
# else:
#     print("\nNO IMAGE URL FOUND IN RESPONSE.")
