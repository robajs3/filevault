// ── Upload z paskiem postępu ──────────────────────────────────────────────────

function startUpload() {
  const form      = document.getElementById('uploadForm');
  const fileInput = document.getElementById('fileInput');

  if (!fileInput || fileInput.files.length === 0) {
    showToast('Wybierz co najmniej jeden plik.');
    return;
  }

  const files     = Array.from(fileInput.files);
  const totalSize = files.reduce((s, f) => s + f.size, 0);
  let loadedTotal  = 0;
  let currentIndex = 0;

  // Zbierz folder_id z formularza (ukryte pole lub select)
  const folderField = form.querySelector('[name="folder_id"]');
  const folderId    = folderField ? folderField.value : '';

  const overlay = document.getElementById('uploadOverlay');
  const circle  = document.getElementById('uploadProgressCircle');
  const pctText = document.getElementById('uploadPercentText');
  const nameEl  = document.getElementById('uploadFileName');
  const CIRC    = 326.7; // 2π × r(52)

  function setProgress(pct) {
    const offset = CIRC * (1 - pct / 100);
    circle.style.strokeDashoffset = offset;
    pctText.textContent = Math.round(pct) + '%';
  }

  document.getElementById('uploadModal').close();
  overlay.style.display = 'flex';
  setProgress(0);

  function uploadNext() {
    if (currentIndex >= files.length) {
      overlay.style.display = 'none';
      window.location.reload();
      return;
    }

    const file = files[currentIndex];
    nameEl.textContent = file.name;

    const fd = new FormData();
    fd.append('file', file);
    if (folderId) fd.append('folder_id', folderId);

    const xhr        = new XMLHttpRequest();
    const prevLoaded = loadedTotal;

    xhr.upload.addEventListener('progress', function(e) {
      if (!e.lengthComputable) return;
      const globalLoaded = prevLoaded + e.loaded;
      const pct = totalSize > 0 ? (globalLoaded / totalSize) * 100 : 0;
      setProgress(Math.min(pct, 99));
    });

    xhr.addEventListener('load', function() {
      loadedTotal += file.size;
      currentIndex++;
      const pct = totalSize > 0 ? (loadedTotal / totalSize) * 100 : 100;
      setProgress(pct);
      uploadNext();
    });

    xhr.addEventListener('error', function() {
      overlay.style.display = 'none';
      showToast('Błąd podczas wgrywania: ' + file.name);
      currentIndex++;
      uploadNext();
    });

    const uploadUrl = form.dataset.uploadUrl || '/filevault/upload';
    xhr.open('POST', uploadUrl);
    xhr.send(fd);
  }

  uploadNext();
}

// ── Share modal ───────────────────────────────────────────────────────────────
function openShare(fileId, filename) {
  const modal = document.getElementById('shareModal');
  const form  = document.getElementById('shareForm');
  const name  = document.getElementById('shareFilename');
  if (!modal) return;
  form.action = `/file/${fileId}/share`;
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