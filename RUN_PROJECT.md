# Alibaba Media Studio Flask App

## Run

```bash
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Then open:

```text
http://127.0.0.1:5055
```

## Edit → Image upload contract

The frontend sends the files as multipart uploads:

```text
image: Image 1 file
image: Image 2 file
image: Image 3 file
prompt: your instruction
model: qwen-image-edit-plus-2025-12-15
```

The Flask backend reads:

```python
request.files.getlist("image")
```

It saves them under:

```text
uploads/images/
```

Then it builds the Alibaba message like your working local script:

```python
messages = [
    {
        "role": "user",
        "content": [
            {"image": "uploads/images/image1_...jpeg"},
            {"image": "uploads/images/image2_...png"},
            {"image": "uploads/images/image3_...png"},
            {"text": "Make the man and woman from Image 1..."},
        ],
    }
]
```

## Upload test without Alibaba

Add this to `.env`:

```env
ALIBABA_MEDIA_DRY_RUN=1
```

Restart with `python app.py`. Edit → Image will accept uploads and return the request message without calling Alibaba.
