const state = {
  channels: [],
  allPosts: [],
  filteredPosts: [],
  selectedPost: null,
  report: null,
  comments: [],
};

const el = {
  dateFrom: document.getElementById("dateFrom"),
  dateTo: document.getElementById("dateTo"),
  channelFilter: document.getElementById("channelFilter"),
  minComments: document.getElementById("minComments"),
  topLimit: document.getElementById("topLimit"),
  applyBtn: document.getElementById("applyBtn"),
  resetBtn: document.getElementById("resetBtn"),
  postsList: document.getElementById("postsList"),
  kpiPosts: document.getElementById("kpiPosts"),
  kpiInvolvement: document.getElementById("kpiInvolvement"),
  kpiComments: document.getElementById("kpiComments"),
  emptyState: document.getElementById("emptyState"),
  detail: document.getElementById("detail"),
  detailChannel: document.getElementById("detailChannel"),
  detailDate: document.getElementById("detailDate"),
  detailMetrics: document.getElementById("detailMetrics"),
  tabReport: document.getElementById("tabReport"),
  tabComments: document.getElementById("tabComments"),
  tabData: document.getElementById("tabData"),
  detailStatus: document.getElementById("detailStatus"),
  refreshCommentsBtn: document.getElementById("refreshCommentsBtn"),
  generateReportBtn: document.getElementById("generateReportBtn"),
  copyMdBtn: document.getElementById("copyMdBtn"),
};

function toIsoDate(date) {
  return date.toISOString().slice(0, 10);
}

function formatNum(v) {
  return Number(v || 0).toLocaleString("ru-RU");
}

function formatDate(iso) {
  return new Date(iso).toLocaleString("ru-RU", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function api(path, opts = {}) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`${resp.status} ${txt}`);
  }
  return resp.json();
}

function setDetailStatus(message = "", ok = false) {
  el.detailStatus.textContent = message;
  el.detailStatus.classList.toggle("ok", Boolean(ok));
}

function initDateDefaults() {
  const now = new Date();
  const before = new Date(now);
  before.setDate(now.getDate() - 7);
  el.dateTo.value = toIsoDate(now);
  el.dateFrom.value = toIsoDate(before);
}

async function loadChannels() {
  state.channels = await api("/api/channels/");
  for (const c of state.channels) {
    const option = document.createElement("option");
    option.value = c.username;
    option.textContent = c.title ? `${c.title} (@${c.username})` : `@${c.username}`;
    el.channelFilter.append(option);
  }
}

function buildTopPostsUrl() {
  const from = `${el.dateFrom.value}T00:00:00`;
  const to = `${el.dateTo.value}T23:59:59`;
  const limit = Number(el.topLimit.value || 25);
  const params = new URLSearchParams({ date_from: from, date_to: to, limit: String(limit) });
  return `/api/posts/top?${params.toString()}`;
}

async function loadTopPosts() {
  state.allPosts = await api(buildTopPostsUrl());
  applyClientFilters();
}

function applyClientFilters() {
  const minComments = Number(el.minComments.value || 0);
  const channel = el.channelFilter.value;

  state.filteredPosts = state.allPosts.filter((p) => {
    if (p.comments_count < minComments) return false;
    if (channel && p.channel_username !== channel) return false;
    return true;
  });

  renderPosts();
  renderKpi();
}

function renderKpi() {
  const posts = state.filteredPosts;
  const totalComments = posts.reduce((acc, p) => acc + (p.comments_count || 0), 0);
  const involvements = posts.filter((p) => p.involvement !== null).map((p) => p.involvement);
  const avgInv = involvements.length ? involvements.reduce((a, b) => a + b, 0) / involvements.length : 0;

  el.kpiPosts.textContent = formatNum(posts.length);
  el.kpiComments.textContent = formatNum(totalComments);
  el.kpiInvolvement.textContent = `${(avgInv * 100).toFixed(1)}%`;
}

function renderPosts() {
  el.postsList.innerHTML = "";
  if (!state.filteredPosts.length) {
    el.postsList.innerHTML = "<div class='card' style='padding:14px'>Нет постов по выбранным фильтрам.</div>";
    return;
  }

  for (const p of state.filteredPosts) {
    const card = document.createElement("article");
    card.className = "post-card" + (state.selectedPost?.id === p.id ? " active" : "");
    card.innerHTML = `
      <div class="post-head">
        <div>
          <div class="post-channel">@${p.channel_username}</div>
          <div class="muted">${formatDate(p.date)}</div>
        </div>
      </div>
      <div class="post-preview">${(p.text_preview || "").slice(0, 170)}</div>
      <div class="post-meta">
        <span>💬 ${formatNum(p.comments_count)}</span>
        <span>👁 ${formatNum(p.views)}</span>
        <span>⚡ ${p.involvement ? (p.involvement * 100).toFixed(1) : "0.0"}%</span>
      </div>
    `;
    card.onclick = () => selectPost(p);
    el.postsList.append(card);
  }
}

async function selectPost(post) {
  state.selectedPost = post;
  renderPosts();
  el.emptyState.classList.add("hidden");
  el.detail.classList.remove("hidden");
  setDetailStatus("");

  el.detailChannel.textContent = `@${post.channel_username}`;
  el.detailDate.textContent = formatDate(post.date);
  el.detailMetrics.innerHTML = `
    <span>💬 ${formatNum(post.comments_count)}</span>
    <span>👁 ${formatNum(post.views)}</span>
    <span>⚡ ${post.involvement ? (post.involvement * 100).toFixed(1) : "0.0"}%</span>
  `;

  await Promise.all([loadReport(post.id), loadComments(post.id)]);
  renderDetail();
}

async function loadReport(postId) {
  try {
    state.report = await api(`/api/reports/${postId}`);
  } catch {
    state.report = { status: "pending", content: "Отчет пока не создан." };
  }
}

async function loadComments(postId) {
  state.comments = await api(`/api/posts/${postId}/comments`);
}

function renderDetail() {
  el.tabReport.textContent = state.report?.content || "Отчет отсутствует";
  el.tabComments.innerHTML = state.comments.length
    ? state.comments
        .slice(0, 200)
        .map((c) => `<div><strong>${c.author_username || c.author_id || "user"}:</strong> ${c.text || ""}</div>`)
        .join("<hr />")
    : "Комментариев пока нет";

  el.tabData.textContent = JSON.stringify(
    {
      post: state.selectedPost,
      report_status: state.report?.status,
      comments_count: state.comments.length,
    },
    null,
    2,
  );
}

function initTabs() {
  const tabs = [...document.querySelectorAll(".tab")];
  tabs.forEach((btn) => {
    btn.onclick = () => {
      tabs.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const key = btn.dataset.tab;
      ["report", "comments", "data"].forEach((name) => {
        document.getElementById(`tab${name[0].toUpperCase()}${name.slice(1)}`).classList.toggle("hidden", name !== key);
      });
    };
  });
}

async function updateCommentsForCurrent() {
  if (!state.selectedPost) return;
  el.refreshCommentsBtn.disabled = true;
  setDetailStatus("Обновляю комментарии...");
  try {
    await api(`/api/posts/${state.selectedPost.id}/comments/update`, { method: "POST" });
    await loadComments(state.selectedPost.id);
    renderDetail();
    setDetailStatus("Комментарии обновлены.", true);
  } catch (e) {
    setDetailStatus(`Ошибка обновления комментариев: ${e.message}`);
  } finally {
    el.refreshCommentsBtn.disabled = false;
  }
}

async function generateReportForCurrent() {
  if (!state.selectedPost) return;
  el.generateReportBtn.disabled = true;
  setDetailStatus("Генерирую отчет...");
  try {
    state.report = await api(`/api/reports/${state.selectedPost.id}/update`, { method: "POST" });
    renderDetail();
    const status = state.report?.status || "unknown";
    if (status === "ready") {
      setDetailStatus("Отчет сгенерирован.", true);
    } else {
      setDetailStatus(`Отчет обновлен со статусом: ${status}`);
    }
  } catch (e) {
    setDetailStatus(`Ошибка генерации отчета: ${e.message}`);
  } finally {
    el.generateReportBtn.disabled = false;
  }
}

async function copyMarkdown() {
  const text = state.report?.content || "";
  if (!text) return;
  await navigator.clipboard.writeText(text);
  el.copyMdBtn.textContent = "Скопировано";
  setTimeout(() => {
    el.copyMdBtn.textContent = "Скопировать Markdown";
  }, 1200);
}

function bindActions() {
  el.applyBtn.onclick = loadTopPosts;
  el.resetBtn.onclick = () => {
    initDateDefaults();
    el.channelFilter.value = "";
    el.minComments.value = "0";
    el.topLimit.value = "25";
    loadTopPosts();
  };
  el.channelFilter.onchange = applyClientFilters;
  el.minComments.oninput = applyClientFilters;
  el.refreshCommentsBtn.onclick = updateCommentsForCurrent;
  el.generateReportBtn.onclick = generateReportForCurrent;
  el.copyMdBtn.onclick = copyMarkdown;
}

async function init() {
  initDateDefaults();
  bindActions();
  initTabs();
  await loadChannels();
  await loadTopPosts();
}

init().catch((e) => {
  el.postsList.innerHTML = `<div class='card' style='padding:14px;color:#b42318'>Ошибка загрузки: ${e.message}</div>`;
});
