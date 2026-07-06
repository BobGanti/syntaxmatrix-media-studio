from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()
FRONTEND = ROOT / "frontend"

VOICE_HTML = FRONTEND / "voice_clone_client.html"
INDEX_HTML = FRONTEND / "index.html"
UPLOAD_FIX_JS = FRONTEND / "voice_upload_submit_fix.js"

if not FRONTEND.exists():
    print("ERROR: frontend folder not found. Run this from the project root.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [VOICE_HTML, INDEX_HTML, UPLOAD_FIX_JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.upload-submit-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

UPLOAD_FIX_JS.write_text(r'''(function () {
  const PATCH_NAME = 'voice-upload-submit-fix-only';

  function log(...args) {
    console.log('[SyntaxMatrix Voice Upload Fix]', ...args);
  }

  function toast(title, message) {
    if (typeof window.toast === 'function') {
      window.toast(title, message);
      return;
    }

    const existing = document.querySelector('#toastRegion');
    if (existing) {
      const note = document.createElement('div');
      note.className = 'toast';
      note.innerHTML = `<strong>${title}</strong><span>${message || ''}</span>`;
      existing.appendChild(note);
      window.setTimeout(() => note.remove(), 4500);
      return;
    }

    alert(`${title}\n${message || ''}`);
  }

  function activeMode() {
    const active = document.querySelector('[data-source-mode].active');
    return active?.dataset?.sourceMode || 'upload';
  }

  function getPrompt() {
    return String(
      document.querySelector('#voicePrompt')?.value ||
      document.querySelector('textarea[name="prompt"]')?.value ||
      ''
    ).trim();
  }

  function getAudioInput() {
    return (
      document.querySelector('#voiceAudio') ||
      document.querySelector('input[type="file"][name="audio"]') ||
      document.querySelector('input[type="file"]')
    );
  }

  function setBusy(isBusy) {
    const button =
      document.querySelector('#voiceSubmit') ||
      [...document.querySelectorAll('button')].find(btn =>
        /generate narration/i.test(btn.textContent || '')
      );

    if (!button) return;

    button.disabled = isBusy;
    button.textContent = isBusy ? 'Generating narration…' : 'Generate narration';
  }

  function renderResult(data) {
    const title = document.querySelector('#voiceResultTitle');
    const status = document.querySelector('#voiceResultStatus');
    const preview = document.querySelector('#voiceResultPreview');
    const meta = document.querySelector('#voiceResultMeta');

    const assetUrl = data.assetUrl || data.audioUrl || data.cloneUrl || data.outputUrl;

    if (title) title.textContent = assetUrl ? 'Narration ready' : 'Narration completed';
    if (status) status.textContent = assetUrl ? 'The generated audio is ready.' : 'The controller returned a response but no audio URL was found.';

    if (preview) {
      if (assetUrl) {
        preview.innerHTML = `
          <audio src="${assetUrl}" controls></audio>
          <div class="asset-lite-actions">
            <a class="asset-lite-button primary" href="${assetUrl}" download>Download</a>
            <button class="asset-lite-button" type="button" id="copyVoiceUrlAfterUpload">Copy URL</button>
          </div>
        `;

        document.querySelector('#copyVoiceUrlAfterUpload')?.addEventListener('click', async () => {
          try {
            await navigator.clipboard.writeText(new URL(assetUrl, window.location.href).href);
            toast('URL copied', 'The audio URL is now on your clipboard.');
          } catch {
            window.prompt('Copy audio URL:', assetUrl);
          }
        });
      } else {
        preview.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
      }
    }

    if (meta) {
      meta.innerHTML = `
        <div><dt>Source</dt><dd>upload</dd></div>
        <div><dt>Controller</dt><dd>/api/media/voice-clone</dd></div>
      `;
    }
  }

  function printFileDebug(file, prompt) {
    console.group('[SyntaxMatrix Voice] UPLOAD AUDIO SUBMIT DEBUG');
    console.log('sourceMode:', activeMode());
    console.log('promptLength:', prompt.length);
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('file field name sent to Flask:', 'audio');
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.log('MODE sent:', 'NOT SENT. Upload flow should be None server-side.');
    console.groupEnd();
  }

  async function submitUploadAudio(event) {
    if (activeMode() !== 'upload') return false;

    const prompt = getPrompt();
    const input = getAudioInput();
    const file = input?.files?.[0] || null;

    printFileDebug(file, prompt);

    if (!prompt) {
      toast('Narration text required', 'Paste the narration script before generating.');
      return true;
    }

    if (!file) {
      toast('Audio file required', 'Choose an audio file before clicking Generate narration.');
      return true;
    }

    const formData = new FormData();

    formData.append('prompt', prompt);

    // IMPORTANT:
    // Do not send MODE for user upload flow.
    // Your controller should treat missing MODE as None.
    formData.append('sourceMode', 'upload');

    // IMPORTANT:
    // The audio field name is exactly "audio".
    // Flask should receive request.files["audio"] or request.files.get("audio").
    formData.append('audio', file, file.name);

    // Safe local label only. The controller must not pass this directly as provider preferred_name
    // unless it sanitizes it according to the provider contract.
    formData.append('voiceName', `smxvoice_${Date.now()}`);

    try {
      setBusy(true);

      log('POST /api/media/voice-clone with multipart/form-data');
      log('audio file:', {
        filename: file.name,
        type: file.type,
        size: file.size
      });

      const response = await fetch('/api/media/voice-clone', {
        method: 'POST',
        body: formData
      });

      const text = await response.text();
      let data;

      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { message: text };
      }

      log('Controller response:', data);

      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}: ${text}`);
      }

      renderResult(data);
      toast('Narration complete', 'The upload audio request reached the controller.');
    } catch (error) {
      console.error('[SyntaxMatrix Voice Upload Fix] failed:', error);

      const title = document.querySelector('#voiceResultTitle');
      const status = document.querySelector('#voiceResultStatus');

      if (title) title.textContent = 'Narration failed';
      if (status) status.textContent = error.message || 'Request failed.';

      toast('Narration failed', error.message || 'Request failed.');
    } finally {
      setBusy(false);
    }

    return true;
  }

  function intercept(event) {
    const submitButton = event.target.closest?.('#voiceSubmit, button[type="submit"]');
    const isSubmitEvent = event.type === 'submit' && event.target?.id === 'voiceCloneForm';

    if (!submitButton && !isSubmitEvent) return;

    if (activeMode() !== 'upload') return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    submitUploadAudio(event);
  }

  document.addEventListener('click', intercept, true);
  document.addEventListener('submit', intercept, true);

  document.addEventListener('change', event => {
    const input = event.target;
    if (!input || input.type !== 'file') return;

    const file = input.files?.[0];

    console.group('[SyntaxMatrix Voice] FILE CHOSEN DEBUG');
    console.log('input id:', input.id);
    console.log('input name:', input.name);
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.groupEnd();
  }, true);

  window.__debugVoiceUploadFile = function () {
    const input = getAudioInput();
    const file = input?.files?.[0] || null;
    const prompt = getPrompt();

    printFileDebug(file, prompt);

    return {
      sourceMode: activeMode(),
      promptLength: prompt.length,
      fileExists: Boolean(file),
      filename: file?.name || null,
      type: file?.type || null,
      size: file?.size || null
    };
  };

  console.log(`[${PATCH_NAME}] active. Upload audio Generate button is now intercepted.`);
})();
''', encoding="utf-8")


def inject_script(path: Path) -> None:
    if not path.exists():
        return

    html = path.read_text(encoding="utf-8")

    html = re.sub(
        r'\n?\s*<script[^>]+src=["\']/?voice_upload_submit_fix\.js(?:\?[^"\']*)?["\'][^>]*></script>\s*',
        '\n',
        html,
        flags=re.I,
    )

    script = f'<script src="/voice_upload_submit_fix.js?v={stamp}" defer></script>'

    if re.search(r'</body>', html, flags=re.I):
        html = re.sub(r'</body>', script + '\n</body>', html, count=1, flags=re.I)
    else:
        html = html.rstrip() + '\n' + script + '\n'

    path.write_text(html, encoding="utf-8")
    print("Injected:", path)


inject_script(VOICE_HTML)
inject_script(INDEX_HTML)

print()
print("Upload audio submit-only patch complete.")
print("Changed only frontend files:")
print("  frontend/voice_upload_submit_fix.js")
print("  frontend/voice_clone_client.html, if present")
print("  frontend/index.html, if present")
print()
print("Restart Flask with: python app.py")
print("Open: http://127.0.0.1:5055/tasks/voice-clone?v=upload-submit")
print()
print("In browser console, you can run:")
print("  __debugVoiceUploadFile()")