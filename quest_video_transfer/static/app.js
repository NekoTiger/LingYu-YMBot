"use strict";

const CHUNK_SIZE = 8 * 1024 * 1024;
const MAX_RETRIES = 3;
const STORAGE_PREFIX = "quest-video-transfer:";

const elements = {
  body: document.body,
  onlineState: document.querySelector("#online-state"),
  onlineLabel: document.querySelector("#online-label"),
  fileInput: document.querySelector("#file-input"),
  dropzone: document.querySelector("#dropzone"),
  copyUrl: document.querySelector("#copy-url"),
  displayUrl: document.querySelector("#display-url"),
  qrFrame: document.querySelector("#qr-frame"),
  qrCode: document.querySelector("#qr-code"),
  connectHint: document.querySelector(".connect-hint"),
  transferSection: document.querySelector("#transfer-section"),
  transferList: document.querySelector("#transfer-list"),
  transferCount: document.querySelector("#transfer-count"),
  fileList: document.querySelector("#file-list"),
  emptyState: document.querySelector("#empty-state"),
  refreshFiles: document.querySelector("#refresh-files"),
  openFolder: document.querySelector("#open-folder"),
  uploadDir: document.querySelector("#upload-dir"),
  toast: document.querySelector("#toast"),
};

const icons = {
  video: `
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="3"/>
      <path d="m10 9 5 3-5 3V9Z"/>
    </svg>`,
  close: `
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17"/>
    </svg>`,
  retry: `
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M20 7v5h-5"/>
      <path d="M19 12a7 7 0 1 0-2 5"/>
    </svg>`,
  check: `
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m6 12 4 4 8-9"/>
    </svg>`,
  download: `<span class="download-glyph" aria-hidden="true">↓</span>`,
};

const state = {
  info: null,
  jobs: [],
  processing: false,
  toastTimer: null,
  filesLoading: false,
};

function isQuestBrowser() {
  const userAgent = navigator.userAgent || "";
  return /OculusBrowser|Quest/i.test(userAgent);
}

function createElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function showToast(message) {
  clearTimeout(state.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("is-visible");
  }, 2600);
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 100 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 1) {
    return "即将完成";
  }
  if (seconds < 60) {
    return `还剩 ${Math.ceil(seconds)} 秒`;
  }
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) {
    return `还剩 ${minutes} 分钟`;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `还剩 ${hours} 小时 ${rest} 分` : `还剩 ${hours} 小时`;
}

function formatDate(timestamp) {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(timestamp * 1000));
  } catch {
    return "";
  }
}

function fingerprint(file) {
  return `${file.name}|${file.size}|${file.lastModified || 0}`;
}

function storageKey(file) {
  return `${STORAGE_PREFIX}${fingerprint(file)}`;
}

function readStoredUploadId(file) {
  try {
    return window.localStorage.getItem(storageKey(file)) || "";
  } catch {
    return "";
  }
}

function storeUploadId(file, uploadId) {
  try {
    window.localStorage.setItem(storageKey(file), uploadId);
  } catch {
    // Resume metadata is an enhancement; uploads still work without storage.
  }
}

function forgetUploadId(file) {
  try {
    window.localStorage.removeItem(storageKey(file));
  } catch {
    // Ignore storage access failures.
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...options,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const error = new Error(
      typeof payload === "object" && payload && payload.error
        ? payload.error
        : `请求失败 (${response.status})`,
    );
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.className = "visually-hidden";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) {
    throw new Error("浏览器不允许复制");
  }
}

async function loadInfo() {
  try {
    state.info = await api("/api/info");
    elements.onlineState.classList.add("is-online");
    elements.onlineLabel.textContent = "电脑在线";
    elements.displayUrl.textContent = state.info.displayUrl.replace(/^https?:\/\//, "");
    elements.uploadDir.textContent = state.info.uploadDir;
    elements.openFolder.hidden = !state.info.canOpenFolder;

    elements.qrCode.addEventListener("load", () => {
      elements.qrFrame.classList.add("is-ready");
    });
    elements.qrCode.addEventListener("error", () => {
      elements.qrFrame.hidden = true;
      elements.connectHint.textContent = "用 Quest 3 浏览器打开上面的地址。";
    });
    elements.qrCode.src = `/api/qr.svg?data=${encodeURIComponent(state.info.entryUrl)}`;
  } catch (error) {
    elements.onlineState.classList.remove("is-online");
    elements.onlineLabel.textContent = "连接已断开";
    elements.displayUrl.textContent = "刷新页面重试";
    elements.uploadDir.textContent = "无法读取保存位置";
    showToast(error.message);
  }
}

function makeJob(file) {
  const job = {
    key: fingerprint(file),
    file,
    status: "queued",
    uploaded: 0,
    uploadId: "",
    speed: 0,
    eta: 0,
    startOffset: 0,
    error: "",
    cancelled: false,
    controller: null,
    startedAt: 0,
    row: null,
  };
  buildJobRow(job);
  return job;
}

function buildJobRow(job) {
  const row = createElement("li", "transfer-item");
  row.dataset.job = job.key;

  const icon = createElement("span", "transfer-icon");
  icon.innerHTML = icons.video;

  const content = createElement("div", "transfer-content");
  const line = createElement("div", "transfer-line");
  const name = createElement("span", "transfer-name", job.file.name);
  name.title = job.file.name;
  const percent = createElement("span", "transfer-percent", "0%");
  line.append(name, percent);

  const track = createElement("div", "progress-track");
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", `${job.file.name} 上传进度`);
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", "100");
  track.setAttribute("aria-valuenow", "0");
  const fill = createElement("div", "progress-fill");
  track.append(fill);

  const statusLine = createElement("div", "transfer-status");
  const statusText = createElement("span", "", "等待");
  const metricText = createElement("span", "", formatBytes(job.file.size));
  statusLine.append(statusText, metricText);
  content.append(line, track, statusLine);

  const action = createElement("button", "transfer-action");
  action.type = "button";
  action.setAttribute("aria-label", "取消上传");
  action.innerHTML = icons.close;
  action.addEventListener("click", () => handleJobAction(job));

  row.append(icon, content, action);
  elements.transferList.append(row);

  job.row = {
    root: row,
    icon,
    percent,
    track,
    fill,
    statusText,
    metricText,
    action,
  };
}

function setJobStatus(job, status, message, metrics = "") {
  job.status = status;
  if (!job.row) {
    return;
  }

  const { root, statusText, metricText } = job.row;
  root.classList.toggle("is-done", status === "done");
  root.classList.toggle("is-error", status === "error");
  statusText.textContent = message;
  statusText.classList.toggle("status-error", status === "error");
  metricText.textContent = metrics;
}

function updateJobProgress(job, uploaded) {
  job.uploaded = Math.min(uploaded, job.file.size);
  const percentValue = job.file.size
    ? Math.min(100, (job.uploaded / job.file.size) * 100)
    : 0;
  const percentLabel = `${Math.floor(percentValue)}%`;

  if (job.row) {
    job.row.fill.style.width = `${percentValue}%`;
    job.row.percent.textContent = percentLabel;
    job.row.track.setAttribute("aria-valuenow", String(Math.floor(percentValue)));
  }
}

function handleJobAction(job) {
  if (job.status === "error") {
    job.cancelled = false;
    job.error = "";
    setJobStatus(job, "queued", "等待", formatBytes(job.file.size));
    if (job.row) {
      job.row.action.innerHTML = icons.close;
      job.row.action.setAttribute("aria-label", "取消上传");
    }
    processQueue();
    return;
  }

  if (job.status === "done") {
    removeJob(job);
    return;
  }

  job.cancelled = true;
  if (job.uploadId) {
    fetch(`/api/upload/${job.uploadId}/abort`, {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
    }).catch(() => {});
  }
  if (job.controller) {
    job.controller.abort();
  }
  setJobStatus(job, "cancelled", "已取消", "");
  window.setTimeout(() => removeJob(job), 700);
}

function removeJob(job) {
  job.cancelled = true;
  if (job.row) {
    job.row.root.remove();
  }
  state.jobs = state.jobs.filter((item) => item !== job);
  updateTransferSummary();
}

function updateTransferSummary() {
  const count = state.jobs.filter((job) => job.status !== "cancelled").length;
  elements.transferSection.hidden = count === 0;
  elements.transferCount.textContent = count ? `${count} 个文件` : "";
}

function enqueueFiles(fileList) {
  const incoming = Array.from(fileList || []).filter((file) => file.size > 0);
  if (!incoming.length) {
    showToast("请选择有效的视频文件");
    return;
  }

  let added = 0;
  let duplicated = 0;
  for (const file of incoming) {
    const key = fingerprint(file);
    if (state.jobs.some((job) => job.key === key && job.status !== "cancelled")) {
      duplicated += 1;
      continue;
    }
    state.jobs.push(makeJob(file));
    added += 1;
  }

  updateTransferSummary();
  if (duplicated) {
    showToast(duplicated === incoming.length ? "文件已在传输列表中" : "已忽略重复文件");
  }
  if (added) {
    processQueue();
  }
}

async function processQueue() {
  if (state.processing) {
    return;
  }
  state.processing = true;

  try {
    while (true) {
      const job = state.jobs.find(
        (item) => item.status === "queued" && !item.cancelled,
      );
      if (!job) {
        break;
      }
      await runJob(job);
    }
  } finally {
    state.processing = false;
  }
}

async function runJob(job) {
  job.startedAt = performance.now();
  try {
    setJobStatus(job, "preparing", "正在连接", formatBytes(job.file.size));
    const session = await resumeOrCreate(job);
    let offset = session.offset;
    job.startOffset = offset;
    job.uploadId = session.uploadId;
    storeUploadId(job.file, job.uploadId);
    updateJobProgress(job, offset);

    if (offset === job.file.size) {
      setJobStatus(job, "verifying", "正在完成", "100%");
      await completeJob(job);
      return;
    }

    while (offset < job.file.size) {
      if (job.cancelled) {
        throw new UploadCancelled();
      }

      const end = Math.min(offset + CHUNK_SIZE, job.file.size);
      const chunk = job.file.slice(offset, end);
      const result = await sendChunkWithRetry(job, chunk, offset);
      offset = result.offset;
      updateJobProgress(job, offset);

      const elapsedSeconds = Math.max(
        (performance.now() - job.startedAt) / 1000,
        0.001,
      );
      job.speed = Math.max(0, offset - job.startOffset) / elapsedSeconds;
      job.eta = job.speed > 0 ? (job.file.size - offset) / job.speed : 0;

      const detail = job.speed > 0
        ? `${formatBytes(job.speed)}/s · ${formatDuration(job.eta)}`
        : formatBytes(job.file.size);
      setJobStatus(job, "uploading", "上传中", detail);
    }

    if (job.cancelled) {
      throw new UploadCancelled();
    }
    setJobStatus(job, "verifying", "正在完成", "100%");
    await completeJob(job);
  } catch (error) {
    if (job.cancelled || error instanceof UploadCancelled) {
      removeJob(job);
      return;
    }

    const message = error && error.message ? error.message : "连接中断";
    setJobStatus(job, "error", "传输中断", "可重试或再次选择续传");
    const action = job.row && job.row.action;
    if (action) {
      action.innerHTML = icons.retry;
      action.setAttribute("aria-label", "重试上传");
    }
    showToast(`${job.file.name}：${message}`);
  } finally {
    job.controller = null;
  }
}

async function resumeOrCreate(job) {
  const storedId = readStoredUploadId(job.file);
  if (storedId) {
    try {
      const status = await api(`/api/upload/${encodeURIComponent(storedId)}`);
      if (status.size === job.file.size && status.offset <= status.size) {
        return {
          uploadId: status.uploadId,
          offset: status.offset,
        };
      }
    } catch (error) {
      if (error.status !== 404) {
        throw error;
      }
    }
    forgetUploadId(job.file);
  }

  const created = await api("/api/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: job.file.name,
      size: job.file.size,
      lastModified: job.file.lastModified || 0,
    }),
  });
  return {
    uploadId: created.uploadId,
    offset: 0,
  };
}

async function sendChunkWithRetry(job, chunk, offset) {
  let attempt = 0;
  while (true) {
    if (job.cancelled) {
      throw new UploadCancelled();
    }

    try {
      return await sendChunk(job, chunk, offset);
    } catch (error) {
      if (error instanceof UploadCancelled || job.cancelled) {
        throw new UploadCancelled();
      }
      if (error.code === "offset_mismatch") {
        return { offset: error.expectedOffset };
      }
      if (attempt >= MAX_RETRIES) {
        throw error;
      }

      attempt += 1;
      setJobStatus(
        job,
        "uploading",
        `正在重试 ${attempt}/${MAX_RETRIES}`,
        formatBytes(job.uploaded),
      );
      await delay(650 * 2 ** (attempt - 1));

      try {
        const status = await api(`/api/upload/${encodeURIComponent(job.uploadId)}`);
        if (status.offset > offset) {
          return { offset: status.offset };
        }
      } catch {
        // The retry below will surface a useful error if the server is unreachable.
      }
    }
  }
}

async function sendChunk(job, chunk, offset) {
  const controller = new AbortController();
  job.controller = controller;
  try {
    const response = await fetch(
      `/api/upload/${encodeURIComponent(job.uploadId)}/chunk?offset=${offset}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: chunk,
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      },
    );

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const error = new Error(
        payload && payload.error ? payload.error : `上传失败 (${response.status})`,
      );
      error.status = response.status;
      error.code = payload && payload.code;
      error.expectedOffset = payload && payload.expectedOffset;
      throw error;
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new UploadCancelled();
    }
    throw error;
  } finally {
    if (job.controller === controller) {
      job.controller = null;
    }
  }
}

async function completeJob(job) {
  await api(`/api/upload/${encodeURIComponent(job.uploadId)}/complete`, {
    method: "POST",
  });
  forgetUploadId(job.file);
  updateJobProgress(job, job.file.size);
  setJobStatus(job, "done", "已送达", formatBytes(job.file.size));
  if (job.row) {
    job.row.icon.innerHTML = icons.check;
    job.row.action.innerHTML = icons.close;
    job.row.action.setAttribute("aria-label", "从列表移除");
  }
  showToast(`${job.file.name} 已保存到电脑`);
  await refreshFiles();
  window.setTimeout(() => removeJob(job), 2200);
}

class UploadCancelled extends Error {
  constructor() {
    super("上传已取消");
    this.name = "UploadCancelled";
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function refreshFiles(showSpinner = false) {
  if (state.filesLoading) {
    return;
  }
  state.filesLoading = true;
  if (showSpinner) {
    elements.refreshFiles.classList.add("is-spinning");
  }

  try {
    const result = await api("/api/files");
    renderFiles(result.files || []);
  } catch (error) {
    if (showSpinner) {
      showToast(error.message);
    }
  } finally {
    state.filesLoading = false;
    elements.refreshFiles.classList.remove("is-spinning");
  }
}

function renderFiles(files) {
  elements.fileList.replaceChildren();
  elements.emptyState.hidden = files.length > 0;
  elements.fileList.hidden = files.length === 0;

  for (const file of files) {
    const item = createElement("li", "file-item");
    const type = createElement("span", "file-type");
    type.innerHTML = icons.video;

    const details = createElement("div", "file-details");
    const name = createElement("a", "file-name", file.name);
    name.href = file.downloadUrl;
    name.download = file.name;
    name.title = file.name;
    const meta = createElement(
      "span",
      "file-meta",
      `${formatBytes(file.size)} · ${formatDate(file.modified)}`,
    );
    details.append(name, meta);

    const download = createElement("a", "download-link");
    download.href = file.downloadUrl;
    download.download = file.name;
    download.setAttribute("aria-label", `下载 ${file.name}`);
    download.innerHTML = icons.download;

    item.append(type, details, download);
    elements.fileList.append(item);
  }
}

async function openUploadFolder() {
  try {
    await api("/api/open-folder", { method: "POST" });
  } catch (error) {
    showToast(error.message);
  }
}

elements.body.classList.toggle("is-quest", isQuestBrowser());

elements.dropzone.addEventListener("click", () => {
  elements.fileInput.click();
});

elements.fileInput.addEventListener("change", () => {
  enqueueFiles(elements.fileInput.files);
  elements.fileInput.value = "";
});

for (const eventName of ["dragenter", "dragover"]) {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  elements.dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropzone.classList.remove("is-dragging");
  });
}

elements.dropzone.addEventListener("drop", (event) => {
  enqueueFiles(event.dataTransfer.files);
});

elements.copyUrl.addEventListener("click", async () => {
  if (!state.info) {
    return;
  }
  try {
    await copyText(state.info.entryUrl);
    showToast("访问链接已复制");
  } catch {
    showToast("复制失败，请手动打开上面的地址");
  }
});

elements.refreshFiles.addEventListener("click", () => {
  refreshFiles(true);
});

elements.openFolder.addEventListener("click", openUploadFolder);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refreshFiles();
  }
});

window.setInterval(() => {
  if (!document.hidden) {
    refreshFiles();
  }
}, 10000);

loadInfo();
refreshFiles();
