const state = {
  channels: [],
  allPosts: [],
  filteredPosts: [],
  selectedPost: null,
  report: null,
  comments: [],
  related: null,
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
  tabLinks: document.getElementById("tabLinks"),
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

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
      <div class="post-actions-row">
        <button class="btn ghost related-btn">Связанные посты</button>
      </div>
    `;
    card.onclick = () => selectPost(p);
    card.querySelector(".related-btn").onclick = async (event) => {
      event.stopPropagation();
      await openRelatedForPost(p);
    };
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

  await Promise.all([loadReport(post.id), loadComments(post.id), loadRelated(post.id)]);
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

async function loadRelated(postId) {
  try {
    state.related = await api(`/api/links/posts/${postId}/related`);
  } catch (error) {
    state.related = {
      root_post_id: postId,
      related_posts: [],
      graph: { nodes: [], edges: [] },
      error: error.message,
    };
  }
}

function renderGraphSvg(graph, rootId) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  if (!nodes.length) {
    return "<div class='muted'>Недостаточно данных для построения графа.</div>";
  }

  const width = 760;
  const height = 320;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.max(95, Math.min(width, height) * 0.36);
  const positions = new Map();

  const rootNode = nodes.find((n) => n.id === rootId) || nodes.find((n) => n.is_root) || nodes[0];
  positions.set(rootNode.id, { x: centerX, y: centerY });

  const others = nodes.filter((n) => n.id !== rootNode.id);
  others.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / Math.max(1, others.length);
    positions.set(node.id, {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    });
  });

  const edgeMarkup = edges
    .map((edge) => {
      const from = positions.get(edge.source);
      const to = positions.get(edge.target);
      if (!from || !to) return "";
      const midX = (from.x + to.x) / 2;
      const midY = (from.y + to.y) / 2;
      const conf = edge.confidence != null ? ` (${(edge.confidence * 100).toFixed(0)}%)` : "";
      return `
        <line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" class="graph-edge-line"></line>
        <text x="${midX}" y="${midY - 8}" class="graph-edge-label">${escapeHtml(edge.relation_ru + conf)}</text>
      `;
    })
    .join("");

  const nodeMarkup = nodes
    .map((node) => {
      const pos = positions.get(node.id);
      if (!pos) return "";
      const nodeClass = node.id === rootNode.id ? "graph-node root" : "graph-node";
      return `
        <g class="${nodeClass}" transform="translate(${pos.x}, ${pos.y})">
          <circle r="30"></circle>
          <text text-anchor="middle" dy="6">${node.id}</text>
        </g>
        <text x="${pos.x}" y="${pos.y + 52}" text-anchor="middle" class="graph-node-label">${escapeHtml(node.label || `Пост ${node.id}`)}</text>
      `;
    })
    .join("");

  return `
    <svg class="related-graph" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
      ${edgeMarkup}
      ${nodeMarkup}
    </svg>
  `;
}

function renderRelatedPanel() {
  if (!state.related || !state.selectedPost) {
    el.tabLinks.innerHTML = "Связи пока не загружены.";
    return;
  }

  const rows = (state.related.related_posts || [])
    .slice()
    .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
    .map(
      (item) => `
      <div class="related-row">
        <div>
          <div class="related-title">Пост ${item.post_id} · @${escapeHtml(item.channel_username)}</div>
          <div class="related-preview">${escapeHtml(item.text_preview || "Без текста")}</div>
        </div>
        <div class="related-meta">
          <div>${escapeHtml(item.link_type_ru)}</div>
          <div class="muted">${escapeHtml(item.direction_ru)}</div>
          <div class="related-confidence">${item.confidence != null ? (item.confidence * 100).toFixed(1) + "%" : "—"}</div>
        </div>
      </div>
    `,
    )
    .join("");

  const graphMarkup = renderGraphSvg(state.related.graph, state.selectedPost.id);
  const loadError = state.related.error
    ? `<div class="related-error">Ошибка загрузки связей: ${escapeHtml(state.related.error)}</div>`
    : "";

  el.tabLinks.innerHTML = `
    ${loadError}
    <div class="related-headline">
      Найдено связей: <strong>${formatNum((state.related.related_posts || []).length)}</strong>
    </div>
    <div class="related-list">
      ${rows || "<div class='muted'>Связанные посты не найдены.</div>"}
    </div>
    <div class="graph-wrap">
      <div class="graph-title">Граф связей</div>
      ${graphMarkup}
    </div>
  `;
}

function renderDetail() {
  el.tabReport.textContent = state.report?.content || "Отчет отсутствует";
  el.tabComments.innerHTML = state.comments.length
    ? state.comments
        .slice(0, 200)
        .map((c) => `<div><strong>${c.author_username || c.author_id || "user"}:</strong> ${escapeHtml(c.text || "")}</div>`)
        .join("<hr />")
    : "Комментариев пока нет";

  renderRelatedPanel();

  el.tabData.textContent = JSON.stringify(
    {
      post: state.selectedPost,
      report_status: state.report?.status,
      comments_count: state.comments.length,
      related_count: state.related?.related_posts?.length || 0,
    },
    null,
    2,
  );
}

function activateTab(key) {
  const tabs = [...document.querySelectorAll(".tab")];
  tabs.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === key));
  ["report", "comments", "links", "data"].forEach((name) => {
    document.getElementById(`tab${name[0].toUpperCase()}${name.slice(1)}`).classList.toggle("hidden", name !== key);
  });
}

function initTabs() {
  const tabs = [...document.querySelectorAll(".tab")];
  tabs.forEach((btn) => {
    btn.onclick = () => activateTab(btn.dataset.tab);
  });
}

async function openRelatedForPost(post) {
  if (!state.selectedPost || state.selectedPost.id !== post.id) {
    await selectPost(post);
  } else {
    await loadRelated(post.id);
    renderDetail();
  }
  activateTab("links");
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
