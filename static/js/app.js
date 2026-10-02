// ── Upload w tle: panel na dole (jak Google Drive) ────────────────────────────
// Strona zostaje w pełni używalna podczas wgrywania. Każdy plik to osobne żądanie XHR
// z własnym paskiem, prędkością, czasem do końca i przyciskiem „Anuluj" (xhr.abort()).

const FvUpload = (function () {
  const CONCURRENCY = 2;
  const queue = [];      // zadania czekające
  let running = 0;       // aktywne żądania
  let okCount = 0, failCount = 0, totalCount = 0;
  let panel = null, listEl = null, titleEl = null, summaryEl = null;

  const trim = n => String(n).replace(/\.0+$/, '');
  const fmtSize = b => b >= 1073741824 ? trim((b / 1073741824).toFixed(2)) + ' GB'
                     : b >= 1048576    ? trim((b / 1048576).toFixed(1)) + ' MB'
                     : b >= 1024       ? Math.round(b / 1024) + ' KB' : b + ' B';
  const fmtTime = s => {
    if (!isFinite(s) || s < 0) return '…';
    if (s >= 3600) return Math.floor(s / 3600) + ' godz. ' + Math.floor(s % 3600 / 60) + ' min';
    if (s >= 60)   return Math.floor(s / 60) + ' min ' + Math.floor(s % 60) + ' s';
    return Math.max(1, Math.ceil(s)) + ' s';
  };

  function injectStyles() {
    if (document.getElementById('fvUpStyles')) return;
    const st = document.createElement('style');
    st.id = 'fvUpStyles';
    st.textContent = `
      #fvUpPanel{position:fixed;right:20px;bottom:0;width:360px;max-width:calc(100vw - 24px);
        background:var(--bg-2,#1a1d27);border:1px solid var(--border,#2e3250);border-bottom:0;
        border-radius:10px 10px 0 0;box-shadow:var(--shadow,0 4px 24px rgba(0,0,0,.4));
        z-index:9000;font-size:13px;color:var(--text,#e2e8f0)}
      #fvUpPanel .fvup-head{display:flex;align-items:center;gap:8px;padding:10px 12px;
        background:var(--bg-3,#222636);border-radius:10px 10px 0 0;cursor:pointer;user-select:none}
      #fvUpPanel .fvup-title{flex:1;font-weight:600}
      #fvUpPanel .fvup-hbtn{background:none;border:0;color:inherit;cursor:pointer;font-size:16px;line-height:1;padding:2px 6px;border-radius:4px}
      #fvUpPanel .fvup-hbtn:hover{background:rgba(255,255,255,.1)}
      #fvUpPanel .fvup-list{max-height:min(46vh,320px);overflow-y:auto}
      #fvUpPanel.collapsed .fvup-list,#fvUpPanel.collapsed .fvup-foot{display:none}
      .fvup-row{padding:10px 12px;border-top:1px solid var(--border,#2e3250)}
      .fvup-top{display:flex;align-items:center;gap:8px}
      .fvup-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .fvup-size{color:var(--text-muted,#64748b);font-size:12px;white-space:nowrap}
      .fvup-cancel{background:none;border:0;color:var(--text-muted,#64748b);cursor:pointer;font-size:18px;line-height:1;padding:0 4px;border-radius:4px}
      .fvup-cancel:hover{color:var(--danger,#ef4444)}
      .fvup-bar{height:4px;margin-top:8px;background:var(--bg,#0f1117);border-radius:2px;overflow:hidden}
      .fvup-fill{height:100%;width:0;background:var(--accent,#6366f1);transition:width .2s linear}
      .fvup-meta{margin-top:6px;font-size:12px;color:var(--text-muted,#64748b)}
      .fvup-row.done .fvup-fill{background:var(--success,#22c55e)}
      .fvup-row.done .fvup-meta{color:var(--success,#22c55e)}
      .fvup-row.error .fvup-fill{background:var(--danger,#ef4444)}
      .fvup-row.error .fvup-meta{color:var(--danger,#ef4444)}
      .fvup-row.cancelled .fvup-meta{color:var(--warning,#f59e0b)}
      .fvup-foot{padding:8px 12px;border-top:1px solid var(--border,#2e3250);display:flex;align-items:center;gap:8px;
        background:var(--bg-3,#222636);font-size:12px}
      .fvup-foot .fvup-summary{flex:1;color:var(--text-muted,#64748b)}
      .fvup-foot button{background:var(--accent,#6366f1);color:#fff;border:0;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px}
    `;
    document.head.appendChild(st);
  }

  function ensurePanel() {
    if (panel) { panel.style.display = ''; return; }
    injectStyles();
    panel = document.createElement('div');
    panel.id = 'fvUpPanel';
    panel.innerHTML = `
      <div class="fvup-head">
        <span class="fvup-title">Przesyłanie…</span>
        <button type="button" class="fvup-hbtn fvup-toggle" title="Zwiń / rozwiń">▾</button>
        <button type="button" class="fvup-hbtn fvup-close" title="Zamknij" style="display:none">×</button>
      </div>
      <div class="fvup-list"></div>
      <div class="fvup-foot"><span class="fvup-summary"></span></div>`;
    document.body.appendChild(panel);
    listEl    = panel.querySelector('.fvup-list');
    titleEl   = panel.querySelector('.fvup-title');
    summaryEl = panel.querySelector('.fvup-summary');
    panel.querySelector('.fvup-head').addEventListener('click', e => {
      if (e.target.closest('.fvup-close')) return;
      panel.classList.toggle('collapsed');
      panel.querySelector('.fvup-toggle').textContent = panel.classList.contains('collapsed') ? '▴' : '▾';
    });
    panel.querySelector('.fvup-close').addEventListener('click', () => {
      panel.style.display = 'none'; listEl.innerHTML = '';
      okCount = failCount = totalCount = 0;
    });
  }

  function refreshHeader() {
    if (!panel) return;
    const active = running + queue.length;
    const closeBtn = panel.querySelector('.fvup-close');
    if (active > 0) {
      titleEl.textContent = `Przesyłanie ${active} ${active === 1 ? 'pliku' : 'plików'}…`;
      closeBtn.style.display = 'none';
    } else {
      titleEl.textContent = failCount
        ? `Zakończono: ${okCount} ok, ${failCount} nieudane/anulowane`
        : `Przesłano ${okCount} ${okCount === 1 ? 'plik' : 'plików'}`;
      closeBtn.style.display = '';
    }
  }

  // Zbiorcze podsumowanie na samym dole panelu: % całości, prędkość, pozostały czas.
  const allJobs = [];
  function refreshSummary() {
    if (!summaryEl) return;
    const live = allJobs.filter(j => j.state === 'uploading' || j.state === 'queued');
    if (!live.length) { summaryEl.textContent = ''; return; }
    const total  = live.reduce((s, j) => s + j.file.size, 0);
    const loaded = live.reduce((s, j) => s + j.loaded, 0);
    const speed  = live.reduce((s, j) => s + (j.state === 'uploading' ? j.speed : 0), 0);
    const pct = total ? Math.min(100, loaded / total * 100) : 0;
    summaryEl.textContent = `Razem: ${pct.toFixed(0)}%` +
      (speed > 0 ? ` · ${fmtSize(speed)}/s · zostało ${fmtTime((total - loaded) / speed)}` : '');
  }

  function maybeFinish() {
    refreshHeader(); refreshSummary();
    if (running + queue.length > 0) return;
    window.removeEventListener('beforeunload', warnUnload);
    allJobs.length = 0;
    if (okCount === 0) return;
    // Odśwież listę plików — ale nie przerywaj użytkownikowi, jeśli akurat coś robi.
    const busy = document.querySelector('dialog[open]') ||
                 /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || '');
    if (!busy && failCount === 0) {
      setTimeout(() => window.location.reload(), 1200);
    } else {
      const foot = panel.querySelector('.fvup-foot');
      if (!foot.querySelector('button')) {
        const b = document.createElement('button');
        b.type = 'button'; b.textContent = 'Odśwież listę';
        b.onclick = () => window.location.reload();
        foot.appendChild(b);
      }
    }
  }

  function warnUnload(e) { e.preventDefault(); e.returnValue = ''; }

  function pump() {
    while (running < CONCURRENCY && queue.length) start(queue.shift());
    refreshHeader();
  }

  function start(job) {
    job.state = 'uploading';
    running++;
    const row = job.row;
    const fill = row.querySelector('.fvup-fill');
    const meta = row.querySelector('.fvup-meta');
    const cancelBtn = row.querySelector('.fvup-cancel');
    meta.textContent = 'Rozpoczynanie…';

    const fd = new FormData();
    fd.append(job.opts.fieldName || 'file', job.file);
    Object.entries(job.opts.fields || {}).forEach(([k, v]) => { if (v !== '' && v != null) fd.append(k, v); });

    const xhr = new XMLHttpRequest();
    job.xhr = xhr;
    xhr.open('POST', job.opts.url);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.setRequestHeader('Accept', 'application/json');

    let lastT = performance.now(), lastB = 0;
    xhr.upload.addEventListener('progress', e => {
      if (!e.lengthComputable) return;
      job.loaded = Math.min(e.loaded, job.file.size);
      const now = performance.now(), dt = (now - lastT) / 1000;
      if (dt >= 0.4) {                                  // wygładzona prędkość (EMA)
        const inst = (e.loaded - lastB) / dt;
        job.speed = job.speed ? job.speed * 0.6 + inst * 0.4 : inst;
        lastT = now; lastB = e.loaded;
      }
      const pct = e.total ? Math.min(100, e.loaded / e.total * 100) : 0;
      fill.style.width = pct + '%';
      if (e.loaded >= e.total) {                        // wszystko wysłane, serwer jeszcze zapisuje
        meta.textContent = '100% · przetwarzanie na serwerze…';
        cancelBtn.style.display = 'none';               // po dojściu do 100% anulowanie jest już niewiarygodne
      } else {
        meta.textContent = `${pct.toFixed(0)}% · ${job.speed ? fmtSize(job.speed) + '/s' : '…'}` +
          (job.speed ? ` · zostało ${fmtTime((e.total - e.loaded) / job.speed)}` : '');
      }
      refreshSummary();
    });

    const settle = (state, text) => {
      if (job.state === 'done' || job.state === 'error' || job.state === 'cancelled') return;
      job.state = state; running--;
      row.classList.add(state);
      meta.textContent = text;
      cancelBtn.style.display = 'none';
      if (state === 'done') { okCount++; fill.style.width = '100%'; } else { failCount++; }
      pump(); maybeFinish();
    };

    xhr.addEventListener('load', () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300 && (!data || data.ok !== false)) {
        settle('done', 'Przesłano · ' + fmtSize(job.file.size));
      } else {
        const msg = (data && data.error) ||
          (xhr.status === 413 ? 'Plik jest za duży.' :
           xhr.status === 429 ? 'Zbyt wiele żądań — spróbuj za chwilę.' :
           'Błąd serwera (' + xhr.status + ')');
        if (xhr.status === 413) alert(msg);
        settle('error', msg);
      }
    });
    xhr.addEventListener('error',   () => settle('error', 'Błąd sieci — nie wgrano pliku.'));
    xhr.addEventListener('timeout', () => settle('error', 'Przekroczono czas oczekiwania.'));
    xhr.addEventListener('abort',   () => settle('cancelled', 'Anulowano'));

    cancelBtn.onclick = () => xhr.abort();
    xhr.send(fd);
  }

  function makeRow(job) {
    const row = document.createElement('div');
    row.className = 'fvup-row';
    row.innerHTML = `
      <div class="fvup-top">
        <span class="fvup-name"></span>
        <span class="fvup-size"></span>
        <button type="button" class="fvup-cancel" title="Anuluj">×</button>
      </div>
      <div class="fvup-bar"><div class="fvup-fill"></div></div>
      <div class="fvup-meta">W kolejce…</div>`;
    row.querySelector('.fvup-name').textContent = job.file.name;
    row.querySelector('.fvup-name').title = job.file.name;
    row.querySelector('.fvup-size').textContent = fmtSize(job.file.size);
    row.querySelector('.fvup-cancel').onclick = () => {   // anulowanie pliku, który jeszcze czeka w kolejce
      const i = queue.indexOf(job);
      if (i === -1) return;
      queue.splice(i, 1);
      job.state = 'cancelled'; failCount++;
      row.classList.add('cancelled');
      row.querySelector('.fvup-meta').textContent = 'Anulowano';
      row.querySelector('.fvup-cancel').style.display = 'none';
      maybeFinish();
    };
    listEl.appendChild(row);
    return row;
  }

  /**
   * files: FileList | File[]
   * opts:  { url, fields: {folder_id: ...}, maxBytes, fieldName }
   */
  function enqueue(files, opts) {
    const arr = Array.from(files || []);
    if (!arr.length) return;

    // 1) Alert przy zbyt dużych plikach — takie pliki w ogóle nie są wysyłane.
    const max = Number(opts.maxBytes) || 0;
    const tooBig = max ? arr.filter(f => f.size > max) : [];
    const ok = max ? arr.filter(f => f.size <= max) : arr;
    if (tooBig.length) {
      const list = tooBig.slice(0, 8).map(f => `• ${f.name} (${fmtSize(f.size)})`).join('\n') +
                   (tooBig.length > 8 ? `\n… i ${tooBig.length - 8} więcej` : '');
      alert(`${tooBig.length === 1 ? 'Ten plik jest za duży' : 'Te pliki są za duże'}. ` +
            `Maksymalny rozmiar to ${fmtSize(max)}.\n\n${list}` +
            (ok.length ? '\n\nPozostałe pliki zostaną wgrane.' : ''));
    }
    if (!ok.length) return;

    ensurePanel();
    panel.classList.remove('collapsed');
    window.addEventListener('beforeunload', warnUnload);
    ok.forEach(file => {
      const job = { file, opts, loaded: 0, speed: 0, state: 'queued', xhr: null, row: null };
      job.row = makeRow(job);
      allJobs.push(job); queue.push(job); totalCount++;
    });
    pump(); refreshSummary();
  }

  return { enqueue, fmtSize };
})();

function startUpload() {
  const form      = document.getElementById('uploadForm');
  const fileInput = document.getElementById('fileInput');

  if (!fileInput || fileInput.files.length === 0) {
    showToast('Wybierz co najmniej jeden plik.');
    return;
  }

  const files = Array.from(fileInput.files);
  const folderField = form.querySelector('[name="folder_id"]');
  const folderId = folderField ? folderField.value : '';

  document.getElementById('uploadModal').close();   // modal się zamyka — strona od razu wolna
  fileInput.value = '';
  const fl = document.getElementById('fileList');
  if (fl) fl.innerHTML = '';

  FvUpload.enqueue(files, {
    url: form.dataset.uploadUrl || '/filevault/upload',
    fields: { folder_id: folderId },
    maxBytes: form.dataset.maxUploadBytes,
  });
}

// ── Share modal ───────────────────────────────────────────────────────────────
function openShare(fileId, filename) {
  const modal = document.getElementById('shareModal');
  const form  = document.getElementById('shareForm');
  const name  = document.getElementById('shareFilename');
  if (!modal) return;
  // Derive prefix from the current path to support any url_prefix (e.g. /filevault)
  const prefix = window.APP_PREFIX || (() => {
    const parts = window.location.pathname.split('/');
    // Find the segment before known view names, or fall back to first segment
    const knownViews = ['dashboard', 'folder', 'file', 'profile', 'admin', 'rooms'];
    for (let i = parts.length - 1; i >= 0; i--) {
      if (knownViews.includes(parts[i])) return parts.slice(0, i).join('/');
    }
    return '/' + (parts[1] || '');
  })();
  form.action = `${prefix}/file/${fileId}/share`;
  if (name) name.textContent = filename;
  modal.showModal();
}

// ── Copy link to clipboard ────────────────────────────────────────────────────
function copyLink(url) {
  navigator.clipboard.writeText(url).then(() => showToast('Link skopiowany do schowka!'));
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2800);
}

// ── Close modal on backdrop click ─────────────────────────────────────────────
document.querySelectorAll('dialog.modal').forEach(d => {
  d.addEventListener('click', e => { if (e.target === d) d.close(); });
});

// ── Auto-dismiss alerts ───────────────────────────────────────────────────────
setTimeout(() => {
  document.querySelectorAll('.alert').forEach(a => a.remove());
}, 5000);