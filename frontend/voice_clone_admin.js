(function () {
  const summary = document.querySelector('#adminSummary');
  const rows = document.querySelector('#adminRows');
  const refresh = document.querySelector('#refreshAdmin');
  const toastRegion = document.querySelector('#toastRegion');

  function toast(headline, detail) {
    if (!toastRegion) return;
    const note = document.createElement('div');
    note.className = 'toast';
    note.innerHTML = `<strong>${escapeHtml(headline)}</strong><span>${escapeHtml(detail || '')}</span>`;
    toastRegion.appendChild(note);
    window.setTimeout(() => note.remove(), 4600);
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function fmtBytes(bytes) {
    const value = Number(bytes || 0);
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  function fmtDate(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
  }

  function flatten(data) {
    return [
      ...(data.sources || []).map(item => ({ type: 'Source', ...item })),
      ...(data.voiceProfiles || []).map(item => ({ type: 'Profile', ...item })),
      ...(data.previews || []).map(item => ({ type: 'Preview', ...item })),
      ...(data.clones || []).map(item => ({ type: 'Clone', ...item })),
    ];
  }

  function render(data) {
    const counts = data.counts || {};
    summary.innerHTML = [
      ['Sources', counts.sources || 0],
      ['Profiles', counts.params || 0],
      ['Previews', counts.previews || 0],
      ['Clones', counts.clones || 0],
    ].map(([label, count]) => `
      <article class="stat-card">
        <p>${escapeHtml(label)}</p>
        <strong>${escapeHtml(count)}</strong>
      </article>
    `).join('');

    const items = flatten(data);
    if (!items.length) {
      rows.innerHTML = '<tr><td colspan="5">No voice assets found yet.</td></tr>';
      return;
    }

    rows.innerHTML = items.map(item => `
      <tr>
        <td>${escapeHtml(item.type)}</td>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(fmtBytes(item.sizeBytes))}</td>
        <td>${escapeHtml(fmtDate(item.modifiedAt))}</td>
        <td>${item.url ? `<a class="asset-lite-button" href="${escapeHtml(item.url)}" download>Download</a>` : '—'}</td>
      </tr>
    `).join('');
  }

  async function load() {
    try {
      refresh.disabled = true;
      const response = await fetch('/api/admin/voice-clone');
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      render(data);
    } catch (error) {
      toast('Admin load failed', error.message || 'Could not load voice admin state.');
      console.error(error);
    } finally {
      refresh.disabled = false;
    }
  }

  refresh?.addEventListener('click', load);
  load();
})();
