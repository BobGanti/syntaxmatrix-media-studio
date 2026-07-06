const STORAGE_KEY = 'syntaxmatrix-media-flask-state-v2';

const MODEL_REGISTRY = {
  textToImage: {
    label: 'Text → Image',
    endpointKey: 'textToImage',
    outputType: 'image',
    models: ['qwen-image-plus-2026-01-09', 'qwen-image-plus'],
    defaultPrompt: 'A man at a Coca-Cola promotion event in Dublin, premium commercial photography, elegant brand atmosphere.'
  },
  editToImage: {
    label: 'Edit → Image',
    endpointKey: 'editToImage',
    outputType: 'image',
    models: ['qwen-image-edit-plus-2025-12-15'],
    defaultPrompt: 'Make the man and the woman from Image 1 wear the outfit from Image 2 and the shoes from Image 3, preserving identity, realism, lighting and correct fitting.'
  },
  textToVideo: {
    label: 'Text → Video',
    endpointKey: 'textToVideo',
    outputType: 'video',
    models: ['wan2.6-t2v'],
    defaultPrompt: 'A cinematic detective office scene with warm mixed lighting, subtle camera motion and realistic speaking animation.'
  },
  imageToVideo: {
    label: 'Image → Video',
    endpointKey: 'imageToVideo',
    outputType: 'video',
    models: ['wan2.6-i2v', 'wan2.5-i2v'],
    defaultPrompt: 'Animate Image 1 into a smooth cinematic advertisement with subtle camera movement, premium lighting and realistic motion.'
  },
  voiceClone: {
    label: 'Voice Clone',
    endpointKey: 'voiceClone',
    outputType: 'audio',
    models: ['qwen3-tts-vc-2026-01-22', 'qwen-voice-enrollment'],
    defaultPrompt: 'Generate a confident, clear voiceover for a premium AI media company announcement.'
  }
};

const DEFAULT_ENDPOINTS = {
  textToImage: '/api/media/text-to-image',
  editToImage: '/api/media/edit-to-image',
  textToVideo: '/api/media/text-to-video',
  imageToVideo: '/api/media/image-to-video',
  voiceClone: '/api/media/voice-clone',
  health: '/api/health'
};

const WORKFLOW_DESCRIPTIONS = {
  textToImage: 'Prompt-based image generation through the image controller.',
  editToImage: 'Ordered multi-reference image editing. Image 1, Image 2 and Image 3 are sent to Flask in that exact order.',
  textToVideo: 'Prompt-based video generation using Wan text-to-video models.',
  imageToVideo: 'Animate one uploaded source image through the video controller.',
  voiceClone: 'Upload a voice source and produce a cloned voice narration asset.'
};

const state = loadState();
let activeWorkflow = state.activeWorkflow || 'textToImage';
let selectedImages = [null, null, null];
let pendingImageSlot = null;
let selectedVoiceFile = null;

const els = {
  sidebar: document.querySelector('#sidebar'),
  menuButton: document.querySelector('#menuButton'),
  themeButton: document.querySelector('#themeButton'),
  navLinks: [...document.querySelectorAll('[data-section-link]')],
  scrollButtons: [...document.querySelectorAll('[data-scroll-target]')],
  tabs: [...document.querySelectorAll('[data-workflow]')],
  form: document.querySelector('#generationForm'),
  modelSelect: document.querySelector('#modelSelect'),
  promptInput: document.querySelector('#promptInput'),
  qualitySelect: document.querySelector('#qualitySelect'),
  sizeSelect: document.querySelector('#sizeSelect'),
  resolutionSelect: document.querySelector('#resolutionSelect'),
  durationSelect: document.querySelector('#durationSelect'),
  seedInput: document.querySelector('#seedInput'),
  watermarkInput: document.querySelector('#watermarkInput'),
  promptExtendInput: document.querySelector('#promptExtendInput'),
  negativePromptInput: document.querySelector('#negativePromptInput'),
  imageUploadPanel: document.querySelector('#imageUploadPanel'),
  imageFiles: document.querySelector('#imageFiles'),
  imagePreviewStrip: document.querySelector('#imagePreviewStrip'),
  voiceUploadPanel: document.querySelector('#voiceUploadPanel'),
  voiceNameInput: document.querySelector('#voiceNameInput'),
  voiceFile: document.querySelector('#voiceFile'),
  advancedToggle: document.querySelector('#advancedToggle'),
  advancedContent: document.querySelector('#advancedContent'),
  submitButton: document.querySelector('#submitButton'),
  resultTitle: document.querySelector('#resultTitle'),
  resultBadge: document.querySelector('#resultBadge'),
  resultPreview: document.querySelector('#resultPreview'),
  resultMeta: document.querySelector('#resultMeta'),
  assetGrid: document.querySelector('#assetGrid'),
  modelGrid: document.querySelector('#modelGrid'),
  clearHistoryButton: document.querySelector('#clearHistoryButton'),
  totalGenerations: document.querySelector('#totalGenerations'),
  readyAssets: document.querySelector('#readyAssets'),
  jobCount: document.querySelector('#jobCount'),
  assetCount: document.querySelector('#assetCount'),
  draftPrompts: document.querySelector('#draftPrompts'),
  backendStatus: document.querySelector('#backendStatus'),
  studioModeLabel: document.querySelector('#studioModeLabel'),
  settingsForm: document.querySelector('#settingsForm'),
  apiBaseUrl: document.querySelector('#apiBaseUrl'),
  demoModeInput: document.querySelector('#demoModeInput'),
  endpointGrid: document.querySelector('#endpointGrid'),
  checkBackendButton: document.querySelector('#checkBackendButton'),
  toastRegion: document.querySelector('#toastRegion')
};

boot();

function boot() {
  applyTheme(state.theme || 'dark');
  renderEndpointSettings();
  hydrateSettingsForm();
  renderModels();
  bindEvents();
  setWorkflow(activeWorkflow, { preservePrompt: true });
  renderHistory();
  updateStats();
  renderLastResult();
  checkBackend({ silent: true });
}

function bindEvents() {
  els.menuButton?.addEventListener('click', () => {
    const open = els.sidebar.classList.toggle('open');
    els.menuButton.setAttribute('aria-expanded', String(open));
  });

  els.themeButton?.addEventListener('click', () => {
    const nextTheme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    applyTheme(nextTheme);
    state.theme = nextTheme;
    saveState();
  });

  els.navLinks.forEach(link => link.addEventListener('click', () => {
    els.sidebar.classList.remove('open');
    els.menuButton?.setAttribute('aria-expanded', 'false');
  }));

  els.scrollButtons.forEach(button => {
    button.addEventListener('click', () => document.getElementById(button.dataset.scrollTarget)?.scrollIntoView());
  });

  els.tabs.forEach(tab => {
    tab.addEventListener('click', () => setWorkflow(tab.dataset.workflow));
  });

  document.querySelectorAll('[data-prompt]').forEach(button => {
    button.addEventListener('click', () => {
      els.promptInput.value = button.dataset.prompt;
      els.promptInput.focus();
    });
  });

  els.advancedToggle?.addEventListener('click', () => {
    const shouldShow = els.advancedContent.hidden;
    els.advancedContent.hidden = !shouldShow;
    els.advancedToggle.setAttribute('aria-expanded', String(shouldShow));
    els.advancedToggle.textContent = shouldShow ? 'Hide advanced controls' : 'Show advanced controls';
  });

  els.imageFiles?.addEventListener('change', event => {
    const files = event.target.files ? [...event.target.files] : [];
    addImagesToSlots(files, pendingImageSlot);
    pendingImageSlot = null;
    event.target.value = '';
  });

  els.imagePreviewStrip?.addEventListener('click', event => {
    const remove = event.target.closest('[data-remove-image-slot]');
    if (remove) {
      event.preventDefault();
      selectedImages[Number(remove.dataset.removeImageSlot)] = null;
      renderImagePreviews();
      return;
    }

    const choose = event.target.closest('[data-choose-image-slot]');
    if (choose) {
      event.preventDefault();
      pendingImageSlot = Number(choose.dataset.chooseImageSlot);
      els.imageFiles?.click();
    }
  });

  els.voiceFile?.addEventListener('change', event => {
    selectedVoiceFile = event.target.files?.[0] || null;
    if (selectedVoiceFile) toast('Voice file selected', `${selectedVoiceFile.name} is ready for submission.`);
  });

  els.form?.addEventListener('submit', submitGeneration);

  els.form?.addEventListener('reset', () => {
    window.setTimeout(() => {
      resetSelectedImages();
      selectedVoiceFile = null;
      setWorkflow(activeWorkflow);
    }, 0);
  });

  els.clearHistoryButton?.addEventListener('click', () => {
    state.jobs = [];
    saveState();
    renderHistory();
    updateStats();
    renderEmptyResult();
    toast('History cleared', 'Local generation history has been removed from this browser.');
  });

  els.settingsForm?.addEventListener('submit', event => {
    event.preventDefault();
    persistSettingsFromForm();
    toast('Settings saved', 'The Flask backend adapter configuration has been saved.');
  });

  els.checkBackendButton?.addEventListener('click', () => checkBackend({ silent: false }));

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const section = entry.target.dataset.section;
          els.navLinks.forEach(link => link.classList.toggle('active', link.dataset.sectionLink === section));
        }
      });
    }, { threshold: 0.35 });
    document.querySelectorAll('[data-section]').forEach(section => observer.observe(section));
  }
}

function setWorkflow(workflow, options = {}) {
  if (!MODEL_REGISTRY[workflow]) workflow = 'textToImage';
  activeWorkflow = workflow;
  const config = MODEL_REGISTRY[workflow];
  state.activeWorkflow = workflow;
  saveState();

  els.tabs.forEach(tab => {
    const isActive = tab.dataset.workflow === workflow;
    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', String(isActive));
  });

  els.modelSelect.innerHTML = config.models
    .map(model => `<option value="${escapeAttribute(model)}">${escapeHtml(model)}</option>`)
    .join('');

  if (!options.preservePrompt || !els.promptInput.value.trim()) {
    els.promptInput.value = config.defaultPrompt;
  }

  const promptLabel = document.querySelector('#promptGroup > span');
  if (promptLabel) {
    promptLabel.textContent = workflow === 'editToImage'
      ? 'Edit instruction. Refer to uploads as Image 1, Image 2 and Image 3.'
      : workflow === 'voiceClone'
        ? 'Narration text'
        : 'Prompt / creative brief';
  }

  const needsImages = workflow === 'editToImage' || workflow === 'imageToVideo';
  const needsVoice = workflow === 'voiceClone';
  const videoFields = workflow === 'textToVideo' || workflow === 'imageToVideo';

  els.imageUploadPanel.hidden = !needsImages;
  els.voiceUploadPanel.hidden = !needsVoice;

  const fieldSize = document.querySelector('[data-field="size"]');
  const fieldResolution = document.querySelector('[data-field="resolution"]');
  const fieldDuration = document.querySelector('[data-field="duration"]');
  const fieldSeed = document.querySelector('[data-field="seed"]');

  if (fieldSize) fieldSize.hidden = videoFields || needsVoice;
  if (fieldResolution) fieldResolution.hidden = !videoFields;
  if (fieldDuration) fieldDuration.hidden = !videoFields;
  if (fieldSeed) fieldSeed.hidden = needsVoice;

  configureImageUploadPanel(workflow);
  if (!needsImages) resetSelectedImages(false);

  if (els.imageFiles) {
    els.imageFiles.disabled = !needsImages;
    els.imageFiles.multiple = workflow === 'editToImage';
  }

  if (els.voiceFile) els.voiceFile.disabled = !needsVoice;

  els.submitButton.textContent = workflow === 'editToImage'
    ? 'Generate edited image'
    : workflow === 'textToImage'
      ? 'Generate image'
      : workflow === 'textToVideo'
        ? 'Generate video'
        : workflow === 'imageToVideo'
          ? 'Animate image'
          : 'Generate voice asset';

  toast(config.label, WORKFLOW_DESCRIPTIONS[workflow]);
}

function configureImageUploadPanel(workflow) {
  const title = els.imageUploadPanel?.querySelector('.field-title');
  const help = els.imageUploadPanel?.querySelector('p');
  const strong = els.imageUploadPanel?.querySelector('.dropzone strong');
  const hint = els.imageUploadPanel?.querySelector('.dropzone span');

  if (workflow === 'editToImage') {
    if (title) title.textContent = 'Ordered reference images';
    if (help) help.textContent = 'Load Image 1, Image 2 and Image 3. The backend receives them in exactly this order.';
    if (strong) strong.textContent = 'Browse or drop up to 3 images';
    if (hint) hint.textContent = 'Your prompt can safely refer to Image 1, Image 2 and Image 3.';
  } else if (workflow === 'imageToVideo') {
    if (title) title.textContent = 'Source image';
    if (help) help.textContent = 'Load the single source image to animate.';
    if (strong) strong.textContent = 'Browse or drop one source image';
    if (hint) hint.textContent = 'Image 1 is sent as the source image.';
  }

  renderImagePreviews();
}

function resetSelectedImages(render = true) {
  selectedImages = [null, null, null];
  pendingImageSlot = null;
  if (els.imageFiles) els.imageFiles.value = '';
  if (render) renderImagePreviews();
}

function imageSlotLimit() {
  if (activeWorkflow === 'editToImage') return 3;
  if (activeWorkflow === 'imageToVideo') return 1;
  return 0;
}

function selectedImageFiles() {
  const limit = imageSlotLimit();
  return selectedImages.slice(0, limit).filter(file => file instanceof File);
}

function hasImageGap() {
  const limit = imageSlotLimit();
  let seenEmpty = false;
  for (let index = 0; index < limit; index += 1) {
    if (!selectedImages[index]) seenEmpty = true;
    else if (seenEmpty) return true;
  }
  return false;
}

function addImagesToSlots(fileList, preferredSlot = null) {
  const limit = imageSlotLimit();
  if (!limit) return;

  const incoming = [...fileList].filter(file => file?.type?.startsWith('image/'));
  if (!incoming.length) return;

  let added = 0;
  const queue = incoming.slice();

  if (Number.isInteger(preferredSlot) && preferredSlot >= 0 && preferredSlot < limit && queue.length) {
    selectedImages[preferredSlot] = queue.shift();
    added += 1;
  }

  for (const file of queue) {
    const emptyIndex = selectedImages.slice(0, limit).findIndex(existing => !existing);
    if (emptyIndex === -1) break;
    selectedImages[emptyIndex] = file;
    added += 1;
  }

  if (incoming.length > added) {
    toast('Image limit applied', activeWorkflow === 'editToImage'
      ? 'Edit → Image accepts exactly three ordered slots: Image 1, Image 2 and Image 3.'
      : 'Image → Video accepts one source image.');
  }

  renderImagePreviews();
}

function renderImagePreviews() {
  if (!els.imagePreviewStrip) return;
  const limit = imageSlotLimit();
  els.imagePreviewStrip.innerHTML = '';
  els.imagePreviewStrip.classList.toggle('ordered-image-slots', limit > 0);

  if (!limit) return;

  for (let index = 0; index < limit; index += 1) {
    const file = selectedImages[index];
    const tile = document.createElement('article');
    tile.className = `preview-tile ordered-slot${file ? ' has-file' : ' is-empty'}`;

    const badge = document.createElement('span');
    badge.className = 'slot-badge';
    badge.textContent = `Image ${index + 1}`;
    tile.appendChild(badge);

    if (file) {
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'slot-remove-button';
      remove.dataset.removeImageSlot = String(index);
      remove.setAttribute('aria-label', `Remove Image ${index + 1}`);
      remove.textContent = '×';
      tile.appendChild(remove);

      const img = document.createElement('img');
      img.alt = `Image ${index + 1}: ${file.name}`;
      img.src = URL.createObjectURL(file);
      img.onload = () => URL.revokeObjectURL(img.src);
      tile.appendChild(img);

      const meta = document.createElement('div');
      meta.className = 'slot-meta';
      meta.innerHTML = `<strong>${escapeHtml(file.name)}</strong><span>${Math.max(1, Math.round(file.size / 1024))} KB</span>`;
      tile.appendChild(meta);

      const replace = document.createElement('button');
      replace.type = 'button';
      replace.className = 'slot-replace-button';
      replace.dataset.chooseImageSlot = String(index);
      replace.textContent = `Replace Image ${index + 1}`;
      tile.appendChild(replace);
    } else {
      const choose = document.createElement('button');
      choose.type = 'button';
      choose.className = 'slot-load-button';
      choose.dataset.chooseImageSlot = String(index);
      choose.innerHTML = `<strong>Load Image ${index + 1}</strong><span>This file will be sent as Image ${index + 1}</span>`;
      tile.appendChild(choose);
    }

    els.imagePreviewStrip.appendChild(tile);
  }
}

async function submitGeneration(event) {
  event.preventDefault();
  const payload = await buildPayload();
  if (!payload) return;

  const config = MODEL_REGISTRY[activeWorkflow];
  const job = {
    id: makeId(),
    title: config.label,
    workflow: activeWorkflow,
    workflowLabel: config.label,
    model: payload.model,
    prompt: payload.prompt,
    status: 'running',
    createdAt: new Date().toISOString(),
    outputType: config.outputType,
    endpoint: getEndpoint(config.endpointKey)
  };

  addJob(job);
  renderResult(job);
  setSubmitting(true);

  try {
    const response = await callBackend(config.endpointKey, payload);
    const normalized = normalizeResponse(response, config.outputType);
    const completed = {
      ...job,
      status: normalized.assetUrl ? 'ready' : 'completed',
      assetUrl: normalized.assetUrl,
      rawResponse: response,
      message: normalized.message || 'Generation request completed.'
    };
    updateJob(completed);
    renderResult(completed);
    toast('Generation complete', completed.assetUrl ? 'The returned asset is ready for review.' : completed.message);
  } catch (error) {
    const failed = {
      ...job,
      status: 'failed',
      message: error.message || 'Backend request failed.'
    };
    updateJob(failed);
    renderResult(failed);
    toast('Generation failed', failed.message);
    console.error(error);
  } finally {
    setSubmitting(false);
  }
}

async function buildPayload() {
  const prompt = els.promptInput.value.trim();
  if (!prompt) {
    toast('Prompt required', 'Add a creative brief before generating an asset.');
    els.promptInput.focus();
    return null;
  }

  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && selectedImageFiles().length === 0) {
    toast('Reference image required', activeWorkflow === 'editToImage'
      ? 'Load Image 1, then Image 2 and Image 3 as needed.'
      : 'Load one source image for Image → Video.');
    return null;
  }

  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && hasImageGap()) {
    toast('Fix image order', 'Do not leave an empty slot before a later image. Image 1, Image 2 and Image 3 must stay in sequence.');
    return null;
  }

  if (activeWorkflow === 'voiceClone' && !selectedVoiceFile) {
    toast('Audio source required', 'Upload a clean voice sample before generating a cloned voice asset.');
    return null;
  }

  const payload = {
    workflow: activeWorkflow,
    model: els.modelSelect.value,
    prompt,
    quality: els.qualitySelect?.value || 'premium',
    watermark: Boolean(els.watermarkInput?.checked),
    promptExtend: Boolean(els.promptExtendInput?.checked),
    negativePrompt: els.negativePromptInput?.value.trim() || ''
  };

  if (activeWorkflow === 'textToImage' || activeWorkflow === 'editToImage') {
    payload.size = els.sizeSelect.value;
  }

  if (activeWorkflow === 'textToVideo' || activeWorkflow === 'imageToVideo') {
    payload.resolution = els.resolutionSelect.value;
    payload.duration = Number(els.durationSelect.value);
  }

  const seed = els.seedInput?.value.trim();
  if (seed) payload.seed = Number(seed);

  if (activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') {
    const files = selectedImageFiles();
    payload.imageFiles = files;
    payload.imageNames = files.map(file => file.name);
    payload.imageLabels = files.map((_, index) => `Image ${index + 1}`);
    payload.imageSlots = files.map((_, index) => index + 1);
  }

  if (activeWorkflow === 'voiceClone') {
    payload.voiceName = els.voiceNameInput.value.trim() || 'smxVoice';
    payload.audioFile = selectedVoiceFile;
    payload.audioName = selectedVoiceFile.name;
  }

  return payload;
}

async function callBackend(endpointKey, payload) {
  const url = joinUrl(state.settings.apiBaseUrl, getEndpoint(endpointKey));
  const hasFiles = payload.imageFiles?.length || payload.audioFile instanceof File;

  const options = hasFiles
    ? { method: 'POST', body: buildFormData(payload) }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) };

  const response = await fetch(url, options);
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text };
  }

  if (!response.ok) {
    const reason = data?.message || data?.error || `HTTP ${response.status}`;
    throw new Error(reason);
  }

  return data;
}

function buildFormData(payload) {
  const formData = new FormData();

  Object.entries(payload).forEach(([key, value]) => {
    if (key === 'imageFiles' || key === 'audioFile') return;
    if (value === undefined || value === null) return;
    if (Array.isArray(value) || typeof value === 'object') formData.append(key, JSON.stringify(value));
    else formData.append(key, String(value));
  });

  if (payload.imageFiles?.length) {
    payload.imageFiles.forEach((file, index) => {
      // Flask reads these with request.files.getlist('image').
      // Order is preserved: first file = Image 1, second = Image 2, third = Image 3.
      formData.append('image', file, file.name);
      formData.append('imageLabel', `Image ${index + 1}`);
      formData.append('imageName', file.name);
    });
  }

  if (payload.audioFile instanceof File) {
    formData.append('audio', payload.audioFile, payload.audioFile.name);
  }

  return formData;
}

function normalizeResponse(response, outputType) {
  const assetUrl = response?.imageUrl
    || response?.videoUrl
    || response?.audioUrl
    || response?.url
    || response?.assetUrl
    || response?.output?.imageUrl
    || response?.output?.videoUrl
    || response?.output?.audioUrl
    || response?.output?.url
    || null;

  return {
    assetUrl,
    outputType,
    message: response?.message || response?.status || (response?.dryRun ? 'Dry-run completed. Upload order was accepted by Flask.' : null)
  };
}

function addJob(job) {
  state.jobs = [job, ...(state.jobs || [])].slice(0, 24);
  saveState();
  renderHistory();
  updateStats();
}

function updateJob(job) {
  state.jobs = (state.jobs || []).map(existing => existing.id === job.id ? job : existing);
  saveState();
  renderHistory();
  updateStats();
}

function renderHistory() {
  const jobs = state.jobs || [];
  if (!jobs.length) {
    els.assetGrid.innerHTML = `<article class="asset-card"><h3>No generations yet</h3><p>Create your first asset from the creation console. Completed jobs will be listed here.</p></article>`;
    return;
  }

  els.assetGrid.innerHTML = jobs.map(job => `
    <article class="asset-card" data-job-id="${escapeAttribute(job.id)}">
      <div class="asset-card-header">
        <div>
          <h3>${escapeHtml(job.workflowLabel)}</h3>
          <p>${escapeHtml(job.model)}</p>
        </div>
        <span class="badge">${escapeHtml(job.status)}</span>
      </div>
      <div class="asset-thumb">${renderAssetThumb(job)}</div>
      <p>${escapeHtml(truncate(job.prompt, 112))}</p>
    </article>
  `).join('');
}

function renderAssetThumb(job) {
  if (job.assetUrl && job.outputType === 'image') {
    return `<img src="${escapeAttribute(job.assetUrl)}" alt="Generated image" />`;
  }
  if (job.assetUrl && job.outputType === 'video') {
    return `<video src="${escapeAttribute(job.assetUrl)}" muted playsinline></video>`;
  }
  if (job.assetUrl && job.outputType === 'audio') return 'Audio asset';
  return job.status === 'running' ? 'Generating…' : 'No preview';
}

function renderResult(job) {
  els.resultTitle.textContent = job.workflowLabel;
  els.resultBadge.textContent = job.status;
  els.resultPreview.innerHTML = renderResultPreview(job);
  els.resultMeta.innerHTML = `
    <div><dt>Workflow</dt><dd>${escapeHtml(job.workflowLabel)}</dd></div>
    <div><dt>Model</dt><dd>${escapeHtml(job.model)}</dd></div>
    <div><dt>Created</dt><dd>${formatDate(job.createdAt)}</dd></div>
  `;
}

function renderLastResult() {
  const first = state.jobs?.[0];
  if (first) renderResult(first);
  else renderEmptyResult();
}

function renderEmptyResult() {
  els.resultTitle.textContent = 'No job selected';
  els.resultBadge.textContent = 'Idle';
  els.resultPreview.innerHTML = '<span>Generated media will appear here when Flask returns an asset URL.</span>';
  els.resultMeta.innerHTML = '<div><dt>Workflow</dt><dd>—</dd></div><div><dt>Model</dt><dd>—</dd></div><div><dt>Created</dt><dd>—</dd></div>';
}

function renderResultPreview(job) {
  if (job.status === 'running') return '<span>Submitting request to Flask…</span>';

  if (!job.assetUrl) {
    const msg = job.message || 'No asset URL returned yet.';
    return `<span>${escapeHtml(msg)}</span>`;
  }

  if (job.outputType === 'image') return `<img src="${escapeAttribute(job.assetUrl)}" alt="Generated image" />`;
  if (job.outputType === 'video') return `<video src="${escapeAttribute(job.assetUrl)}" controls playsinline></video>`;
  if (job.outputType === 'audio') return `<audio src="${escapeAttribute(job.assetUrl)}" controls></audio>`;
  return `<a href="${escapeAttribute(job.assetUrl)}" target="_blank" rel="noreferrer">Open generated asset</a>`;
}

function renderModels() {
  const cards = Object.entries(MODEL_REGISTRY).map(([key, config]) => `
    <article class="model-card">
      <div class="model-card-header">
        <div>
          <h3>${escapeHtml(config.label)}</h3>
          <p>${escapeHtml(WORKFLOW_DESCRIPTIONS[key])}</p>
        </div>
        <span class="badge">${escapeHtml(config.outputType)}</span>
      </div>
      <div class="model-pill-list">
        ${config.models.map(model => `<span>${escapeHtml(model)}</span>`).join('')}
      </div>
    </article>
  `).join('');

  els.modelGrid.innerHTML = cards;
}

function renderEndpointSettings() {
  els.endpointGrid.innerHTML = Object.entries(DEFAULT_ENDPOINTS).map(([key]) => `
    <label>
      <span>${humanize(key)} endpoint</span>
      <input data-endpoint-key="${escapeAttribute(key)}" type="text" />
    </label>
  `).join('');
}

function hydrateSettingsForm() {
  els.apiBaseUrl.value = state.settings.apiBaseUrl;
  els.demoModeInput.checked = Boolean(state.settings.demoMode);
  document.querySelectorAll('[data-endpoint-key]').forEach(input => {
    input.value = state.settings.endpoints[input.dataset.endpointKey] || DEFAULT_ENDPOINTS[input.dataset.endpointKey];
  });
  els.studioModeLabel.textContent = 'Flask live';
}

function persistSettingsFromForm() {
  state.settings.apiBaseUrl = els.apiBaseUrl.value.trim() || window.location.origin;
  state.settings.demoMode = Boolean(els.demoModeInput.checked);
  document.querySelectorAll('[data-endpoint-key]').forEach(input => {
    state.settings.endpoints[input.dataset.endpointKey] = input.value.trim() || DEFAULT_ENDPOINTS[input.dataset.endpointKey];
  });
  els.studioModeLabel.textContent = 'Flask live';
  saveState();
}

async function checkBackend(options = {}) {
  persistSettingsFromForm();
  els.backendStatus.textContent = 'Checking…';
  try {
    const response = await fetch(joinUrl(state.settings.apiBaseUrl, getEndpoint('health')));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    els.backendStatus.textContent = 'Online';
    if (!options.silent) toast('Backend online', 'The Flask health endpoint responded successfully.');
  } catch (error) {
    els.backendStatus.textContent = 'Unavailable';
    if (!options.silent) toast('Backend unavailable', `Health check failed: ${error.message}`);
  }
}

function updateStats() {
  const jobs = state.jobs || [];
  const ready = jobs.filter(job => job.status === 'ready' || job.assetUrl).length;
  els.totalGenerations.textContent = String(jobs.length);
  els.readyAssets.textContent = String(ready);
  els.jobCount.textContent = String(jobs.length);
  els.assetCount.textContent = String(ready);
  els.draftPrompts.textContent = String(document.querySelectorAll('[data-prompt]').length + 2);
}

function setSubmitting(isSubmitting) {
  els.submitButton.disabled = isSubmitting;
  if (isSubmitting) {
    els.submitButton.textContent = activeWorkflow === 'editToImage' ? 'Generating edited image…' : 'Submitting…';
  } else {
    setWorkflow(activeWorkflow, { preservePrompt: true });
  }
}

function getEndpoint(key) {
  return state.settings.endpoints[key] || DEFAULT_ENDPOINTS[key];
}

function joinUrl(baseUrl, endpoint) {
  const base = (baseUrl || '').replace(/\/$/, '');
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${base}${path}`;
}

function loadState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (parsed) {
      return {
        jobs: parsed.jobs || [],
        activeWorkflow: parsed.activeWorkflow || 'textToImage',
        theme: parsed.theme || 'dark',
        settings: {
          apiBaseUrl: parsed.settings?.apiBaseUrl || window.location.origin,
          demoMode: false,
          endpoints: { ...DEFAULT_ENDPOINTS, ...(parsed.settings?.endpoints || {}) }
        }
      };
    }
  } catch {}

  return {
    jobs: [],
    activeWorkflow: 'textToImage',
    theme: 'dark',
    settings: {
      apiBaseUrl: window.location.origin,
      demoMode: false,
      endpoints: { ...DEFAULT_ENDPOINTS }
    }
  };
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  if (els.themeButton) els.themeButton.textContent = theme === 'light' ? '☾' : '☼';
}

function toast(title, message) {
  if (!els.toastRegion) return;
  const note = document.createElement('div');
  note.className = 'toast';
  note.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(message || '')}</span>`;
  els.toastRegion.appendChild(note);
  window.setTimeout(() => note.remove(), 4600);
}

function makeId() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  return `job_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function humanize(key) {
  return key.replace(/([A-Z])/g, ' $1').replace(/^./, c => c.toUpperCase());
}

function truncate(value, length) {
  const text = String(value || '');
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll('`', '&#096;');
}

// Debug helper for your exact issue. Run this in browser DevTools after uploading images.
window.__debugSyntaxMatrixUpload = function debugSyntaxMatrixUpload() {
  const files = selectedImageFiles();
  console.table(files.map((file, index) => ({
    slot: `Image ${index + 1}`,
    name: file.name,
    type: file.type,
    sizeKB: Math.round(file.size / 1024)
  })));
  return {
    workflow: activeWorkflow,
    endpoint: getEndpoint(MODEL_REGISTRY[activeWorkflow].endpointKey),
    imageCount: files.length,
    imageNames: files.map(file => file.name),
    prompt: els.promptInput.value.trim()
  };
};


