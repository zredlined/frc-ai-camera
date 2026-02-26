let isRecording = false;

async function getJSON(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

function setStatus(data) {
  const line = document.getElementById("statusLine");
  const badge = document.getElementById("recordBadge");
  const btn = document.getElementById("recordToggleBtn");

  isRecording = Boolean(data.recording);

  if (data.error) {
    line.textContent = `Error: ${data.error}`;
  } else if (!data.camera_connected) {
    line.textContent = "Camera disconnected";
  } else {
    const fps = data.measured_fps > 0 ? `${data.measured_fps} FPS` : "-- FPS";
    const rec = isRecording ? " • Recording" : "";
    line.textContent = `Camera OK • ${fps}${rec}`;
  }

  if (isRecording) {
    badge.textContent = "Recording";
    badge.classList.add("recording");
    btn.textContent = "Stop Recording";
    btn.classList.remove("primary");
    btn.classList.add("danger");
  } else {
    badge.textContent = "Idle";
    badge.classList.remove("recording");
    btn.textContent = "Start Recording";
    btn.classList.add("primary");
    btn.classList.remove("danger");
  }
}

function setClips(clips) {
  const list = document.getElementById("clips");
  list.innerHTML = "";
  if (clips.length === 0) {
    const li = document.createElement("li");
    li.className = "clip-item";
    li.textContent = "No clips yet.";
    list.appendChild(li);
    return;
  }

  for (const clip of clips) {
    const li = document.createElement("li");
    li.className = "clip-item";

    const top = document.createElement("div");
    top.className = "clip-top";

    const name = document.createElement("span");
    name.className = "clip-name";
    name.textContent = clip.name;

    const link = document.createElement("a");
    link.className = "download-link";
    link.textContent = "Download";
    link.href = clip.download_url;

    top.appendChild(name);
    top.appendChild(link);

    const meta = document.createElement("div");
    meta.className = "clip-meta";
    const mb = (clip.size_bytes / (1024 * 1024)).toFixed(2);
    const time = new Date(clip.modified_ts * 1000).toLocaleString();
    meta.textContent = `${mb} MB • ${time}`;

    li.appendChild(top);
    li.appendChild(meta);
    list.appendChild(li);
  }
}

async function refreshStatus() {
  try {
    const status = await getJSON("/api/status");
    setStatus(status);
  } catch (err) {
    setStatus({ error: String(err) });
  }
}

async function refreshClips() {
  try {
    const data = await getJSON("/api/clips");
    setClips(data.clips || []);
  } catch {
    setClips([]);
  }
}

async function toggleRecording() {
  const btn = document.getElementById("recordToggleBtn");
  btn.disabled = true;
  try {
    if (isRecording) {
      await getJSON("/api/stop", { method: "POST" });
    } else {
      const label = document.getElementById("label").value;
      await getJSON("/api/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      });
    }
  } catch (err) {
    alert(`Recording failed: ${err}`);
  } finally {
    btn.disabled = false;
    await refreshStatus();
    await refreshClips();
  }
}

async function uploadLogo() {
  const input = document.getElementById("logoInput");
  if (!input.files || input.files.length === 0) return;
  const form = new FormData();
  form.append("logo", input.files[0]);
  try {
    const res = await getJSON("/api/logo", { method: "POST", body: form });
    if (res.logo_url) {
      document.getElementById("teamLogo").src = `${res.logo_url}?t=${Date.now()}`;
    }
  } catch (err) {
    alert(`Logo upload failed: ${err}`);
  } finally {
    input.value = "";
  }
}

document.getElementById("recordToggleBtn").addEventListener("click", toggleRecording);
document.getElementById("logoInput").addEventListener("change", uploadLogo);

refreshStatus();
refreshClips();
setInterval(refreshStatus, 1000);
setInterval(refreshClips, 10000);
