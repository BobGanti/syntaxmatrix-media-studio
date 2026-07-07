from pathlib import Path
from datetime import datetime

ROOT = Path(".").resolve()

HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [HTML, CSS, JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice frontend not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.visible-timer-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

html = HTML.read_text(encoding="utf-8")

if 'id="recordingTimer"' not in html:
    old = '''<p class="status" id="recordingStatus">Start recording, speak clearly, then stop. The recording will be sent as recorded_voice.wav.</p>'''
    new = '''<p class="status" id="recordingStatus">Start recording, speak clearly, then stop. The recording will be sent as recorded_voice.wav.</p>
            <div class="record-timer" id="recordingTimer" aria-live="polite">0.0s / 35s</div>'''

    if old not in html:
        print("ERROR: Could not find recordingStatus paragraph in HTML.")
        raise SystemExit(1)

    html = html.replace(old, new, 1)

html = html.replace(
    '<script src="/clone_voice/client.js?v=duration-step2"></script>',
    '<script src="/clone_voice/client.js?v=visible-timer-1"></script>',
)

html = html.replace(
    '<script src="/clone_voice/client.js?v=stable-naming-1"></script>',
    '<script src="/clone_voice/client.js?v=visible-timer-1"></script>',
)

HTML.write_text(html, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")

if ".record-timer" not in css:
    css += r'''

.record-timer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-width: 150px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid #465662;
  background: #071017;
  color: #9ee8dc;
  font-weight: 900;
  letter-spacing: .04em;
}
'''

CSS.write_text(css, encoding="utf-8")

js = JS.read_text(encoding="utf-8")

if 'const recordingTimer = $("#recordingTimer");' not in js:
    anchor = 'const recordingStatus = $("#recordingStatus");'
    if anchor not in js:
        print("ERROR: Could not find recordingStatus const in JS.")
        raise SystemExit(1)

    js = js.replace(
        anchor,
        anchor + '\n  const recordingTimer = $("#recordingTimer");',
        1,
    )

if "let recordingTicker = null;" not in js:
    anchor = "let recordingStartedAt = 0;"
    if anchor not in js:
        print("ERROR: Could not find recordingStartedAt variable in JS.")
        raise SystemExit(1)

    js = js.replace(
        anchor,
        anchor + "\n  let recordingTicker = null;",
        1,
    )

if "function renderRecordingTimer" not in js:
    anchor = '''  function clearRecordingAutoStopTimer() {
    if (recordingAutoStopTimer) {
      clearTimeout(recordingAutoStopTimer);
      recordingAutoStopTimer = null;
    }
  }'''

    if anchor not in js:
        print("ERROR: Could not find clearRecordingAutoStopTimer function in JS.")
        raise SystemExit(1)

    replacement = r'''  function renderRecordingTimer(elapsedSeconds = 0) {
    if (!recordingTimer) return;

    const safeElapsed = Math.max(0, elapsedSeconds);
    const safeMax = Math.max(1, Number(maxVoiceSourceSeconds || 35));
    const remaining = Math.max(0, safeMax - safeElapsed);

    recordingTimer.textContent = `${safeElapsed.toFixed(1)}s / ${safeMax}s`;
    recordingTimer.setAttribute("title", `${remaining.toFixed(1)} seconds remaining`);
  }

  function clearRecordingTicker() {
    if (recordingTicker) {
      clearInterval(recordingTicker);
      recordingTicker = null;
    }
  }

  function startRecordingTicker() {
    clearRecordingTicker();
    renderRecordingTimer(0);

    recordingTicker = setInterval(() => {
      const elapsed = (Date.now() - recordingStartedAt) / 1000;
      renderRecordingTimer(Math.min(elapsed, maxVoiceSourceSeconds));
    }, 100);
  }

  function clearRecordingAutoStopTimer() {
    if (recordingAutoStopTimer) {
      clearTimeout(recordingAutoStopTimer);
      recordingAutoStopTimer = null;
    }

    clearRecordingTicker();
  }'''

    js = js.replace(anchor, replacement, 1)

old = '''  function startRecordingAutoStopTimer() {
    clearRecordingAutoStopTimer();

    recordingStartedAt = Date.now();

    recordingAutoStopTimer = setTimeout(() => {
      console.log(`[Clone Voice] auto-stopping recording at ${maxVoiceSourceSeconds} seconds`);

      if (!stopRecordingBtn.disabled) {
        stopRecording();
      }
    }, maxVoiceSourceSeconds * 1000);
  }'''

new = r'''  function startRecordingAutoStopTimer() {
    clearRecordingAutoStopTimer();

    recordingStartedAt = Date.now();
    startRecordingTicker();

    recordingAutoStopTimer = setTimeout(() => {
      console.log(`[Clone Voice] auto-stopping recording at ${maxVoiceSourceSeconds} seconds`);

      if (!stopRecordingBtn.disabled) {
        stopRecording();
      }
    }, maxVoiceSourceSeconds * 1000);
  }'''

if old in js:
    js = js.replace(old, new, 1)

if "renderRecordingTimer(maxVoiceSourceSeconds);" not in js:
    # In stopRecording(), after clearRecordingAutoStopTimer(); show final D reached if auto-stopped.
    stop_anchor = '''  async function stopRecording() {
    clearRecordingAutoStopTimer();

    try {'''

    if stop_anchor in js:
        js = js.replace(
            stop_anchor,
            '''  async function stopRecording() {
    const elapsedBeforeStop = recordingStartedAt ? Math.min((Date.now() - recordingStartedAt) / 1000, maxVoiceSourceSeconds) : 0;

    clearRecordingAutoStopTimer();
    renderRecordingTimer(elapsedBeforeStop);

    try {''',
            1,
        )

if "renderRecordingTimer(0);" not in js.split("function discardRecording()", 1)[-1]:
    discard_anchor = '''    recordingStatus.textContent = "Start recording, speak clearly, then stop.";'''
    if discard_anchor in js:
        js = js.replace(
            discard_anchor,
            discard_anchor + "\n    renderRecordingTimer(0);",
            1,
        )

# Make settings load update the visible max display.
old_settings_line = '''      if (recordingStatus) {
        recordingStatus.textContent = `Start recording, speak clearly, then stop. Recording auto-stops at ${maxVoiceSourceSeconds} seconds.`;
      }'''

new_settings_line = '''      if (recordingStatus) {
        recordingStatus.textContent = `Start recording, speak clearly, then stop. Recording auto-stops at ${maxVoiceSourceSeconds} seconds.`;
      }

      renderRecordingTimer(0);'''

if old_settings_line in js and new_settings_line not in js:
    js = js.replace(old_settings_line, new_settings_line, 1)

# Ensure initial render even if settings route fails.
if 'renderRecordingTimer(0);\n\n  setMode("upload");' not in js:
    js = js.replace(
        'setMode("upload");',
        'renderRecordingTimer(0);\n  setMode("upload");',
        1,
    )

JS.write_text(js, encoding="utf-8")

print()
print("Visible recording timer installed.")
print()
print("Recording panel now shows:")
print("  0.0s / D seconds")
print()
print("During recording it updates every 0.1 second.")
print("At D seconds recording auto-stops.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?visible-timer=1")
