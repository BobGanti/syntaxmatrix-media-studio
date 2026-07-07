from pathlib import Path
from datetime import datetime
import re

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
    backup = path.with_name(path.name + f".bak.mic-signal-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# HTML: add visible mic meter under recording timer/status.
# -------------------------------------------------------------------
html = HTML.read_text(encoding="utf-8")

if 'id="micMeter"' not in html:
    mic_meter_html = '''            <div class="mic-meter" id="micMeter" aria-label="Microphone input level">
              <span class="mic-meter-label">Mic signal</span>
              <div class="mic-meter-track">
                <div class="mic-meter-fill" id="micMeterFill"></div>
              </div>
              <span class="mic-meter-value" id="micMeterValue">silent</span>
            </div>
'''

    if 'id="recordingTimer"' in html:
        html = re.sub(
            r'(\s*<div class="record-timer" id="recordingTimer"[^>]*>[\s\S]*?</div>\s*)',
            r'\1' + mic_meter_html,
            html,
            count=1,
        )
    elif 'id="recordingStatus"' in html:
        html = re.sub(
            r'(\s*<p class="status" id="recordingStatus">[\s\S]*?</p>\s*)',
            r'\1' + mic_meter_html,
            html,
            count=1,
        )
    else:
        print("ERROR: Could not find recordingStatus or recordingTimer in client.html.")
        raise SystemExit(1)

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=mic-signal-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

# -------------------------------------------------------------------
# CSS: add clean mic meter styling.
# -------------------------------------------------------------------
css = CSS.read_text(encoding="utf-8")

if ".mic-meter" not in css:
    css += r'''

.mic-meter {
  display: grid;
  grid-template-columns: auto minmax(140px, 1fr) auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #465662;
  border-radius: 14px;
  background: #071017;
}

.mic-meter-label,
.mic-meter-value {
  color: #a9bfd3;
  font-size: 0.92rem;
  font-weight: 800;
  white-space: nowrap;
}

.mic-meter-track {
  position: relative;
  width: 100%;
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: #1e2a34;
  border: 1px solid #33414c;
}

.mic-meter-fill {
  width: 0%;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #9ee8dc, #82a8ff);
  transition: width 80ms linear;
}

.mic-meter.is-active .mic-meter-value {
  color: #9ee8dc;
}

.mic-meter.is-loud .mic-meter-fill {
  background: linear-gradient(90deg, #9ee8dc, #ffd166);
}

@media (max-width: 720px) {
  .mic-meter {
    grid-template-columns: 1fr;
  }
}
'''

CSS.write_text(css, encoding="utf-8")

# -------------------------------------------------------------------
# JS: add analyser-based mic signal meter.
# -------------------------------------------------------------------
js = JS.read_text(encoding="utf-8")

if 'const micMeter = $("#micMeter");' not in js:
    if 'const recordingTimer = $("#recordingTimer");' in js:
        js = js.replace(
            'const recordingTimer = $("#recordingTimer");',
            '''const recordingTimer = $("#recordingTimer");
  const micMeter = $("#micMeter");
  const micMeterFill = $("#micMeterFill");
  const micMeterValue = $("#micMeterValue");''',
            1,
        )
    elif 'const recordingStatus = $("#recordingStatus");' in js:
        js = js.replace(
            'const recordingStatus = $("#recordingStatus");',
            '''const recordingStatus = $("#recordingStatus");
  const micMeter = $("#micMeter");
  const micMeterFill = $("#micMeterFill");
  const micMeterValue = $("#micMeterValue");''',
            1,
        )
    else:
        print("ERROR: Could not find recording const block in client.js.")
        raise SystemExit(1)

if "let micAnalyserNode = null;" not in js:
    anchor = "let recordedFilename = \"\";"
    if anchor not in js:
        print("ERROR: Could not find recordedFilename variable in client.js.")
        raise SystemExit(1)

    js = js.replace(
        anchor,
        '''let recordedFilename = "";

  let micAnalyserNode = null;
  let micMeterData = null;
  let micMeterAnimationFrame = null;''',
        1,
    )

if "function renderMicLevel" not in js:
    insert_before = "async function startRecording()"

    if insert_before not in js:
        print("ERROR: Could not find startRecording function in client.js.")
        raise SystemExit(1)

    mic_meter_js = r'''function renderMicLevel(level) {
    const safeLevel = Math.max(0, Math.min(1, Number(level) || 0));
    const percent = Math.round(safeLevel * 100);

    if (micMeterFill) {
      micMeterFill.style.width = `${percent}%`;
    }

    if (micMeter) {
      micMeter.classList.toggle("is-active", safeLevel > 0.08);
      micMeter.classList.toggle("is-loud", safeLevel > 0.72);
    }

    if (micMeterValue) {
      if (safeLevel < 0.04) {
        micMeterValue.textContent = "silent";
      } else if (safeLevel < 0.18) {
        micMeterValue.textContent = "low";
      } else if (safeLevel < 0.72) {
        micMeterValue.textContent = "good";
      } else {
        micMeterValue.textContent = "loud";
      }
    }
  }

  function stopMicMeter() {
    if (micMeterAnimationFrame) {
      cancelAnimationFrame(micMeterAnimationFrame);
      micMeterAnimationFrame = null;
    }

    try {
      if (micAnalyserNode) {
        micAnalyserNode.disconnect();
      }
    } catch {}

    micAnalyserNode = null;
    micMeterData = null;
    renderMicLevel(0);
  }

  function startMicMeter(sourceNode, audioCtx) {
    stopMicMeter();

    if (!sourceNode || !audioCtx) {
      renderMicLevel(0);
      return;
    }

    micAnalyserNode = audioCtx.createAnalyser();
    micAnalyserNode.fftSize = 2048;
    micAnalyserNode.smoothingTimeConstant = 0.82;
    micMeterData = new Uint8Array(micAnalyserNode.fftSize);

    sourceNode.connect(micAnalyserNode);

    const tick = () => {
      if (!micAnalyserNode || !micMeterData) {
        renderMicLevel(0);
        return;
      }

      micAnalyserNode.getByteTimeDomainData(micMeterData);

      let sumSquares = 0;

      for (let index = 0; index < micMeterData.length; index += 1) {
        const centered = (micMeterData[index] - 128) / 128;
        sumSquares += centered * centered;
      }

      const rms = Math.sqrt(sumSquares / micMeterData.length);

      // Scale RMS so normal speaking produces a visible response.
      const level = Math.min(1, rms * 4.5);

      renderMicLevel(level);

      micMeterAnimationFrame = requestAnimationFrame(tick);
    };

    tick();
  }

  '''

    js = js.replace(insert_before, mic_meter_js + insert_before, 1)

if "startMicMeter(micSource, audioContext);" not in js:
    anchor = "micSource = audioContext.createMediaStreamSource(micStream);"

    if anchor not in js:
        print("ERROR: Could not find micSource creation line in startRecording.")
        raise SystemExit(1)

    js = js.replace(
        anchor,
        anchor + "\n      startMicMeter(micSource, audioContext);",
        1,
    )

# Ensure stopRecording stops meter.
if re.search(r'async function stopRecording\(\)\s*\{\s*stopMicMeter\(\);', js) is None:
    js = re.sub(
        r'(async function stopRecording\(\)\s*\{)',
        r'\1\n    stopMicMeter();',
        js,
        count=1,
    )

# Ensure discardRecording stops meter.
if re.search(r'function discardRecording\(\)\s*\{\s*stopMicMeter\(\);', js) is None:
    js = re.sub(
        r'(function discardRecording\(\)\s*\{)',
        r'\1\n    stopMicMeter();',
        js,
        count=1,
    )

# Ensure initial reset.
if 'renderMicLevel(0);\n\n  setMode("upload");' not in js:
    js = js.replace(
        'setMode("upload");',
        'renderMicLevel(0);\n  setMode("upload");',
        1,
    )

JS.write_text(js, encoding="utf-8")

print()
print("Mic volume signal installed.")
print()
print("Frontend-only changes:")
print("  frontend/clone_voice/client.html")
print("  frontend/clone_voice/client.css")
print("  frontend/clone_voice/client.js")
print()
print("No controller, service, provider, or workspace files were touched.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?mic-signal=1")
