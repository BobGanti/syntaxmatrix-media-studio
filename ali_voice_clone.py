import os
import requests
import base64
import pathlib
import dashscope
from dotenv import load_dotenv
from datetime import datetime


load_dotenv()

# ======= Constants & Configurations =======
# 1. RETRIEVE ENVIRONMENT VARIABLES
ALIBABA_API_KEY = os.getenv("SINGAPORE_API_KEY")
WORKSPACE_ID = os.getenv("SINGAPORE_WORKSPACE_ID")  

DEFAULT_TARGET_MODEL = "qwen3-tts-vc-2026-01-22"   
# qwen3-tts-instruct-flash
# qwen3-tts-instruct-flash-realtime
# cosyvoice-v3.5-plus

DEFAULT_PREFERRED_NAME = "smxVoice"
DEFAULT_AUDIO_MIME_TYPE = "audio/mpeg"

def create_voice(file_path: str,
                 target_model: str = DEFAULT_TARGET_MODEL,
                 preferred_name: str = DEFAULT_PREFERRED_NAME,
                 audio_mime_type: str = DEFAULT_AUDIO_MIME_TYPE) -> str:
    """
    Create a custom voice and return the voice parameter.
    """
    file_path_obj = pathlib.Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    base64_str = base64.b64encode(file_path_obj.read_bytes()).decode()
    data_uri = f"data:{audio_mime_type};base64,{base64_str}"

    # FIXED: Replaced placeholder {WorkspaceId} with your actual workspace ID variable
    url = f"https://{WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/audio/tts/customization"
    
    payload = {
        "model": "qwen-voice-enrollment",
        "input": {
            "action": "create",
            "target_model": target_model,
            "preferred_name": preferred_name,
            "audio": {"data": data_uri}
        }
    }
    headers = {
        "Authorization": f"Bearer {ALIBABA_API_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to create voice: {resp.status_code}, {resp.text}")

    try:
        return resp.json()["output"]["voice"]
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Failed to parse voice response: {e}")


def clone_voice(api_key: str, model: str, voice: str, text: str, stream: bool=False):
    print("Generating speech response...")
    response = dashscope.MultiModalConversation.call(
        api_key=api_key,
        model=model,
        text=text,
        voice=voice,
        stream=stream
    )

    return response


def save_voice_to_disk(voice_data: str, storage_path: str):
    """Saves the cloned voice string to a text file."""
    pathlib.Path(storage_path).write_text(voice_data, encoding="utf-8")
    print(f"Successfully saved cloned voice data to {storage_path}")


def load_voice_from_disk(storage_path: str) -> str:
    """Loads the cloned voice string from the text file."""
    path_obj = pathlib.Path(storage_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"No clone found at Clone it first.")
    return path_obj.read_text(encoding="utf-8").strip()


def read_text_from_file(file_path: str) -> str:
    """Reads text content from a specified file."""
    path_obj = pathlib.Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Text file not found: {file_path}")
    return path_obj.read_text(encoding="utf-8").strip()


def preview(filename:str):
    vname = filename.split("_")[0]
    text = f"{vname}: {read_text_from_file('smxPPprev.txt')}"
    return text


MODE = None  # preview or None

if __name__ == '__main__':
    dashscope.base_http_api_url = f'https://{WORKSPACE_ID}.ap-southeast-1.maas.aliyuncs.com/api/v1'

    ROOT_DIR = "voices"
    os.makedirs("voices", exist_ok=True)
    SOURCES_DIR = "sources"
    os.makedirs(f"{ROOT_DIR}/{SOURCES_DIR}", exist_ok=True)
    PARAMS_DIR = "params"
    os.makedirs(f"{ROOT_DIR}/{PARAMS_DIR}", exist_ok=True)
    PREVIEWS_DIR = "previews"
    os.makedirs(f"{ROOT_DIR}/{PREVIEWS_DIR}", exist_ok=True)
    CLONES_DIR = "clones"
    os.makedirs(f"{ROOT_DIR}/{CLONES_DIR}", exist_ok=True)

    SOURCE_VOICE_FILE_NAME = "smxPP_M.wav"
    SOURCE_VOICE_FILE_PATH = os.path.join(ROOT_DIR, SOURCES_DIR, SOURCE_VOICE_FILE_NAME) 

    CLONED_DATA_FILE_NAME = SOURCE_VOICE_FILE_NAME.replace(".", "_")
    CLONED_DATA_FILE_PATH = os.path.join(ROOT_DIR, PARAMS_DIR, CLONED_DATA_FILE_NAME + ".txt")

    PREVIEW_FILE_PATH = os.path.join(ROOT_DIR, CLONES_DIR, "preview_" + SOURCE_VOICE_FILE_NAME)
    
     # Check if we already have a saved voice on disk
    if pathlib.Path(CLONED_DATA_FILE_PATH).exists():
        print("Loading existing voice from disk...")
        cloned_voice_parameter = load_voice_from_disk(CLONED_DATA_FILE_PATH)
    else:
        print("No existing voice param found. Cloning new voice from audio file...")
        # 1. Clone the voice via API
        cloned_voice_parameter = create_voice(SOURCE_VOICE_FILE_PATH)
        # 2. Save it to disk for next time
        save_voice_to_disk(cloned_voice_parameter, CLONED_DATA_FILE_PATH)


    fname = "txt_sources\yt131.txt"
    ctx = read_text_from_file(fname)
    NARRATION_TEXT = {
        "title": fname.split(".")[0], 
        "content": ctx
    }

    if MODE == preview:
        output_filename = f"{CLONED_DATA_FILE_NAME}_preview.wav"
        output_file_path = os.path.join(ROOT_DIR, PREVIEWS_DIR, output_filename)
        if pathlib.Path(output_file_path).exists():
            print("Preview Exist!")
            quit()
        text = preview(SOURCE_VOICE_FILE_NAME)
    else:
        title = NARRATION_TEXT["title"]
        text = NARRATION_TEXT["content"]
        checksum = datetime.now().strftime("%Y%m%d%H%M%S")
        output_filename = f"{title}_{checksum}.wav"
        output_file_path = os.path.join(ROOT_DIR, CLONES_DIR, output_filename)
    
    print("\n--- API Response ---")
    # print(response)
    
    # ======= FIXED: EXTRACT AND SAVE THE AUDIO OUTPUT =======
    try:
        response = clone_voice(api_key=ALIBABA_API_KEY, model=DEFAULT_TARGET_MODEL, voice=cloned_voice_parameter, text=text)

        output_data = response.get("output", {})
        audio_info = output_data.get("audio", {})
        audio_url = audio_info.get("url")
        
        if audio_url:
            # print(f"Downloading generated audio from: {audio_url}")
            print("Downloading generated audio...")
            audio_data = requests.get(audio_url).content           
            pathlib.Path(output_file_path).write_bytes(audio_data)
            print(f"Success! Saved the voice output to '{output_filename}'.")
        else:
            print("Could not find an audio URL in the response structure.")
            
    except Exception as e:
        print(f"Failed to extract or save audio file: {e}")

