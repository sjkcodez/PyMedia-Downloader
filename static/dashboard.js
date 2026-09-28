/* ============================================================
   PyMedia Downloader — dashboard logic
   ============================================================ */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // ---------- Quality + format options per kind ----------
  const QUALITIES = {
    video: [
      { value: "360p",  label: "360p" },
      { value: "480p",  label: "480p" },
      { value: "720p",  label: "720p (HD)" },
      { value: "1080p", label: "1080p (Full HD)" },
      { value: "2k",    label: "2K (1440p)" },
      { value: "4k",    label: "4K (2160p)" },
      { value: "best",  label: "Best available" },
    ],
    audio: [
      { value: "128", label: "128 kbps" },
      { value: "192", label: "192 kbps" },
      { value: "320", label: "320 kbps (best)" },
    ],
    image: [
      { value: "original", label: "Original size" },
      { value: "720p",     label: "Resize to 1280px" },
      { value: "1080p",    label: "Resize to 1920px" },
      { value: "2k",       label: "Resize to 2560px" },
      { value: "4k",       label: "Resize to 3840px" },
    ],
  };

  const FORMATS = {
    video: ["mp4", "webm", "mkv"],
    audio: ["mp3", "m4a", "wav", "flac"],
    image: ["", "jpg", "png", "webp"],
  };

  function fillOptions(qualitySelect, formatSelect, kind) {
    const qs = QUALITIES[kind] || [];
    const fs = FORMATS[kind] || [];

    qualitySelect.innerHTML = qs.map(q =>
      `<option value="${q.value}">${q.label}</option>`
    ).join("");

    formatSelect.innerHTML = fs.map(f => {
      if (!f) return `<option value="">Keep original</option>`;
      return `<option value="${f}">${f.toUpperCase()}</option>`;
    }).join("");

    if (kind === "video") qualitySelect.value = "1080p";
    if (kind === "audio") qualitySelect.value = "192";
    if (kind === "image") qualitySelect.value = "original";
  }

  // ---------- Tab switching ----------
  const tabs = document.querySelectorAll(".tab");
  const panels = { single: $("panel-single"), batch: $("panel-batch") };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      Object.values(panels).forEach(p => p && p.classList.add("hidden"));
      panels[tab.dataset.tab]?.classList.remove("hidden");
    });
  });

  // ---------- Kind switching (single) ----------
  const kindGroup = $("kind-group");
  let currentKind = "video";

  kindGroup.querySelectorAll(".seg").forEach((btn) => {
    btn.addEventListener("click", () => {
      kindGroup.querySelectorAll(".seg").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentKind = btn.dataset.kind;
      fillOptions($("quality-select"), $("format-select"), currentKind);
    });
  });

  fillOptions($("quality-select"), $("format-select"), currentKind);

  // ---------- Kind switching (batch) ----------
  const batchKindGroup = $("batch-kind-group");
  let currentBatchKind = "video";

  batchKindGroup.querySelectorAll(".seg").forEach((btn) => {
    btn.addEventListener("click", () => {
      batchKindGroup.querySelectorAll(".seg").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentBatchKind = btn.dataset.kind;
      fillOptions($("batch-quality-select"), $("batch-format-select"), currentBatchKind);
    });
  });

  fillOptions($("batch-quality-select"), $("batch-format-select"), currentBatchKind);

  // ---------- Analyze single ----------
  const analyzeBtn = $("analyze-btn");
  const singleUrl = $("single-url");
  const previewEl = $("preview");
  const optionsEl = $("options");
  const downloadBtn = $("download-btn");

  analyzeBtn.addEventListener("click", async () => {
    const url = singleUrl.value.trim();
    if (!url) return;
    if (!url.startsWith("http")) {
      alert("Please enter a valid URL starting with http:// or https://");
      return;
    }

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Analyzing…";

    try {
      // Detect image URL client-side as a shortcut
      const isImage = /\.(jpg|jpeg|png|gif|webp|bmp|tiff|svg|avif|heic|heif)(\?|$)/i.test(url);

      if (isImage) {
        $("preview-thumb").src = url;
        $("preview-thumb").style.display = "block";
        $("preview-title").textContent = url.split("/").pop() || "Image";
        $("preview-meta").textContent = "Direct image URL";
        $("preview-source").textContent = "Image";
        previewEl.classList.remove("hidden");
        optionsEl.classList.remove("hidden");

        // Switch to image mode
        kindGroup.querySelectorAll(".seg").forEach(b => {
          b.classList.toggle("active", b.dataset.kind === "image");
        });
        currentKind = "image";
        fillOptions($("quality-select"), $("format-select"), "image");
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = "Analyze";
        return;
      }

      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();

      if (!data.ok) throw new Error(data.error || "Analysis failed");

      const info = data.info;
      $("preview-thumb").src = info.thumbnail || "";
      $("preview-thumb").style.display = info.thumbnail ? "block" : "none";
      $("preview-title").textContent = info.title || "Untitled";
      $("preview-meta").textContent = [
        info.channel,
        info.duration_str,
        info.extractor,
      ].filter(Boolean).join(" · ");
      $("preview-source").textContent = info.is_playlist
        ? `Playlist (${info.playlist_count} items)`
        : "Single";

      previewEl.classList.remove("hidden");
      optionsEl.classList.remove("hidden");

    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = "Analyze";
    }
  });

  // ---------- Download single ----------
  downloadBtn.addEventListener("click", async () => {
    const url = singleUrl.value.trim();
    if (!url) return;

    const payload = {
      urls: [url],
      kind: currentKind,
      quality: $("quality-select").value,
      format: $("format-select").value,
    };

    downloadBtn.disabled = true;
    downloadBtn.textContent = "Starting…";

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Failed to start download");

      // Watch the new job
      data.jobs.forEach(j => watchJob(j.id));
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      downloadBtn.disabled = false;
      downloadBtn.textContent = "⬇ Download";
    }
  });

  // ---------- Batch download ----------
  const batchBtn = $("batch-download-btn");

  batchBtn.addEventListener("click", async () => {
    const raw = $("batch-urls").value;
    const urls = raw.split("\n")
      .map(s => s.trim())
      .filter(s => s.startsWith("http://") || s.startsWith("https://"));

    if (!urls.length) {
      alert("Paste at least one valid URL.");
      return;
    }

    const payload = {
      urls,
      kind: currentBatchKind,
      quality: $("batch-quality-select").value,
      format: $("batch-format-select").value,
    };

    batchBtn.disabled = true;
    batchBtn.textContent = "Adding…";

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Failed to queue downloads");

      data.jobs.forEach(j => watchJob(j.id));
      $("batch-urls").value = "";
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      batchBtn.disabled = false;
      batchBtn.textContent = "⬇ Add all to queue";
    }
  });

  // ---------- Live job tracking ----------
  const jobsList = $("jobs-list");
  const activeJobs = new Map();

  function ensureJobsContainer() {
    const emptyMsg = jobsList.querySelector(".empty");
    if (emptyMsg) emptyMsg.remove();
  }

  function renderJob(job) {
    let card = document.getElementById("job-" + job.id);
    if (!card) {
      card = document.createElement("div");
      card.className = "job-card";
      card.id = "job-" + job.id;
      card.innerHTML = `
        <div class="job-body">
          <div class="job-title" data-role="title">—</div>
          <div class="job-meta" data-role="meta">—</div>
          <div class="job-bar"><div class="job-fill" data-role="fill"></div></div>
          <div class="job-status">
            <span data-role="state">Queued</span>
            <span class="speed" data-role="speed"></span>
          </div>
        </div>
        <div class="job-actions" data-role="actions"></div>
      `;
      jobsList.prepend(card);
      ensureJobsContainer();
    }

    const titleEl = card.querySelector('[data-role="title"]');
    const metaEl  = card.querySelector('[data-role="meta"]');
    const fillEl  = card.querySelector('[data-role="fill"]');
    const stateEl = card.querySelector('[data-role="state"]');
    const speedEl = card.querySelector('[data-role="speed"]');
    const actions = card.querySelector('[data-role="actions"]');

    titleEl.textContent = job.title || job.url;
    metaEl.textContent = `${job.kind} · ${job.format || "auto"} · ${job.quality || ""}`;
    fillEl.style.width = (job.percent || 0) + "%";

    const labels = {
      queued:       "Queued",
      analyzing:    "Analyzing…",
      downloading:  `Downloading — ${job.percent || 0}%`,
      processing:   "Processing…",
      done:         "✓ Done",
      error:        "✕ Error",
    };
    stateEl.textContent = labels[job.status] || job.status;
    speedEl.textContent = job.speed || "";

    card.classList.toggle("done", job.status === "done");
    card.classList.toggle("error", job.status === "error");

    if (job.status === "done" && job.file_path) {
      const url = "/download?path=" + encodeURIComponent(job.file_path);
      actions.innerHTML = `<a class="btn btn-small btn-amber" href="${url}">Save</a>`;
    } else if (job.status === "error") {
      actions.innerHTML = `<button class="btn btn-small btn-danger-soft" onclick="this.closest('.job-card').remove()">Dismiss</button>`;
    } else {
      actions.innerHTML = "";
    }
  }

  async function pollJob(id) {
    try {
      const res = await fetch("/api/job/" + id);
      if (!res.ok) return null;
      return await res.json();
    } catch { return null; }
  }

  function watchJob(id) {
    if (activeJobs.has(id)) return;

    const tick = async () => {
      const job = await pollJob(id);
      if (!job) return;
      renderJob(job);

      if (job.status === "done" || job.status === "error") {
        activeJobs.delete(id);
        return;
      }
      activeJobs.set(id, setTimeout(tick, 1000));
    };
    activeJobs.set(id, setTimeout(tick, 400));
  }

  // ---------- Restore recent jobs on load ----------
  (async function resumeJobs() {
    try {
      const res = await fetch("/api/jobs");
      const data = await res.json();
      (data.jobs || []).slice(0, 20).forEach((job) => {
        renderJob(job);
        if (["queued", "analyzing", "downloading", "processing"].includes(job.status)) {
          watchJob(job.id);
        }
      });
    } catch {}
  })();

})();
