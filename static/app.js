const form = document.getElementById("add-form");
const tbody = document.getElementById("pages-tbody");

// --- Helpers ---
const STATUS_ICONS = {
  pending: "clock",
  scheduled: "calendar-clock",
  "in-progress": "loader",
  successful: "check-circle-2",
  failed: "x-circle",
  expired: "timer-off",
  stopped: "square",
};

const STATUS_LABELS = {
  pending: "ожидает",
  scheduled: "запланировано",
  "in-progress": "выполняется",
  successful: "успешно",
  failed: "ошибка",
  expired: "время вышло",
  stopped: "остановлено",
};

function badge(status) {
  const icon = STATUS_ICONS[status] || "circle";
  const label = STATUS_LABELS[status] || status;
  return `<span class="badge badge-${status}"><i data-lucide="${icon}" class="icon icon-sm"></i> ${label}</span>`;
}

function formatDT(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function errorCell(err) {
  if (!err) return "";
  const escaped = err.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  return `<div class="error-content">
    <span class="error-text" title="${escaped}">${escaped}</span>
    <button class="btn btn-ghost copy-err" onclick="copyError(this)" title="Копировать ошибку">
      <i data-lucide="copy" class="icon icon-sm"></i>
    </button>
  </div>`;
}

function rowHTML(p) {
  const canRun = ["pending", "scheduled", "stopped"].includes(p.status);
  const canStop = p.status === "in-progress";
  const displayName = p.label || p.url;
  const escaped_url = p.url.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  return `<tr data-id="${p.id}">
    <td class="url-cell" title="${escaped_url}">
      <span class="url-cell-content">${displayName}</span>
      <button class="btn btn-ghost copy-url" onclick="copyUrl(this, '${p.url.replace(/'/g, "\\'")}')" title="Копировать ссылку">
        <i data-lucide="link" class="icon icon-sm"></i>
      </button>
    </td>
    <td class="mono">${formatDT(p.window_start)} — ${formatDT(p.window_end)}</td>
    <td>${badge(p.status)}</td>
    <td>${p.attempts}</td>
    <td class="error-cell">${errorCell(p.last_error)}</td>
    <td class="actions-cell">
      ${canRun ? `<button class="btn btn-success-ghost" onclick="runNow(${p.id})" title="Запустить"><i data-lucide="play" class="icon icon-sm"></i></button>` : ""}
      ${canStop ? `<button class="btn btn-warning-ghost" onclick="stopTask(${p.id})" title="Остановить"><i data-lucide="square" class="icon icon-sm"></i></button>` : ""}
      <button class="btn btn-destructive-ghost" onclick="deletePage(${p.id})" title="Удалить"><i data-lucide="trash-2" class="icon icon-sm"></i></button>
    </td>
  </tr>`;
}

function renderIcons() {
  if (window.lucide) lucide.createIcons();
}

// --- Load pages ---
async function loadPages() {
  const res = await fetch("/api/pages");
  const pages = await res.json();
  if (pages.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Страниц пока нет.</td></tr>`;
  } else {
    tbody.innerHTML = pages.map(rowHTML).join("");
  }
  renderIcons();
}

// --- Add page ---
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(form);
  const body = {
    url: fd.get("url"),
    label: fd.get("label"),
    window_start: fd.get("window_start") + ":00",
    window_end: fd.get("window_end") + ":00",
  };
  await fetch("/api/pages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  form.reset();
  loadPages();
});

// --- Delete page ---
async function deletePage(id) {
  await fetch(`/api/pages/${id}`, { method: "DELETE" });
  loadPages();
}

// --- Run now ---
async function runNow(id) {
  await fetch(`/api/pages/${id}/run`, { method: "POST" });
}

// --- Stop task ---
async function stopTask(id) {
  await fetch(`/api/pages/${id}/stop`, { method: "POST" });
}

// --- Paste URL ---
async function pasteUrl() {
  const input = document.getElementById("f-url");
  try {
    const text = await navigator.clipboard.readText();
    input.value = text;
    input.dispatchEvent(new Event("input"));
  } catch {
    input.focus();
    document.execCommand("paste");
  }
}

// --- Copy URL ---
function copyUrl(btn, url) {
  navigator.clipboard.writeText(url).then(() => {
    const iconEl = btn.querySelector("[data-lucide]");
    iconEl.setAttribute("data-lucide", "check");
    renderIcons();
    setTimeout(() => {
      iconEl.setAttribute("data-lucide", "link");
      renderIcons();
    }, 1500);
  });
}

// --- Copy error ---
function copyError(btn) {
  const textEl = btn.closest(".error-content").querySelector(".error-text");
  const text = textEl.getAttribute("title");
  navigator.clipboard.writeText(text).then(() => {
    const iconEl = btn.querySelector("[data-lucide]");
    iconEl.setAttribute("data-lucide", "check");
    renderIcons();
    setTimeout(() => {
      iconEl.setAttribute("data-lucide", "copy");
      renderIcons();
    }, 1500);
  });
}

// --- SSE ---
function connectSSE() {
  const es = new EventSource("/api/events");
  es.addEventListener("update", (e) => {
    const p = JSON.parse(e.data);
    const existing = document.querySelector(`tr[data-id="${p.id}"]`);
    if (existing) {
      existing.outerHTML = rowHTML(p);
      renderIcons();
    } else {
      loadPages();
    }
  });
  es.onerror = () => {
    es.close();
    setTimeout(connectSSE, 3000);
  };
}

// --- Init ---
document.addEventListener("DOMContentLoaded", () => {
  renderIcons();
  loadPages();
  connectSSE();
});
