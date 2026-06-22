// Drop zone
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileListPreview = document.getElementById('fileList');

if (dropZone) {
  ['dragenter','dragover'].forEach(e => {
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.add('dragover'); });
  });
  ['dragleave','drop'].forEach(e => {
    dropZone.addEventListener(e, ev => { ev.preventDefault(); dropZone.classList.remove('dragover'); });
  });
  dropZone.addEventListener('drop', ev => {
    fileInput.files = ev.dataTransfer.files;
    renderFileList(ev.dataTransfer.files);
  });
  fileInput.addEventListener('change', () => renderFileList(fileInput.files));
}

function renderFileList(files) {
  if (!fileListPreview) return;
  fileListPreview.innerHTML = '';
  Array.from(files).forEach(f => {
    const d = document.createElement('div');
    d.className = 'fp-item';
    d.textContent = `${f.name} (${formatBytes(f.size)})`;
    fileListPreview.appendChild(d);
  });
}

function formatBytes(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  if (b < 1073741824) return (b/1048576).toFixed(1) + ' MB';
  return (b/1073741824).toFixed(1) + ' GB';
}

// Share modal
function openShare(fileId, filename) {
  const modal = document.getElementById('shareModal');
  const form  = document.getElementById('shareForm');
  const name  = document.getElementById('shareFilename');
  if (!modal) return;
  form.action = `/file/${fileId}/share`;
  if (name) name.textContent = filename;
  modal.showModal();
}

// Copy link to clipboard
function copyLink(url) {
  navigator.clipboard.writeText(url).then(() => showToast('Link skopiowany do schowka!'));
}

// Toast
function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2800);
}

// Close modal on backdrop click
document.querySelectorAll('dialog.modal').forEach(d => {
  d.addEventListener('click', e => { if (e.target === d) d.close(); });
});

// Auto-dismiss alerts
setTimeout(() => {
  document.querySelectorAll('.alert').forEach(a => a.remove());
}, 5000);