from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()
HTML = ROOT / "frontend" / "clone_voice_debug_print.html"

if not HTML.exists():
    print("ERROR: frontend/clone_voice_debug_print.html not found.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")
backup = HTML.with_name(HTML.name + f".bak.system-list-render-{stamp}")

text = HTML.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

# Remove previous copies of this override.
text = re.sub(
    r"\n\s*<!-- SMX_SYSTEM_VOICE_RENDER_OVERRIDE_START -->[\s\S]*?<!-- SMX_SYSTEM_VOICE_RENDER_OVERRIDE_END -->\s*\n",
    "\n",
    text,
)

override = r'''
<!-- SMX_SYSTEM_VOICE_RENDER_OVERRIDE_START -->
<script>
(function () {
  let smxSystemVoices = [];
  let smxSelectedSystemVoice = null;
  let smxPreviewAudio = null;
  let smxPreviewIndex = null;

  function qs(selector) {
    return document.querySelector(selector);
  }

  function systemPanelIsActive() {
    const tab = qs("#systemTab");
    const panel = qs("#systemPanel");
    return Boolean((tab && tab.classList.contains("active")) || (panel && !panel.hidden));
  }

  function stopPreview() {
    if (smxPreviewAudio) {
      try {
        smxPreviewAudio.pause();
        smxPreviewAudio.currentTime = 0;
      } catch (error) {
        console.warn("[SyntaxMatrix Clone Voice] preview stop failed:", error);
      }
    }

    smxPreviewAudio = null;
    smxPreviewIndex = null;
    updatePreviewButtons();
  }

  function updatePreviewButtons() {
    document.querySelectorAll("[data-smx-system-play]").forEach(button => {
      const index = Number(button.dataset.smxSystemPlay);

      if (smxPreviewIndex === index && smxPreviewAudio && !smxPreviewAudio.paused) {
        button.innerHTML = "■";
        button.setAttribute("title", "Stop preview");
        button.setAttribute("aria-label", "Stop preview");
      } else {
        button.innerHTML = "▶";
        button.setAttribute("title", "Play preview");
        button.setAttribute("aria-label", "Play preview");
      }
    });
  }

  function setListOpen(open) {
    const list = qs("#systemVoiceList");
    const button = qs("#refreshSystemVoices");

    if (!list || !button) return;

    list.hidden = !open;
    button.textContent = open ? "Close system voices" : "Show system voices";

    if (!open) {
      stopPreview();
    }
  }

  function renderSystemVoices() {
    const list = qs("#systemVoiceList");

    if (!list) return;

    if (!smxSystemVoices.length) {
      list.innerHTML = `
        <p class="status">
          No system voices found. Add .txt voice parameter files to:
          <br>workspaces/system/voice_params/
        </p>
      `;
      return;
    }

    list.innerHTML = smxSystemVoices.map((voice, index) => {
      const selected = smxSelectedSystemVoice && smxSelectedSystemVoice.voiceId === voice.voiceId;
      const name = voice.displayName || voice.voiceId;

      return `
        <div class="system-row ${selected ? "selected" : ""}">
          <div class="system-name">${name}</div>
          <div class="system-actions">
            ${voice.previewUrl ? `<button class="secondary icon-button" type="button" data-smx-system-play="${index}" title="Play preview" aria-label="Play preview">▶</button>` : ""}
            <button type="button" data-smx-system-use="${index}">
              ${selected ? "Selected" : "Use"}
            </button>
          </div>
        </div>
      `;
    }).join("");

    updatePreviewButtons();
  }

  async function loadSystemVoicesOverride() {
    const list = qs("#systemVoiceList");
    const button = qs("#refreshSystemVoices");

    if (!list) return;

    stopPreview();

    list.hidden = false;
    list.innerHTML = "<p class='status'>Loading system voices...</p>";

    if (button) {
      button.textContent = "Close system voices";
    }

    try {
      const response = await fetch("/api/clone-voice/system-voices?ts=" + Date.now(), {
        cache: "no-store"
      });

      const data = await response.json();

      console.log("[SyntaxMatrix Clone Voice] system voices response:", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load system voices");
      }

      smxSystemVoices = Array.isArray(data.voices) ? data.voices : [];

      if (
        smxSelectedSystemVoice &&
        !smxSystemVoices.some(voice => voice.voiceId === smxSelectedSystemVoice.voiceId)
      ) {
        smxSelectedSystemVoice = null;
      }

      renderSystemVoices();
    } catch (error) {
      console.error("[SyntaxMatrix Clone Voice] system voices render failed:", error);
      list.innerHTML = `<p class="status">${error.message || String(error)}</p>`;
    }
  }

  async function playSystemPreview(index, button) {
    const voice = smxSystemVoices[index];

    if (!voice || !voice.previewUrl) return;

    if (smxPreviewIndex === index && smxPreviewAudio && !smxPreviewAudio.paused) {
      stopPreview();
      return;
    }

    stopPreview();

    smxPreviewIndex = index;
    smxPreviewAudio = new Audio(voice.previewUrl);

    button.innerHTML = "■";
    button.setAttribute("title", "Stop preview");
    button.setAttribute("aria-label", "Stop preview");

    smxPreviewAudio.addEventListener("ended", stopPreview);
    smxPreviewAudio.addEventListener("error", stopPreview);

    try {
      await smxPreviewAudio.play();
    } catch (error) {
      console.error("[SyntaxMatrix Clone Voice] preview play failed:", error);
      stopPreview();
    }
  }

  async function submitSystemVoice(event) {
    if (!systemPanelIsActive()) return false;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const promptInput = qs("#promptInput");
    const submitBtn = qs("#submitBtn");
    const resultTitle = qs("#resultTitle");
    const audioResult = qs("#audioResult");
    const resultBox = qs("#resultBox");

    const prompt = String(promptInput && promptInput.value || "").trim();

    if (!prompt) {
      alert("Paste narration text first.");
      return true;
    }

    if (!smxSelectedSystemVoice) {
      alert("Choose a system voice first.");
      return true;
    }

    const formData = new FormData();
    formData.append("prompt", prompt);
    formData.append("voiceId", smxSelectedSystemVoice.voiceId);
    formData.append("workspaceId", "mock_user_001");

    console.group("[SyntaxMatrix Clone Voice] SYSTEM VOICE SUBMIT");
    console.log("endpoint:", "/api/clone-voice/generate-system");
    console.log("voiceId:", smxSelectedSystemVoice.voiceId);
    console.log("promptLength:", prompt.length);
    console.groupEnd();

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Generating...";
    }

    if (resultTitle) resultTitle.textContent = "Generating narration";
    if (audioResult) audioResult.innerHTML = "";
    if (resultBox) resultBox.textContent = "Working... Check Flask terminal for logs.";

    try {
      const response = await fetch("/api/clone-voice/generate-system", {
        method: "POST",
        body: formData
      });

      const text = await response.text();
      let data;

      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }

      console.log("[SyntaxMatrix Clone Voice] system voice backend response:", data);

      if (resultBox) {
        resultBox.textContent = JSON.stringify(data, null, 2);
      }

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "HTTP " + response.status);
      }

      if (resultTitle) resultTitle.textContent = "Narration ready";

      const url = data.assetUrl || data.audioUrl;

      if (url && audioResult) {
        audioResult.innerHTML = `
          <audio src="${url}" controls></audio>
          <div class="actions">
            <a href="${url}" download>Download</a>
          </div>
        `;
      }
    } catch (error) {
      console.error("[SyntaxMatrix Clone Voice] system voice request failed:", error);

      if (resultTitle) resultTitle.textContent = "Narration failed";
      if (resultBox) resultBox.textContent = error.message || String(error);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Generate narration";
      }
    }

    return true;
  }

  document.addEventListener("click", async function (event) {
    const refresh = event.target.closest && event.target.closest("#refreshSystemVoices");

    if (refresh) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      const list = qs("#systemVoiceList");

      if (list && !list.hidden && smxSystemVoices.length) {
        setListOpen(false);
      } else {
        await loadSystemVoicesOverride();
      }

      return;
    }

    const systemTab = event.target.closest && event.target.closest("#systemTab");

    if (systemTab) {
      setTimeout(loadSystemVoicesOverride, 50);
      return;
    }

    const play = event.target.closest && event.target.closest("[data-smx-system-play]");

    if (play) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      await playSystemPreview(Number(play.dataset.smxSystemPlay), play);
      return;
    }

    const use = event.target.closest && event.target.closest("[data-smx-system-use]");

    if (use) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      smxSelectedSystemVoice = smxSystemVoices[Number(use.dataset.smxSystemUse)] || null;

      try {
        selectedSystemVoice = smxSelectedSystemVoice;
      } catch {}

      console.log("[SyntaxMatrix Clone Voice] selected system voice:", smxSelectedSystemVoice);

      renderSystemVoices();
      return;
    }
  }, true);

  document.addEventListener("submit", async function (event) {
    const form = event.target.closest && event.target.closest("#cloneVoiceForm");

    if (!form) return;

    await submitSystemVoice(event);
  }, true);

  window.__smxLoadSystemVoices = loadSystemVoicesOverride;
  window.__smxStopSystemPreview = stopPreview;

  setTimeout(function () {
    if (systemPanelIsActive()) {
      loadSystemVoicesOverride();
    }
  }, 200);

  console.log("[SyntaxMatrix Clone Voice] system voice render override active");
})();
</script>
<!-- SMX_SYSTEM_VOICE_RENDER_OVERRIDE_END -->
'''

if re.search(r"</body>", text, flags=re.I):
    text = re.sub(r"</body>", override + "\n</body>", text, count=1, flags=re.I)
else:
    text = text.rstrip() + "\n" + override + "\n"

HTML.write_text(text, encoding="utf-8")

print()
print("System voice frontend override installed.")
print()
print("It fixes:")
print("  system voices stuck on Loading")
print("  close/open list toggle")
print("  preview play/stop")
print("  system voice generation submit")
print()
print("Restart Flask:")
print("  python app.py")
