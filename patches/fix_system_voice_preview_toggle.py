from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()
HTML = ROOT / "frontend" / "clone_voice_debug_print.html"

if not HTML.exists():
    print("ERROR: frontend/clone_voice_debug_print.html not found.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")
backup = HTML.with_name(HTML.name + f".bak.system-preview-toggle-{stamp}")

text = HTML.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

# Remove old copy if patch is rerun.
text = re.sub(
    r"\n\s*<!-- SMX_SYSTEM_PREVIEW_TOGGLE_FIX_START -->[\s\S]*?<!-- SMX_SYSTEM_PREVIEW_TOGGLE_FIX_END -->\s*\n",
    "\n",
    text,
)

fix_script = r'''
<!-- SMX_SYSTEM_PREVIEW_TOGGLE_FIX_START -->
<script>
(function () {
  let currentPreviewAudio = null;
  let currentPreviewButton = null;
  let currentPreviewIndex = null;

  function getList() {
    return document.querySelector("#systemVoiceList");
  }

  function getToggleButton() {
    return document.querySelector("#refreshSystemVoices");
  }

  function stopCurrentPreview() {
    if (currentPreviewAudio) {
      try {
        currentPreviewAudio.pause();
        currentPreviewAudio.currentTime = 0;
      } catch (error) {
        console.warn("[SyntaxMatrix Clone Voice] could not stop preview:", error);
      }
    }

    if (currentPreviewButton) {
      currentPreviewButton.innerHTML = '<span aria-hidden="true">▶</span>';
      currentPreviewButton.setAttribute("aria-label", "Play preview voice");
      currentPreviewButton.setAttribute("title", "Play preview voice");
    }

    currentPreviewAudio = null;
    currentPreviewButton = null;
    currentPreviewIndex = null;

    normalizePlayButtons();
  }

  function normalizePlayButtons() {
    document.querySelectorAll("[data-play-system]").forEach(button => {
      button.classList.add("icon-button");

      const buttonIndex = Number(button.dataset.playSystem);

      if (currentPreviewIndex === buttonIndex && currentPreviewAudio && !currentPreviewAudio.paused) {
        button.innerHTML = '<span aria-hidden="true">■</span>';
        button.setAttribute("aria-label", "Stop preview voice");
        button.setAttribute("title", "Stop preview voice");
      } else {
        button.innerHTML = '<span aria-hidden="true">▶</span>';
        button.setAttribute("aria-label", "Play preview voice");
        button.setAttribute("title", "Play preview voice");
      }
    });
  }

  function setSystemListOpen(open) {
    const list = getList();
    const button = getToggleButton();

    if (!list || !button) return;

    list.hidden = !open;
    button.textContent = open ? "Close system voices" : "Show system voices";

    if (!open) {
      stopCurrentPreview();
    }
  }

  function systemListHasRows() {
    const list = getList();
    return Boolean(list && list.querySelector(".system-row"));
  }

  async function openAndRefreshSystemVoices() {
    const list = getList();

    setSystemListOpen(true);

    if (typeof loadSystemVoices === "function") {
      await loadSystemVoices();
    }

    if (list) {
      list.hidden = false;
    }

    const button = getToggleButton();
    if (button) {
      button.textContent = "Close system voices";
    }

    normalizePlayButtons();
  }

  document.addEventListener("click", async function (event) {
    const playButton = event.target.closest && event.target.closest("[data-play-system]");

    if (playButton) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      const index = Number(playButton.dataset.playSystem);

      if (currentPreviewIndex === index && currentPreviewAudio && !currentPreviewAudio.paused) {
        stopCurrentPreview();
        return;
      }

      let voice = null;

      if (typeof systemVoices !== "undefined" && Array.isArray(systemVoices)) {
        voice = systemVoices[index] || null;
      }

      if (!voice || !voice.previewUrl) {
        console.warn("[SyntaxMatrix Clone Voice] No preview URL for system voice index:", index);
        return;
      }

      stopCurrentPreview();

      currentPreviewAudio = new Audio(voice.previewUrl);
      currentPreviewButton = playButton;
      currentPreviewIndex = index;

      playButton.innerHTML = '<span aria-hidden="true">■</span>';
      playButton.setAttribute("aria-label", "Stop preview voice");
      playButton.setAttribute("title", "Stop preview voice");

      currentPreviewAudio.addEventListener("ended", stopCurrentPreview);
      currentPreviewAudio.addEventListener("error", stopCurrentPreview);

      try {
        await currentPreviewAudio.play();
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] Preview play failed:", error);
        stopCurrentPreview();
      }

      return;
    }

    const toggleButton = event.target.closest && event.target.closest("#refreshSystemVoices");

    if (toggleButton) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      const list = getList();

      if (!list) return;

      const isOpen = !list.hidden;

      if (isOpen && systemListHasRows()) {
        setSystemListOpen(false);
        return;
      }

      await openAndRefreshSystemVoices();
    }
  }, true);

  const observer = new MutationObserver(function () {
    normalizePlayButtons();

    const list = getList();
    const button = getToggleButton();

    if (list && button && !list.hidden && systemListHasRows()) {
      button.textContent = "Close system voices";
    }
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });

  setTimeout(function () {
    normalizePlayButtons();

    const button = getToggleButton();
    const list = getList();

    if (button && list && !list.hidden) {
      button.textContent = "Close system voices";
    }
  }, 250);

  window.__smxStopSystemVoicePreview = stopCurrentPreview;

  console.log("[SyntaxMatrix Clone Voice] system preview toggle fix active");
})();
</script>
<!-- SMX_SYSTEM_PREVIEW_TOGGLE_FIX_END -->
'''

if "</body>" not in text.lower():
    text = text.rstrip() + "\n" + fix_script + "\n"
else:
    text = re.sub(r"</body>", fix_script + "\n</body>", text, count=1, flags=re.I)

HTML.write_text(text, encoding="utf-8")

print()
print("System voice preview toggle fixed.")
print()
print("Behaviour now:")
print("  ▶ starts preview")
print("  ■ stops preview")
print("  Close system voices hides the list")
print("  Show system voices opens the list again")
print()
print("Restart Flask:")
print("  python app.py")
