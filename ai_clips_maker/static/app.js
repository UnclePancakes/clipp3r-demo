const sourceTabs = [...document.querySelectorAll(".source-tab")];
const urlPanel = document.getElementById("url-panel");
const filePanel = document.getElementById("file-panel");
const sourceUrl = document.getElementById("source-url");
const sourceFile = document.getElementById("source-file");
const dropzone = document.getElementById("dropzone");
const createButton = document.getElementById("create-button");
const clipLimit = document.getElementById("clip-limit");
const faceTracking = document.getElementById("face-tracking");
const outputMode = document.getElementById("output-mode");
const captionStyle = document.getElementById("caption-style");
const transcriptionLanguage = document.getElementById("transcription-language");
const selectAllClips = document.getElementById("select-all-clips");
const suggestSelected = document.getElementById("suggest-selected");
const metadataMessage = document.getElementById("metadata-message");
const jobPanel = document.getElementById("job-panel");
const results = document.getElementById("results");
const candidateReview = document.getElementById("candidate-review");
const sourcePreview = document.getElementById("source-preview");
const candidateList = document.getElementById("candidate-list");
const candidateTimeline = document.getElementById("candidate-timeline");
const sourceScrubber = document.getElementById("source-scrubber");
const renderSelectedButton = document.getElementById("render-selected");
const candidateSearch = document.getElementById("candidate-search");
const candidateSort = document.getElementById("candidate-sort");
const SAVED_JOB_KEY = "clipp3r.activeJobId";
let sourceMode = "url";
let activeJobId = null;
let pollTimer = null;
let candidateReviewJobId = null;
let candidatesForReview = [];
let sourceDuration = 1;
let previewEndTime = null;

sourceTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    sourceMode = tab.dataset.mode;
    sourceTabs.forEach((item) => {
      const selected = item === tab;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-selected", String(selected));
    });
    urlPanel.classList.toggle("hidden", sourceMode !== "url");
    filePanel.classList.toggle("hidden", sourceMode !== "file");
  });
});

dropzone.addEventListener("click", () => sourceFile.click());
sourceFile.addEventListener("change", () => showSelectedFile(sourceFile.files[0]));
clipLimit.addEventListener("change", () => {
  document.getElementById("clip-limit-label").textContent =
    clipLimit.value === "0" ? "ALL GOOD PICKS" : `UP TO ${clipLimit.value}`;
});
outputMode.addEventListener("change", updateOutputMode);
selectAllClips.addEventListener("change", () => {
  document.querySelectorAll(".clip-select").forEach((input) => {
    input.checked = selectAllClips.checked;
  });
  updateSelectedClipCount();
});
suggestSelected.addEventListener("click", suggestSelectedClips);
document.getElementById("select-all-candidates").addEventListener("click", () => {
  setCandidateSelection(true);
});
document.getElementById("clear-candidates").addEventListener("click", () => {
  setCandidateSelection(false);
});
document.getElementById("select-top-10").addEventListener("click", () => {
  selectTopCandidates(10);
});
document.getElementById("select-top-25").addEventListener("click", () => {
  selectTopCandidates(25);
});
candidateSearch.addEventListener("input", updateCandidateListView);
candidateSort.addEventListener("change", updateCandidateListView);
renderSelectedButton.addEventListener("click", renderSelectedCandidates);
sourcePreview.addEventListener("loadedmetadata", () => {
  if (Number.isFinite(sourcePreview.duration) && sourcePreview.duration > 0) {
    sourceDuration = sourcePreview.duration;
  }
  updateCandidateTimeline();
});
sourcePreview.addEventListener("timeupdate", () => {
  sourceScrubber.value = String(sourcePreview.currentTime || 0);
  document.getElementById("timeline-current-time").textContent =
    formatTimelineTime(sourcePreview.currentTime || 0);
  updateActiveCandidateMarker();
  if (previewEndTime !== null && sourcePreview.currentTime >= previewEndTime) {
    sourcePreview.pause();
    previewEndTime = null;
  }
});
sourceScrubber.addEventListener("input", () => {
  previewEndTime = null;
  sourcePreview.currentTime = Number(sourceScrubber.value);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  });
});
dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  sourceFile.files = transfer.files;
  showSelectedFile(file);
});

sourceUrl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") startJob();
});
createButton.addEventListener("click", startJob);

function showSelectedFile(file) {
  document.getElementById("drop-title").innerHTML = file
    ? escapeHtml(file.name)
    : 'Drop a video here or <u>browse files</u>';
  document.getElementById("drop-meta").textContent = file
    ? `${formatBytes(file.size)} · ready to upload`
    : "MP4, MOV, MKV, WebM · up to 20 GB";
}

function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = value;
  return node.innerHTML;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

function showError(message) {
  const error = document.getElementById("job-error");
  error.textContent = message;
  error.classList.remove("hidden");
  jobPanel.classList.remove("hidden");
  document.getElementById("job-spinner").classList.add("done");
  document.getElementById("job-spinner").textContent = "!";
  document.getElementById("job-stage").textContent = "NEEDS ATTENTION";
  document.getElementById("job-title").textContent = "We couldn't finish that job";
}

async function startJob() {
  if (createButton.disabled) return;
  const payload = {
    max_clips: Number(clipLimit.value),
    face_tracking: faceTracking.checked,
    output_mode: outputMode.value,
    caption_style: captionStyle.value,
    language: transcriptionLanguage.value,
    streamer_tag: document.getElementById("streamer-tag").value.trim(),
    streamer_platform: document.getElementById("streamer-platform").value,
    creator_context: getSourceContext(),
  };
  let request;

  if (sourceMode === "url") {
    payload.url = sourceUrl.value.trim();
    if (!payload.url) {
      sourceUrl.focus();
      return showError("Paste a public video URL to get started.");
    }
    try {
      const parsed = new URL(payload.url);
      if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error("Choose a complete public video link beginning with http:// or https://.");
      }
    } catch (error) {
      return showError(error.message || "Enter a valid public video URL.");
    }
    request = submitUrl(payload);
  } else {
    const file = sourceFile.files[0];
    if (!file) return showError("Choose a video file to get started.");
    if (file.size > 20 * 1024 ** 3) {
      return showError("This upload is over CLIPP3R's 20 GB limit.");
    }
    request = uploadFile(file, payload);
  }

  clearPreviousResult();
  createButton.disabled = true;
  createButton.querySelector("span").textContent =
    sourceMode === "file" ? "UPLOADING…" : "STARTING…";
  jobPanel.classList.remove("hidden");
  jobPanel.scrollIntoView({ behavior: "smooth", block: "center" });
  try {
    const data = await request;
    activeJobId = data.job_id;
    localStorage.setItem(SAVED_JOB_KEY, activeJobId);
    createButton.querySelector("span").textContent = "ANALYZING…";
    pollJob();
  } catch (error) {
    showError(error.message || "Could not start this clip job.");
    resetCreateButton();
  }
}

function submitUrl(payload) {
  return fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(readResponse);
}

function getSourceContext() {
  return {
    audience: document.getElementById("context-audience").value.trim(),
    topic: document.getElementById("context-topic").value.trim(),
    goal: document.getElementById("context-goal").value.trim(),
    tone: document.getElementById("context-tone").value.trim(),
  };
}

function uploadFile(file, payload) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    form.append("max_clips", String(payload.max_clips));
    form.append("face_tracking", String(payload.face_tracking));
    form.append("output_mode", payload.output_mode);
    form.append("caption_style", payload.caption_style);
    form.append("language", payload.language);
    form.append("streamer_tag", payload.streamer_tag);
    form.append("streamer_platform", payload.streamer_platform);
    Object.entries(payload.creator_context).forEach(([key, value]) => {
      form.append(`context_${key}`, value);
    });
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const progress = Math.round(10 * event.loaded / event.total);
      setProgress(progress, "Uploading your video…");
      document.getElementById("job-stage").textContent = "UPLOADING SOURCE";
      document.getElementById("job-title").textContent = file.name;
    });
    xhr.addEventListener("load", () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        return reject(new Error("The local server returned an unreadable response."));
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        return reject(new Error(data.error || `Upload failed (${xhr.status}).`));
      }
      setProgress(11, "Upload complete. CLIPP3R is transcribing the source and finding candidate moments.");
      document.getElementById("job-stage").textContent = "SOURCE UPLOADED";
      document.getElementById("job-title").textContent = "Finding all ranked clips";
      resolve(data);
    });
    xhr.addEventListener("error", () => reject(new Error(
      "The upload connection was interrupted. If the bar reached 10%, the source may already be uploaded and processing; check the CLIPP3R job folder before retrying to avoid uploading another copy."
    )));
    xhr.addEventListener("abort", () => reject(new Error("The upload was cancelled.")));
    xhr.send(form);
  });
}

async function readResponse(response) {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

async function pollJob() {
  if (!activeJobId) return;
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(activeJobId)}`);
    const job = await readResponse(response);
    updateJob(job);
    if (job.status === "ready") {
      localStorage.removeItem(SAVED_JOB_KEY);
      renderClips(job);
      resetCreateButton();
      return;
    }
    if (job.status === "awaiting_selection") {
      renderCandidateReview(job);
      return;
    }
    if (job.status === "error") {
      localStorage.removeItem(SAVED_JOB_KEY);
      showError(job.error || job.message);
      resetCreateButton();
      return;
    }
    createButton.disabled = true;
    createButton.querySelector("span").textContent =
      job.stage === "rendering" ? "RENDERING ALL CLIPS…" : "ANALYZING VIDEO…";
    pollTimer = window.setTimeout(pollJob, 1400);
  } catch (error) {
    showError(error.message || "Could not read job status.");
    resetCreateButton();
  }
}

function updateJob(job) {
  jobPanel.classList.remove("hidden");
  if (job.status === "processing" || job.status === "downloading") {
    document.getElementById("job-spinner").classList.remove("done");
    document.getElementById("job-spinner").textContent = "";
  }
  document.getElementById("job-stage").textContent = job.stage.replaceAll("_", " ").toUpperCase();
  document.getElementById("job-title").textContent = job.source_name || "Getting your clips ready";
  document.getElementById("job-message").textContent = job.message;
  document.getElementById("job-count").textContent =
    job.clip_total ? `${job.clip_done || 0} / ${job.clip_total} CLIPS` : "";
  setProgress(job.progress, job.message);
  document.getElementById("job-error").classList.add("hidden");
}

function setProgress(value, message) {
  const progress = Math.max(0, Math.min(100, Number(value) || 0));
  document.getElementById("progress-bar").style.width = `${progress}%`;
  document.getElementById("job-percent").textContent = `${progress}%`;
  if (message) document.getElementById("job-message").textContent = message;
}

function renderClips(job) {
  candidateReview.classList.add("hidden");
  candidateReviewJobId = null;
  sourcePreview.pause();
  document.getElementById("job-spinner").classList.add("done");
  document.getElementById("job-spinner").textContent = "✓";
  document.getElementById("job-stage").textContent = "ALL SET";
  document.getElementById("job-title").textContent = `${job.clips.length} clips, ready for your review`;
  document.getElementById("job-message").textContent = job.message;
  document.querySelector(".results-heading h2").textContent = "Your clip picks";
  document.getElementById("results-subtitle").textContent =
    `${job.clips.length} clips rendered. Watch first, add or edit headlines, then suggest titles before downloading.`;
  const grid = document.getElementById("clip-grid");
  grid.replaceChildren();
  job.clips.forEach((clip, index) => {
    grid.append(makeClipCard(job.id, clip, index, clip.creator_context || job.creator_context || {}, job.output_dir));
  });
  selectAllClips.checked = false;
  updateSelectedClipCount();
  const downloadAll = document.getElementById("download-all");
  downloadAll.href = job.download_url;
  downloadAll.classList.toggle("hidden", !job.download_url);
  results.classList.remove("hidden");
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderCandidateReview(job) {
  createButton.disabled = true;
  createButton.querySelector("span").textContent = "CANDIDATES READY";
  candidateReview.classList.remove("hidden");
  results.classList.add("hidden");
  document.getElementById("candidate-review-summary").textContent =
    `Found ${job.clips.length} candidate moments. Preview the source, then choose which moments to render. Transcript-based picks can miss visual-only events; use the timeline to find them.`;
  if (candidateReviewJobId === job.id) return;

  candidateReviewJobId = job.id;
  candidatesForReview = job.clips;
  sourceDuration = Math.max(1, Number(job.source_duration) || 1);
  sourcePreview.src = `/api/jobs/${encodeURIComponent(job.id)}/source`;
  sourcePreview.load();
  sourceScrubber.max = String(sourceDuration);
  document.getElementById("timeline-duration").textContent =
    formatTimelineTime(sourceDuration);
  candidateList.replaceChildren();
  candidateTimeline.replaceChildren();
  candidateSearch.value = "";
  candidateSort.value = "time";

  candidatesForReview.forEach((clip, index) => {
    const option = document.createElement("article");
    option.className = "candidate-option";
    option.dataset.clipName = clip.name;
    const pick = document.createElement("label");
    pick.className = "candidate-pick";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "candidate-checkbox";
    checkbox.dataset.clipName = clip.name;
    checkbox.checked = true;
    checkbox.addEventListener("change", updateCandidateSelection);
    checkbox.setAttribute("aria-label", `Select candidate ${index + 1}`);
    const number = document.createElement("strong");
    number.textContent = `#${String(index + 1).padStart(3, "0")}`;
    const description = document.createElement("span");
    description.className = "candidate-snippet";
    description.textContent =
      `${formatTimelineTime(clip.start)} · ${clip.duration.toFixed(1)} sec · ${clip.text || "Transcript unavailable"}`;
    description.title = clip.text || "Transcript unavailable";
    const score = document.createElement("em");
    score.textContent = `${clip.score}/100`;
    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "candidate-preview";
    previewButton.textContent = "PREVIEW";
    previewButton.setAttribute("aria-label", `Preview candidate ${index + 1}`);
    previewButton.addEventListener("click", () => previewCandidate(clip));
    pick.append(checkbox, number, description);
    option.append(pick, score, previewButton);
    candidateList.append(option);

    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = "timeline-marker selected";
    marker.dataset.clipName = clip.name;
    marker.style.left = `${Math.max(0, clip.start / sourceDuration * 100)}%`;
    marker.style.width = `${Math.max(0.35, clip.duration / sourceDuration * 100)}%`;
    marker.title =
      `${formatTimelineTime(clip.start)}–${formatTimelineTime(clip.end)} · score ${clip.score}: ${clip.text || "Transcript unavailable"}`;
    marker.setAttribute("aria-label", `Preview candidate ${index + 1} at ${formatTimelineTime(clip.start)}`);
    marker.setAttribute("aria-pressed", "false");
    marker.addEventListener("click", () => previewCandidate(clip));
    candidateTimeline.append(marker);
  });
  sourcePreview.currentTime = 0;
  updateCandidateTimeline();
  updateCandidateListView();
  updateCandidateSelection();
  candidateReview.scrollIntoView({ behavior: "smooth", block: "start" });
}

function previewCandidate(clip) {
  previewEndTime = Number(clip.end);
  sourcePreview.currentTime = Number(clip.start);
  sourcePreview.play().catch(() => {
    document.getElementById("candidate-review-summary").textContent =
      "Preview playback did not start. Use the source player controls to try again.";
  });
  updateActiveCandidateMarker();
}

function updateActiveCandidateMarker() {
  const currentTime = Number(sourcePreview.currentTime) || 0;
  const active = candidatesForReview
    .filter((clip) => currentTime >= Number(clip.start) && currentTime <= Number(clip.end))
    .sort((left, right) => Number(right.start) - Number(left.start))[0];
  candidateTimeline.querySelectorAll(".timeline-marker").forEach((marker) => {
    const isActive = Boolean(active && marker.dataset.clipName === active.name);
    marker.classList.toggle("active", isActive);
    if (isActive) marker.setAttribute("aria-current", "time");
    else marker.removeAttribute("aria-current");
  });
}

function updateCandidateTimeline() {
  if (!candidatesForReview.length) return;
  const duration = Math.max(1, sourceDuration);
  sourceScrubber.max = String(duration);
  document.getElementById("timeline-duration").textContent =
    formatTimelineTime(duration);
  candidateTimeline.querySelectorAll(".timeline-marker").forEach((marker) => {
    const clip = candidatesForReview.find((item) => item.name === marker.dataset.clipName);
    if (!clip) return;
    marker.style.left = `${Math.max(0, clip.start / duration * 100)}%`;
    marker.style.width = `${Math.max(0.35, clip.duration / duration * 100)}%`;
  });
}

function updateCandidateSelection() {
  const selected = new Set(
    [...candidateList.querySelectorAll(".candidate-checkbox:checked")]
      .map((input) => input.dataset.clipName),
  );
  candidateTimeline.querySelectorAll(".timeline-marker").forEach((marker) => {
    marker.classList.toggle("selected", selected.has(marker.dataset.clipName));
    marker.setAttribute("aria-pressed", String(selected.has(marker.dataset.clipName)));
  });
  const selectedDuration = candidatesForReview
    .filter((clip) => selected.has(clip.name))
    .reduce((total, clip) => total + Math.max(0, Number(clip.duration) || 0), 0);
  const visibleCount = candidateList.querySelectorAll(".candidate-option:not(.filtered-out)").length;
  document.getElementById("candidate-selection-count").textContent =
    `${selected.size} of ${candidatesForReview.length} selected · ${formatTimelineTime(selectedDuration)} total · ${visibleCount} shown`;
  renderSelectedButton.disabled = selected.size === 0;
  renderSelectedButton.textContent = selected.size
    ? `RENDER ${selected.size} CLIPS · ${formatTimelineTime(selectedDuration)}`
    : "SELECT CLIPS TO RENDER";
  document.getElementById("select-all-candidates").disabled =
    selected.size === candidatesForReview.length;
  document.getElementById("clear-candidates").disabled = selected.size === 0;
  document.getElementById("select-top-10").disabled =
    candidatesForReview.length === 0 || (selected.size === Math.min(10, candidatesForReview.length) &&
      candidatesForReview.slice().sort((a, b) => Number(b.score) - Number(a.score))
        .slice(0, 10).every((clip) => selected.has(clip.name)));
  document.getElementById("select-top-25").disabled =
    candidatesForReview.length === 0 || (selected.size === Math.min(25, candidatesForReview.length) &&
      candidatesForReview.slice().sort((a, b) => Number(b.score) - Number(a.score))
        .slice(0, 25).every((clip) => selected.has(clip.name)));
}

function setCandidateSelection(checked) {
  candidateList.querySelectorAll(".candidate-checkbox").forEach((input) => {
    input.checked = checked;
  });
  updateCandidateSelection();
}

function selectTopCandidates(limit) {
  const selectedNames = new Set(
    candidatesForReview
      .slice()
      .sort((left, right) => Number(right.score) - Number(left.score))
      .slice(0, limit)
      .map((clip) => clip.name),
  );
  candidateList.querySelectorAll(".candidate-checkbox").forEach((input) => {
    input.checked = selectedNames.has(input.dataset.clipName);
  });
  updateCandidateSelection();
}

function updateCandidateListView() {
  const query = candidateSearch.value.trim().toLocaleLowerCase();
  const sorted = candidatesForReview.slice().sort((left, right) => {
    if (candidateSort.value === "score") {
      return Number(right.score) - Number(left.score) || Number(left.start) - Number(right.start);
    }
    return Number(left.start) - Number(right.start);
  });
  sorted.forEach((clip) => {
    const option = [...candidateList.querySelectorAll(".candidate-option")]
      .find((item) => item.dataset.clipName === clip.name);
    if (option) candidateList.append(option);
  });
  candidateList.querySelectorAll(".candidate-option").forEach((option) => {
    const clip = candidatesForReview.find((item) => item.name === option.dataset.clipName);
    const haystack = `${clip?.text || ""} ${clip?.name || ""}`.toLocaleLowerCase();
    option.classList.toggle("filtered-out", Boolean(query) && !haystack.includes(query));
    const marker = [...candidateTimeline.querySelectorAll(".timeline-marker")]
      .find((item) => item.dataset.clipName === option.dataset.clipName);
    if (marker) marker.classList.toggle("filtered-out", Boolean(query) && !haystack.includes(query));
  });
  updateCandidateSelection();
}

async function renderSelectedCandidates() {
  const clipNames = [...candidateList.querySelectorAll(".candidate-checkbox:checked")]
    .map((input) => input.dataset.clipName);
  if (!activeJobId || !clipNames.length) return;
  renderSelectedButton.disabled = true;
  renderSelectedButton.textContent = "STARTING RENDER…";
  try {
    await readResponse(await fetch(
      `/api/jobs/${encodeURIComponent(activeJobId)}/render`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clip_names: clipNames }),
      },
    ));
    candidateReview.classList.add("hidden");
    pollJob();
  } catch (error) {
    document.getElementById("candidate-review-summary").textContent =
      error.message || "Could not start rendering the selected clips.";
    updateCandidateSelection();
  }
}

function formatTimelineTime(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${remainder}`
    : `${minutes}:${remainder}`;
}

function makeClipCard(jobId, clip, index, creatorContext, outputDir) {
  const card = document.createElement("article");
  card.className = "clip-card";

  const video = document.createElement("video");
  video.controls = true;
  video.preload = "metadata";
  video.playsInline = true;
  video.src = `/api/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(clip.name)}`;
  video.setAttribute("aria-label", `Preview ${clip.name}`);

  const info = document.createElement("div");
  info.className = "clip-info";

  const topline = document.createElement("div");
  topline.className = "clip-topline";
  const number = document.createElement("span");
  number.textContent = `CLIP ${String(index + 1).padStart(2, "0")} · ${formatTime(clip.start)}`;
  const selectLabel = document.createElement("label");
  selectLabel.className = "clip-select-row";
  const select = document.createElement("input");
  select.className = "clip-select";
  select.type = "checkbox";
  select.setAttribute("aria-label", `Select clip ${index + 1} for title suggestions`);
  select.addEventListener("change", updateSelectedClipCount);
  selectLabel.append(select, document.createTextNode("SELECT"));
  const score = document.createElement("span");
  score.className = "score-chip";
  score.textContent = `${clip.score} / 100`;
  score.title = "Relative editing-priority score based on transcript signals";
  topline.append(number, selectLabel, score);

  const snippet = document.createElement("p");
  snippet.className = "clip-snippet";
  snippet.textContent = clip.text || "Captioned highlight";

  const selectedTitle = document.createElement("p");
  selectedTitle.className = "clip-title";
  selectedTitle.textContent = clip.title || "";
  selectedTitle.classList.toggle("hidden", !clip.title);

  const contextEditor = makeClipContextEditor(creatorContext);
  const headlineEditor = makeHeadlineEditor(card, jobId, clip);
  const actions = document.createElement("div");
  actions.className = "clip-actions";
  const download = document.createElement("a");
  download.href = `/api/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(clip.name)}?download=1`;
  download.textContent = "SAVE CLIP ↗";
  const fileLocation = document.createElement("small");
  fileLocation.className = "clip-file-location";
  fileLocation.textContent = `Saved in ${outputDir || "C:\\Users\\User pc\\Desktop\\YouTube\\CLIPS"}`;
  const duration = document.createElement("span");
  duration.textContent = `${clip.duration.toFixed(1)} SEC`;
  actions.append(download, duration);
  info.append(
    topline,
    selectedTitle,
    snippet,
    headlineEditor,
    contextEditor,
    actions,
    fileLocation,
  );
  card.append(video, info);
  card.dataset.clipName = clip.name;
  if (clip.suggestions) {
    renderSuggestionPanel(card, jobId, clip, clip.suggestions);
  }
  return card;
}

function makeHeadlineEditor(card, jobId, clip) {
  const details = document.createElement("details");
  details.className = "clip-headline-editor";
  const summary = document.createElement("summary");
  summary.textContent = clip.hook
    ? "Edit on-screen headline"
    : "Add an on-screen headline after watching";
  details.append(summary);

  const label = document.createElement("label");
  label.textContent = "HEADLINE · OPTIONAL · UP TO 100 CHARACTERS";
  const input = document.createElement("textarea");
  input.className = "clip-hook-input";
  input.maxLength = 100;
  input.value = clip.hook || "";
  input.setAttribute("aria-label", `On-screen headline for ${clip.name}`);

  const save = document.createElement("button");
  save.className = "headline-save";
  save.type = "button";
  save.textContent = clip.hook ? "UPDATE HEADLINE" : "APPLY HEADLINE";
  const status = document.createElement("p");
  status.className = "headline-status hidden";
  status.setAttribute("role", "status");
  save.addEventListener("click", async () => {
    save.disabled = true;
    status.textContent = "Updating the video and download bundle…";
    status.classList.remove("hidden");
    try {
      const data = await readResponse(await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(card.dataset.clipName)}/headline`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ headline: input.value }),
        },
      ));
      clip.hook = data.headline;
      summary.textContent = data.headline
        ? "Edit on-screen headline"
        : "Add an on-screen headline after watching";
      save.textContent = data.headline ? "UPDATE HEADLINE" : "APPLY HEADLINE";
      const video = card.querySelector("video");
      video.src = `/api/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(data.name)}?v=${Date.now()}`;
      status.textContent = data.headline
        ? "Headline updated in the preview and download bundle."
        : "Headline removed from the preview and download bundle.";
    } catch (error) {
      status.textContent = error.message || "Could not update this headline.";
    } finally {
      save.disabled = false;
    }
  });
  details.append(label, input, save, status);
  return details;
}

function makeClipContextEditor(initialContext) {
  const details = document.createElement("details");
  details.className = "clip-context";
  const summary = document.createElement("summary");
  summary.textContent = "Adjust context for this clip";
  details.append(summary);
  const labels = {
    audience: "TARGET AUDIENCE",
    topic: "TOPIC",
    goal: "CREATOR GOAL",
    tone: "TONE / VOICE",
  };
  Object.entries(labels).forEach(([key, label]) => {
    const fieldLabel = document.createElement("label");
    fieldLabel.textContent = label;
    const input = document.createElement("input");
    input.name = key;
    input.maxLength = 300;
    input.value = initialContext[key] || "";
    input.placeholder = `Optional ${label.toLowerCase()}`;
    details.append(fieldLabel, input);
  });
  return details;
}

function getClipContext(card) {
  const context = {};
  card.querySelectorAll(".clip-context input").forEach((input) => {
    context[input.name] = input.value.trim();
  });
  return context;
}

function updateSelectedClipCount() {
  const selected = document.querySelectorAll(".clip-select:checked").length;
  suggestSelected.disabled = selected === 0;
  suggestSelected.textContent = selected
    ? `SUGGEST TITLES & HASHTAGS · ${selected}`
    : "SUGGEST TITLES & HASHTAGS";
  const total = document.querySelectorAll(".clip-select").length;
  selectAllClips.checked = total > 0 && selected === total;
  selectAllClips.indeterminate = selected > 0 && selected < total;
}

async function suggestSelectedClips() {
  if (!activeJobId) return;
  const cards = [...document.querySelectorAll(".clip-select:checked")]
    .map((input) => input.closest(".clip-card"));
  if (!cards.length) return;
  suggestSelected.disabled = true;
  metadataMessage.textContent = "Drafting transcript-grounded suggestions locally…";
  metadataMessage.classList.remove("hidden");
  try {
    const contexts = {};
    cards.forEach((card) => {
      contexts[card.dataset.clipName] = getClipContext(card);
    });
    const response = await fetch(`/api/jobs/${encodeURIComponent(activeJobId)}/suggestions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clip_names: cards.map((card) => card.dataset.clipName),
        contexts,
      }),
    });
    const data = await readResponse(response);
    cards.forEach((card) => {
      const suggestions = data.suggestions[card.dataset.clipName];
      renderSuggestionPanel(
        card,
        activeJobId,
        { name: card.dataset.clipName },
        suggestions,
      );
    });
    metadataMessage.textContent =
      "Suggestions are drafts based on the transcript and your context. Check accuracy and fit before using them.";
  } catch (error) {
    metadataMessage.textContent = error.message || "Could not suggest titles for these clips.";
  } finally {
    updateSelectedClipCount();
  }
}

function renderSuggestionPanel(card, jobId, clip, suggestions) {
  card.querySelector(".suggestion-panel")?.remove();
  const panel = document.createElement("section");
  panel.className = "suggestion-panel";
  const summary = document.createElement("p");
  summary.className = "suggestion-summary";
  summary.textContent = `Transcript summary: ${suggestions.summary}`;
  panel.append(summary);

  let activeTitle;
  suggestions.options.forEach((option, index) => {
    const optionRow = document.createElement("div");
    optionRow.className = "suggestion-option";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = `title-choice-${clip.name}`;
    radio.checked = index === 0;
    const description = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = option.title;
    const rationale = document.createElement("p");
    rationale.textContent = option.rationale;
    description.append(title, rationale);
    const copyOption = document.createElement("button");
    copyOption.type = "button";
    copyOption.textContent = "COPY";
    copyOption.addEventListener("click", () => copyTitle(option.title, panel));
    radio.addEventListener("change", () => {
      activeTitle.value = option.title;
    });
    optionRow.append(radio, description, copyOption);
    panel.append(optionRow);
  });

  const tags = document.createElement("p");
  tags.className = "suggestion-summary";
  tags.textContent = suggestions.hashtags.length
    ? `Suggested hashtags: ${suggestions.hashtags.join(" ")}`
    : "No specific hashtags suggested; add only tags that accurately describe this clip.";
  panel.append(tags);

  if (suggestions.uncertainties.length) {
    const uncertaintyList = document.createElement("ul");
    uncertaintyList.className = "suggestion-uncertainty";
    suggestions.uncertainties.forEach((note) => {
      const item = document.createElement("li");
      item.textContent = note;
      uncertaintyList.append(item);
    });
    panel.append(uncertaintyList);
  }

  const titleLabel = document.createElement("label");
  titleLabel.className = "chosen-title-label";
  titleLabel.textContent = "EDIT THE TITLE TO SAVE AS THIS FILE NAME";
  activeTitle = document.createElement("input");
  activeTitle.className = "chosen-title";
  activeTitle.maxLength = 100;
  activeTitle.value = suggestions.options[0].title;
  panel.append(titleLabel, activeTitle);

  const actions = document.createElement("div");
  actions.className = "metadata-actions";
  const copyChosen = document.createElement("button");
  copyChosen.type = "button";
  copyChosen.textContent = "COPY EDITED TITLE";
  copyChosen.addEventListener("click", () => copyTitle(activeTitle.value, panel));
  const saveTitle = document.createElement("button");
  saveTitle.type = "button";
  saveTitle.textContent = "USE TITLE & SAVE CLIP";
  saveTitle.addEventListener("click", async () => {
    const oldName = card.dataset.clipName;
    saveTitle.disabled = true;
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(oldName)}/title`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: activeTitle.value,
            context: getClipContext(card),
          }),
        },
      );
      const data = await readResponse(response);
      card.dataset.clipName = data.name;
      card.querySelector("video").src =
        `/api/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(data.name)}`;
      const download = card.querySelector(".clip-actions a");
      download.href = data.download_url;
      card.querySelector(".clip-title").textContent = data.title;
      card.querySelector(".clip-title").classList.remove("hidden");
      card.querySelector(".clip-file-location").textContent = `Saved in ${data.path}`;
      panel.remove();
      metadataMessage.textContent = `Saved as ${data.name} in ${data.path}`;
      metadataMessage.classList.remove("hidden");
    } catch (error) {
      metadataMessage.textContent = error.message || "Could not save the selected title.";
      metadataMessage.classList.remove("hidden");
      saveTitle.disabled = false;
    }
  });
  const skip = document.createElement("button");
  skip.type = "button";
  skip.textContent = "SKIP SUGGESTIONS";
  skip.addEventListener("click", async () => {
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(card.dataset.clipName)}/skip-suggestions`,
        { method: "POST" },
      );
      await readResponse(response);
      panel.remove();
      metadataMessage.textContent = "Suggestions skipped. The clip itself is unchanged.";
    } catch (error) {
      metadataMessage.textContent = error.message || "Could not skip suggestions.";
    }
    metadataMessage.classList.remove("hidden");
  });
  actions.append(copyChosen, saveTitle, skip);
  panel.append(actions);
  card.querySelector(".clip-info").append(panel);
}

async function copyTitle(title, panel) {
  const status = document.createElement("p");
  status.className = "suggestion-summary";
  try {
    await navigator.clipboard.writeText(title);
    status.textContent = "Title copied.";
  } catch {
    status.textContent = "Clipboard access was unavailable; select and copy the title manually.";
  }
  panel.append(status);
}

function formatTime(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function clearPreviousResult() {
  if (pollTimer) window.clearTimeout(pollTimer);
  localStorage.removeItem(SAVED_JOB_KEY);
  activeJobId = null;
  results.classList.add("hidden");
  candidateReview.classList.add("hidden");
  candidateReviewJobId = null;
  candidatesForReview = [];
  sourcePreview.pause();
  sourcePreview.removeAttribute("src");
  sourcePreview.load();
  jobPanel.classList.remove("hidden");
  document.getElementById("job-error").classList.add("hidden");
  document.getElementById("job-spinner").classList.remove("done");
  document.getElementById("job-spinner").textContent = "";
  document.getElementById("job-stage").textContent = "STARTING";
  document.getElementById("job-title").textContent = "Getting your clips ready";
  document.getElementById("job-count").textContent = "";
  setProgress(0, "Waiting to start…");
}

function resetCreateButton() {
  createButton.disabled = false;
  createButton.querySelector("span").textContent = "FIND MY CLIPS";
}

function updateOutputMode() {
  const isOriginal = outputMode.value === "original";
  document.getElementById("output-mode-hint").textContent = isOriginal
    ? "Keeps each clip at the source video's encoded width, height, and aspect ratio."
    : "Portrait 1080 × 1920 with the full source over a blurred fill.";
  document.getElementById("format-badge").textContent = isOriginal ? "SOURCE" : "9:16";
  document.getElementById("format-title").textContent = isOriginal
    ? "Original video shape"
    : "Vertical, with room to breathe";
  document.getElementById("format-details").textContent = isOriginal
    ? "Source dimensions and aspect ratio are preserved."
    : "Full video + blurred fill · 1080 × 1920";
  faceTracking.disabled = isOriginal;
  document.getElementById("face-tracking-hint").textContent = isOriginal
    ? "Only used for TikTok-style framing"
    : "Keep detected faces in frame";
}

const savedJobId = localStorage.getItem(SAVED_JOB_KEY);
if (savedJobId) {
  activeJobId = savedJobId;
  createButton.disabled = true;
  createButton.querySelector("span").textContent = "RECONNECTING…";
  jobPanel.classList.remove("hidden");
  document.getElementById("job-stage").textContent = "RECONNECTING TO JOB";
  document.getElementById("job-title").textContent = "Checking your clip progress";
  document.getElementById("job-message").textContent =
    "Your upload has been accepted. Reconnecting to the existing job so you do not need to upload it again.";
  pollJob();
}

updateOutputMode();
