/* Staff mobile scanner: native getUserMedia preview (always visible)
   + QR decode via BarcodeDetector, fallback to html5-qrcode scanFile. */
var stream = null, scanning = false, facing = 'environment';
var decodeTimer = null, detector = null, useNative = false, html5 = null, busy = false;
function dbg(m) { try { document.getElementById('debugLine').textContent = m; } catch (e) {} }
function setStatus(m, t) {
  document.getElementById('statusText').textContent = m;
  document.getElementById('statusBox').className = 'alert py-2 mb-2 alert-' + (t || 'info');
}
function stopTracks() {
  if (stream) { try { stream.getTracks().forEach(function (tr) { try { tr.stop(); } catch (e) {} }); } catch (e) {} stream = null; }
  var v = document.getElementById('nativePreview'); if (v) { try { v.srcObject = null; } catch (e) {} }
}
async function startScan() {
  if (scanning) return;
  document.getElementById('resultBox').classList.add('d-none');
  document.getElementById('secureState').textContent = window.isSecureContext ? 'YES' : 'NO';
  if (!window.isSecureContext) { setStatus('Camera needs HTTPS or localhost. Use HTTPS URL or Upload QR.', 'danger'); dbg('insecure: ' + location.href); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { setStatus('Camera not supported. Use Upload QR.', 'danger'); return; }
  try {
    setStatus('Requesting camera... tap Allow.', 'info'); dbg('asking facing=' + facing);
    stopTracks();
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } } }); }
    catch (e1) {
      dbg('ideal fail ' + (e1 && e1.name) + ', retry basic');
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: facing } }); }
      catch (e2) { dbg('basic fail, retry any'); stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: true }); }
    }
    var v = document.getElementById('nativePreview');
    v.srcObject = stream; v.muted = true;
    try { await v.play(); } catch (e) { dbg('play warn ' + e); }
    scanning = true;
    document.getElementById('startBtn').classList.add('d-none');
    setStatus('Camera LIVE. Hold QR inside green box.', 'success');
    dbg('live: ' + stream.getVideoTracks().map(function (t) { return t.label; }).join(','));
    try { var caps = stream.getVideoTracks()[0].getCapabilities(); if (caps && caps.torch) document.getElementById('torchBtn').classList.remove('d-none'); } catch (e) {}
    try { detector = ('BarcodeDetector' in window) ? new BarcodeDetector({ formats: ['qr_code'] }) : null; useNative = !!detector; } catch (e) { useNative = false; }
    if (decodeTimer) clearInterval(decodeTimer);
    decodeTimer = setInterval(decodeTick, 400);
  } catch (err) {
    scanning = false; stopTracks();
    document.getElementById('startBtn').classList.remove('d-none');
    var n = (err && err.name) || '';
    dbg('fail ' + n + ' ' + (err && err.message));
    if (n === 'NotAllowedError') setStatus('BLOCKED. Tap lock icon > allow camera, reload, Start.', 'danger');
    else if (n === 'NotFoundError' || n === 'OverconstrainedError') setStatus('No matching camera. Try Flip or Upload QR.', 'danger');
    else if (n === 'NotReadableError') setStatus('Camera busy. Close other app/tab, reload.', 'danger');
    else setStatus('Cannot start (' + (n || 'error') + '). Use Upload QR.', 'danger');
  }
}
async function stopScan() {
  if (decodeTimer) { clearInterval(decodeTimer); decodeTimer = null; }
  stopTracks(); scanning = false;
  document.getElementById('torchBtn').classList.add('d-none');
  document.getElementById('startBtn').classList.remove('d-none');
  setStatus('Stopped. Tap Start Camera to scan again.', 'secondary');
}
async function decodeTick() {
  if (!scanning || busy) return;
  var v = document.getElementById('nativePreview');
  if (!v || !v.videoWidth) return;
  busy = true;
  try {
    if (useNative && detector) {
      var codes = await detector.detect(v);
      if (codes && codes.length && codes[0].rawValue) { await onOK(codes[0].rawValue); return; }
    } else if (typeof Html5Qrcode !== 'undefined') {
      if (!html5) html5 = new Html5Qrcode('qrTmp', { verbose: false });
      var c = document.createElement('canvas');
      var w = v.videoWidth, h = v.videoHeight, s = Math.floor(Math.min(w, h) * 0.7);
      c.width = s; c.height = s;
      c.getContext('2d').drawImage(v, (w - s) / 2, (h - s) / 2, s, s, 0, 0, s, s);
      var blob = await (await fetch(c.toDataURL('image/png'))).blob();
      try { var t = await html5.scanFile(blob, true); if (t) { await onOK(t); return; } } catch (e) {}
    }
  } catch (e) {}
  busy = false;
}
async function onOK(t) {
  var id = (t || '').trim(); if (!id) { busy = false; return; }
  if (navigator.vibrate) { try { navigator.vibrate(80); } catch (e) {} }
  await stopScan(); verifyPass(id);
}
document.getElementById('torchBtn').addEventListener('click', async function () {
  try { var tr = stream.getVideoTracks()[0]; var on = this.dataset.on !== '1'; this.dataset.on = on ? '1' : '0'; await tr.applyConstraints({ advanced: [{ torch: on }] }); }
  catch (e) { setStatus('Torch not supported.', 'warning'); }
});
document.getElementById('flipBtn').addEventListener('click', async function () {
  facing = (facing === 'environment') ? 'user' : 'environment';
  if (decodeTimer) { clearInterval(decodeTimer); decodeTimer = null; }
  stopTracks(); scanning = false; busy = false;
  document.getElementById('startBtn').classList.remove('d-none');
  startScan();
});
document.getElementById('fileInput').addEventListener('change', async function (e) {
  var f = e.target.files && e.target.files[0]; if (!f) return;
  try {
    var tmp = new Html5Qrcode('qrTmp', { verbose: false });
    var id = await tmp.scanFile(f, true);
    try { await tmp.clear(); } catch (x) {}
    verifyPass(('' + (id || '')).trim());
  } catch (err) { setStatus('Cannot read QR from image.', 'danger'); }
  e.target.value = '';
});
function verifyManual() {
  var x = document.getElementById('manualId').value.trim();
  if (!x) { setStatus('Type pass ID first.', 'warning'); return; }
  verifyPass(x);
}
async function verifyPass(pid) {
  var box = document.getElementById('resultBox');
  box.classList.remove('d-none');
  box.innerHTML = '<div class="alert alert-info py-2">Verifying...</div>';
  try {
    var res = await window.KP.authFetch('/api/queue-pass/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pass_id: pid }) });
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      var m = data.message || 'Not eligible';
      if (res.status === 404) m = 'Invalid Queue Pass';
      else if (res.status === 403) m = 'Pass Belongs to Another Centre';
      else if (res.status === 409) { var st = data.smart_queue_pass && (data.smart_queue_pass.pass_status || data.smart_queue_pass.status); m = st === 'VERIFIED' ? 'Already Verified' : (st === 'CANCELLED' ? 'Cancelled' : (data.message || m)); }
      box.innerHTML = '<div class="alert alert-danger"><b>' + m + '</b><br><small>' + pid + '</small></div>';
      document.getElementById('startBtn').classList.remove('d-none');
      return;
    }
    var p = data.smart_queue_pass || {};
    var fn = (p.farmer && p.farmer.name) || '--', tk = (p.booking && p.booking.token_number) || '--';
    box.innerHTML = '<div class="card border-success"><div class="card-header bg-success text-white fw-bold">ENTRY VERIFIED</div><div class="card-body">Farmer: <b>' + fn + '</b><br>Token: <b>' + tk + '</b><br><span class="badge bg-success mt-2">' + (p.pass_status || p.status || 'VERIFIED') + '</span><div class="d-grid mt-3"><button class="btn btn-kp" onclick="startScan()">Scan Next</button></div></div></div>';
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (e) { box.innerHTML = '<div class="alert alert-danger">Network error.</div>'; document.getElementById('startBtn').classList.remove('d-none'); }
}
document.addEventListener('DOMContentLoaded', function () {
  var t = window.KP.getAuthToken();
  if (!t) { window.location.href = '/login?next=/staff/scan'; return; }
  document.getElementById('secureState').textContent = window.isSecureContext ? 'YES' : 'NO';
  document.addEventListener('visibilitychange', function () { if (document.hidden && scanning) stopScan(); });
});
