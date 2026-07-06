# SyntaxMatrix Media Studio

Commercial media-generation studio for SyntaxMatrix.

## Launch

From the project root:

```bash
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5055
```

Windows shortcut:

```text
run_flask.bat
```

## Environment

Create `.env` in the project root:

```env
SINGAPORE_API_KEY=your_provider_api_key
SINGAPORE_WORKSPACE_ID=your_workspace_id
```

## Feature architecture

The frontend must not call the provider wrapper directly. The intended commercial structure is:

```text
Frontend view
  -> Feature controller
      -> Provider/service module only when that feature needs it
```

Clone Voice is now the first feature moved into this pattern.

## Clone Voice

Client view:

```text
http://127.0.0.1:5055/tasks/clone-voice
```

Admin view:

```text
http://127.0.0.1:5055/admin/clone-voice
```

Controller:

```text
controllers/voice_clone_controller.py
```

The Clone Voice controller talks to the existing voice feature module. It does not call the generic provider wrapper module.

Generated voice assets are stored under:

```text
voices/clones/
```

Voice source recordings are stored under:

```text
voices/sources/
```

Voice profile parameters are stored under:

```text
voices/params/
```

## Next commercial steps

Do the same controller/view/admin split feature by feature:

```text
controllers/text_to_image_controller.py
controllers/edit_image_controller.py
controllers/text_to_video_controller.py
controllers/image_to_video_controller.py
```

Then add authentication, admin permissions, customer billing and usage metering.


## Voice Narration client workflow

Open:

http://127.0.0.1:5055/tasks/clone-voice

The client page does not show internal voice profile names or model names.

A client can choose one of three source options:

1. Upload a clean voice sample.
2. Record their voice in the browser.
3. Listen to an approved preview voice and choose it for narration.

The client page posts only to the Clone Voice controller:

/api/media/voice-clone
