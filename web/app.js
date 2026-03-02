const state = {
  channels: [],
  eventsRaw: [],
  events: [],
  selectedEvent: null,
  selectedPost: null,
  eventPosts: [],
  eventEdges: [],
  report: null,
  comments: [],
  loadingEvents: false,
  loadingGraph: false,
  activeTab: "posts",
  graphView: { x: 0, y: 0, w: 1200, h: 620 },
  drag: { active: false, startX: 0, startY: 0, startViewX: 0, startViewY: 0 },
  eventsApiAvailable: true,
};

const NS = "http://www.w3.org/2000/svg";

const el = {
  dateFrom: document.getElementById("dateFrom"),
  dateTo: document.getElementById("dateTo"),
  channelFilter: document.getElementById("channelFilter"),
  channelDropdown: document.getElementById("channelDropdown"),
  channelDropdownBtn: document.getElementById("channelDropdownBtn"),
  channelDropdownMenu: document.getElementById("channelDropdownMenu"),
  channelDropdownValue: document.getElementById("channelDropdownValue"),
  categoryFilter: document.getElementById("categoryFilter"),
  minComments: document.getElementById("minComments"),
  topLimit: document.getElementById("topLimit"),
  applyBtn: document.getElementById("applyBtn"),
  resetBtn: document.getElementById("resetBtn"),
  eventsSearch: document.getElementById("eventsSearch"),
  eventsList: document.getElementById("eventsList"),
  kpiEvents: document.getElementById("kpiEvents"),
  kpiInvolvement: document.getElementById("kpiInvolvement"),
  kpiComments: document.getElementById("kpiComments"),
  kpiDelta: document.getElementById("kpiDelta"),
  graphTitle: document.getElementById("graphTitle"),
  graphSubtitle: document.getElementById("graphSubtitle"),
  graphSvg: document.getElementById("graphSvg"),
  timelineAxis: document.getElementById("timelineAxis"),
  relationFilter: document.getElementById("relationFilter"),
  fitViewBtn: document.getElementById("fitViewBtn"),
  detailsPane: document.getElementById("detailsPane"),
  detailsToggle: document.getElementById("detailsToggle"),
  closeDetailsBtn: document.getElementById("closeDetailsBtn"),
  emptyState: document.getElementById("emptyState"),
  detailsContent: document.getElementById("detailsContent"),
  detailTitle: document.getElementById("detailTitle"),
  detailDate: document.getElementById("detailDate"),
  detailMetrics: document.getElementById("detailMetrics"),
  tabPosts: document.getElementById("tabPosts"),
  tabComments: document.getElementById("tabComments"),
  tabReport: document.getElementById("tabReport"),
  tabSources: document.getElementById("tabSources"),
  detailStatus: document.getElementById("detailStatus"),
  refreshCommentsBtn: document.getElementById("refreshCommentsBtn"),
  generateReportBtn: document.getElementById("generateReportBtn"),
  exportPdfBtn: document.getElementById("exportPdfBtn"),
  exportDocxBtn: document.getElementById("exportDocxBtn"),
  copyMdBtn: document.getElementById("copyMdBtn"),
  themeToggle: document.getElementById("themeToggle"),
};

function toIsoDate(date) {
  return date.toISOString().slice(0, 10);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function num(value) {
  return Number(value || 0).toLocaleString("ru-RU");
}

function compact(value) {
  const n = Number(value || 0);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function normalizeInvolvement(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return null;
  if (n > 1) return n / 100;
  return n;
}

function formatInvolvement(value) {
  const normalized = normalizeInvolvement(value);
  if (normalized === null) return "—";
  return `${(normalized * 100).toFixed(1)}%`;
}

function truncateText(value, maxLen) {
  const text = String(value || "").trim();
  if (text.length <= maxLen) return text;
  return `${text.slice(0, Math.max(1, maxLen - 1))}…`;
}

function parsePostId(value) {
  if (value === null || value === undefined) return null;
  const str = String(value);
  const direct = Number(str);
  if (Number.isInteger(direct) && direct > 0) return direct;
  const match = str.match(/(\d+)/);
  if (!match) return null;
  const n = Number(match[1]);
  return Number.isInteger(n) && n > 0 ? n : null;
}

function isSyntheticPostId(value) {
  return !/^\d+$/.test(String(value ?? ""));
}

function getActionablePostId() {
  const currentId = state.selectedPost?.id;
  if (!isSyntheticPostId(currentId)) return Number(currentId);
  const eventRoot = parsePostId(state.selectedEvent?.root_post_id);
  if (eventRoot != null) return eventRoot;
  return null;
}

function formatDate(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("ru-RU", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

async function api(path, opts = {}) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${text}`);
  }
  return resp.json();
}

function setStatus(message = "", ok = false) {
  el.detailStatus.textContent = message;
  el.detailStatus.classList.toggle("ok", Boolean(ok));
}

function openDetailsPane() {
  document.body.classList.add("details-open");
}

function closeDetailsPane() {
  document.body.classList.remove("details-open");
}

function selectedChannels() {
  return [...el.channelFilter.selectedOptions].map((opt) => opt.value).filter(Boolean);
}

function updateChannelDropdownLabel() {
  const selected = selectedChannels();
  if (!selected.length) {
    el.channelDropdownValue.textContent = "Все каналы";
    return;
  }
  if (selected.length === 1) {
    const option = [...el.channelFilter.options].find((item) => item.value === selected[0]);
    el.channelDropdownValue.textContent = option?.textContent || selected[0];
    return;
  }
  el.channelDropdownValue.textContent = `Выбрано: ${selected.length}`;
}

function renderChannelDropdownOptions() {
  el.channelDropdownMenu.innerHTML = "";
  for (const option of el.channelFilter.options) {
    const row = document.createElement("label");
    row.className = "channel-option";
    row.innerHTML = `
      <input type="checkbox" value="${escapeHtml(option.value)}" ${option.selected ? "checked" : ""} />
      <span>${escapeHtml(option.textContent || option.value)}</span>
    `;
    const checkbox = row.querySelector("input");
    checkbox.onchange = () => {
      option.selected = checkbox.checked;
      updateChannelDropdownLabel();
      applyFiltersAndRender();
    };
    el.channelDropdownMenu.append(row);
  }
  updateChannelDropdownLabel();
}

function channelUsernameById(channelId) {
  const channel = state.channels.find((item) => Number(item.id) === Number(channelId));
  return channel?.username || "";
}

function postTitleFromText(text, fallback = "Без заголовка") {
  if (!text) return fallback;
  const line = String(text).split(/\r?\n/).map((v) => v.trim()).find(Boolean);
  return (line || fallback).slice(0, 80);
}

function initDates() {
  const now = new Date();
  const prev = new Date(now);
  prev.setDate(now.getDate() - 7);
  el.dateTo.value = toIsoDate(now);
  el.dateFrom.value = toIsoDate(prev);
}

async function loadChannels() {
  try {
    state.channels = await api("/api/channels/");
  } catch {
    state.channels = [];
  }

  el.channelFilter.innerHTML = "";
  for (const channel of state.channels) {
    const option = document.createElement("option");
    option.value = channel.username;
    option.textContent = channel.title ? `${channel.title} (@${channel.username})` : `@${channel.username}`;
    el.channelFilter.append(option);
  }
  renderChannelDropdownOptions();
}

function toEventFromPost(post) {
  const title = (post.text_preview || "").slice(0, 84) || `Событие из @${post.channel_username}`;
  return {
    id: `post-${post.id}`,
    source: "post",
    root_post_id: post.id,
    title,
    started_at: post.date,
    category: post.category || "other",
    views: post.views || 0,
    comments_count: post.comments_count || 0,
    involvement: normalizeInvolvement(post.involvement),
    report_status: post.report_status || "pending",
    channel_username: post.channel_username || "",
    raw: post,
  };
}

function eventFiltersMatch(event) {
  const selected = selectedChannels();
  const minComments = Number(el.minComments.value || 0);
  const category = el.categoryFilter.value;
  const q = (el.eventsSearch.value || "").trim().toLowerCase();

  if (selected.length && !selected.includes(event.channel_username)) return false;
  if (event.comments_count < minComments) return false;
  if (category && category !== event.category) return false;
  if (q && !`${event.title} ${event.channel_username}`.toLowerCase().includes(q)) return false;
  return true;
}

function renderEventsListLoading() {
  el.eventsList.innerHTML = "";
  for (let i = 0; i < 6; i += 1) {
    const div = document.createElement("div");
    div.className = "event-skeleton skeleton";
    el.eventsList.append(div);
  }
}

function renderEventsList() {
  el.eventsList.innerHTML = "";
  if (!state.events.length) {
    el.eventsList.innerHTML = "<div class='muted'>События не найдены по текущим фильтрам.</div>";
    return;
  }

  for (const event of state.events) {
    const item = document.createElement("article");
    item.className = "event-item" + (state.selectedEvent?.id === event.id ? " active" : "");
    const status = (event.report_status || "pending").toLowerCase();
    const statusClass = status === "ready" ? "status-ready" : status === "failed" ? "status-failed" : "status-pending";
    item.innerHTML = `
      <div class="event-title">${escapeHtml(event.title)}</div>
      <div class="event-date">${formatDate(event.started_at)}</div>
      <div class="event-metrics">
        <span>👁 ${compact(event.views)}</span>
        <span>💬 ${compact(event.comments_count)}</span>
        <span>⚡ ${formatInvolvement(event.involvement)}</span>
      </div>
      <div class="status-chip ${statusClass}">${escapeHtml(status)}</div>
    `;
    item.onclick = () => selectEvent(event);
    el.eventsList.append(item);
  }
}

function renderKpi() {
  const events = state.events;
  const totalComments = events.reduce((acc, e) => acc + (e.comments_count || 0), 0);
  const involvementValues = events
    .map((event) => normalizeInvolvement(event.involvement))
    .filter((value) => value !== null);
  const avgInvolvement = involvementValues.length
    ? involvementValues.reduce((acc, value) => acc + value, 0) / involvementValues.length
    : null;

  el.kpiEvents.textContent = num(events.length);
  el.kpiComments.textContent = num(totalComments);
  el.kpiInvolvement.textContent = avgInvolvement === null ? "—" : `${(avgInvolvement * 100).toFixed(1)}%`;
  el.kpiDelta.textContent = avgInvolvement === null ? "—" : `${Math.max(-99, Math.round(avgInvolvement * 100 - 4))}%`;
  el.kpiDelta.classList.toggle("muted-value", avgInvolvement === null);
}

function buildPostsTopUrl() {
  const from = `${el.dateFrom.value}T00:00:00`;
  const to = `${el.dateTo.value}T23:59:59`;
  const limit = Number(el.topLimit.value || 25);
  const params = new URLSearchParams({ date_from: from, date_to: to, limit: String(limit) });
  return `/api/posts/top?${params.toString()}`;
}

function buildEventsTopUrl() {
  const from = `${el.dateFrom.value}T00:00:00`;
  const to = `${el.dateTo.value}T23:59:59`;
  const limit = Number(el.topLimit.value || 25);
  const params = new URLSearchParams({ date_from: from, date_to: to, limit: String(limit) });
  return `/api/events/top?${params.toString()}`;
}

async function loadEvents() {
  state.loadingEvents = true;
  renderEventsListLoading();
  try {
    let events;
    if (state.eventsApiAvailable) {
      try {
        events = await api(buildEventsTopUrl());
        if (!Array.isArray(events)) throw new Error("bad events payload");
        events = events.map((ev) => ({
          id: String(ev.id),
          source: "event",
          root_post_id: ev.root_post_id || ev.post_id || null,
          title: ev.title || ev.name || "Без названия",
          started_at: ev.started_at || ev.date || ev.created_at,
          category: ev.category || "other",
          views: ev.views || 0,
          comments_count: ev.comments_count || 0,
          involvement: normalizeInvolvement(ev.involvement),
          report_status: ev.report_status || "pending",
          channel_username: ev.channel_username || "",
          raw: ev,
        }));
      } catch {
        state.eventsApiAvailable = false;
      }
    }
    if (!events) {
      const posts = await api(buildPostsTopUrl());
      events = posts.map(toEventFromPost);
    }

    state.eventsRaw = events;
    applyFiltersAndRender();
    if (state.events.length) {
      await selectEvent(state.events[0], { silentOpen: true });
    } else {
      clearGraph();
      hideDetails();
    }
  } catch (error) {
    el.eventsList.innerHTML = `<div class='muted'>Ошибка загрузки событий: ${escapeHtml(error.message)}</div>`;
  } finally {
    state.loadingEvents = false;
  }
}

function applyFiltersAndRender() {
  state.events = state.eventsRaw.filter(eventFiltersMatch);
  renderEventsList();
  renderKpi();
}

function clearGraph() {
  el.graphTitle.textContent = "Event Graph";
  el.graphSubtitle.textContent = "Выберите событие слева";
  el.graphSvg.innerHTML = "";
  el.timelineAxis.innerHTML = "";
  applyGraphViewBox();
}

function hideDetails() {
  state.selectedPost = null;
  el.emptyState.classList.remove("hidden");
  el.detailsContent.classList.add("hidden");
}

function showDetails() {
  el.emptyState.classList.add("hidden");
  el.detailsContent.classList.remove("hidden");
}

function fallbackMockPostsForEvent(event) {
  const baseDate = new Date(event.started_at || Date.now());
  const postCount = 5;
  const rootId = parsePostId(event.root_post_id ?? event.id) || `synthetic-${event.id}`;
  const posts = [];
  for (let i = 0; i < postCount; i += 1) {
    const d = new Date(baseDate);
    d.setMinutes(d.getMinutes() + i * 27);
    posts.push({
      id: i === 0 ? rootId : `synthetic-${rootId}-${i}`,
      event_id: event.id,
      title: i === 0 ? event.title : `Репост / реакция ${i}`,
      date: d.toISOString(),
      views: Math.max(1, Math.round(event.views * (1 - i * 0.18))),
      comments_count: Math.max(0, Math.round(event.comments_count * (1 - i * 0.22))),
      involvement: normalizeInvolvement(event.involvement) === null
        ? null
        : Math.max(0, normalizeInvolvement(event.involvement) * (1 - i * 0.08)),
      channel_username: i === 0 ? event.channel_username : `channel_${i}`,
      text_preview: i === 0 ? event.title : `Пост ${i} по событию ${event.title}`,
      is_root: i === 0,
    });
  }

  const edges = posts.slice(1).map((p, i) => ({
    source: posts[i].id,
    target: p.id,
    relation_type: "related",
    relation_ru: "Связано",
    confidence: clamp(0.95 - i * 0.1, 0.5, 0.99),
  }));

  return { posts, edges };
}

async function loadPostLinks(postId) {
  try {
    return await api(`/api/links/posts/${postId}`);
  } catch {
    return { post_id: postId, links: [] };
  }
}

async function loadPostNode(postId, event) {
  if (Number(event?.raw?.id) === Number(postId)) {
    return {
      id: postId,
      event_id: event.id,
      title: (event.raw.text_preview || event.title || `Пост ${postId}`).slice(0, 80),
      date: event.raw.date || event.started_at,
      views: event.raw.views || event.views || 0,
      comments_count: event.raw.comments_count || event.comments_count || 0,
      involvement: normalizeInvolvement(event.raw.involvement ?? event.involvement),
      channel_username: event.raw.channel_username || event.channel_username || channelUsernameById(event.raw.channel_id),
      text_preview: event.raw.text_preview || "",
      is_root: true,
    };
  }

  try {
    const post = await api(`/api/posts/${postId}`);
    return {
      id: post.id,
      event_id: event?.id || null,
      title: postTitleFromText(post.text, `Пост ${post.id}`),
      date: post.date,
      views: post.views || 0,
      comments_count: post.comments_count || 0,
      involvement: normalizeInvolvement(post.involvement),
      channel_username: channelUsernameById(post.channel_id),
      text_preview: (post.text || "").slice(0, 220),
      is_root: parsePostId(event?.root_post_id ?? event?.id) === post.id,
    };
  } catch {
    return null;
  }
}

async function collectGraphFromRoot(rootPostId, maxDepth = 1, maxNodes = 24) {
  const postIds = new Set([rootPostId]);
  const edges = [];
  const edgeKeys = new Set();
  let frontier = [rootPostId];

  for (let depth = 0; depth < maxDepth; depth += 1) {
    const next = [];
    const responses = await Promise.all(frontier.map((id) => loadPostLinks(id)));
    for (const payload of responses) {
      for (const link of payload.links || []) {
        const src = Number(link.src_post_id);
        const dst = Number(link.dst_post_id);
        if (!Number.isInteger(src) || !Number.isInteger(dst)) continue;

        const key = `${src}|${dst}|${link.link_type || ""}|${link.direction || ""}`;
        if (!edgeKeys.has(key)) {
          edgeKeys.add(key);
          edges.push({
            source: src,
            target: dst,
            relation_type: link.link_type || "related",
            relation_ru: link.link_type || "related",
            confidence: link.score,
          });
        }

        const other = src === payload.post_id ? dst : src;
        if (!postIds.has(other) && postIds.size < maxNodes) {
          postIds.add(other);
          next.push(other);
        }
      }
    }
    frontier = [...new Set(next)];
    if (!frontier.length) break;
  }

  return { postIds: [...postIds], edges };
}

async function loadEventGraph(event) {
  state.loadingGraph = true;
  el.graphSvg.innerHTML = "";
  el.timelineAxis.innerHTML = "";

  let posts = [];
  let edges = [];
  const rootId = parsePostId(event.root_post_id ?? event.id);

  if (event.source === "event") {
    try {
      const eventDetail = await api(`/api/links/events/${event.id}`);
      const eventPostIds = [...new Set(eventDetail.post_ids || [])].map((id) => Number(id)).filter((id) => Number.isInteger(id));
      const effectiveRoot = rootId || eventPostIds[0] || null;

      if (eventPostIds.length) {
        const linksByPost = await Promise.all(eventPostIds.map((id) => loadPostLinks(id)));
        const edgeKeys = new Set();
        const eventPostSet = new Set(eventPostIds);
        for (const payload of linksByPost) {
          for (const link of payload.links || []) {
            const src = Number(link.src_post_id);
            const dst = Number(link.dst_post_id);
            if (!eventPostSet.has(src) || !eventPostSet.has(dst)) continue;
            const key = `${src}|${dst}|${link.link_type || ""}|${link.direction || ""}`;
            if (edgeKeys.has(key)) continue;
            edgeKeys.add(key);
            edges.push({
              source: src,
              target: dst,
              relation_type: link.link_type || "related",
              relation_ru: link.link_type || "related",
              confidence: link.score,
            });
          }
        }

        const nodes = await Promise.all(eventPostIds.map((id) => loadPostNode(id, event)));
        posts = nodes.filter(Boolean).map((node) => ({
          ...node,
          is_root: effectiveRoot != null && Number(node.id) === Number(effectiveRoot),
        }));
      }
    } catch {
      // fallback to post-root based links
    }
  }

  if (!posts.length && rootId) {
    const graph = await collectGraphFromRoot(rootId, 1, 24);
    edges = graph.edges;
    const nodes = await Promise.all(graph.postIds.map((id) => loadPostNode(id, event)));
    posts = nodes.filter(Boolean).map((node) => ({
      ...node,
      is_root: Number(node.id) === Number(rootId),
    }));
  }

  if (!posts.length) {
    if (rootId) {
      const rootNode = await loadPostNode(rootId, event);
      if (rootNode) {
        posts = [{ ...rootNode, is_root: true }];
        edges = [];
      }
    }
  }

  if (!posts.length) {
    const mock = fallbackMockPostsForEvent(event);
    posts = mock.posts;
    edges = mock.edges;
  }

  state.eventPosts = posts.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
  state.eventEdges = edges;
  state.selectedPost = state.eventPosts.find((p) => p.is_root) || state.eventPosts[0];
  state.loadingGraph = false;
}

function renderTimeline(posts) {
  el.timelineAxis.innerHTML = "";
  if (!posts.length) return;
  const ticks = [];
  const min = new Date(posts[0].date).getTime();
  const max = new Date(posts[posts.length - 1].date).getTime();
  const span = Math.max(1, max - min);

  for (let i = 0; i < 6; i += 1) {
    const t = min + (span * i) / 5;
    ticks.push(new Date(t));
  }

  for (const tick of ticks) {
    const div = document.createElement("div");
    div.className = "timeline-tick";
    div.textContent = tick.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    el.timelineAxis.append(div);
  }
}

function fitGraphViewToContent(positions, nodeW, nodeH, canvasWidth, canvasHeight) {
  if (!positions.size) {
    state.graphView = { x: 0, y: 0, w: 1200, h: 620 };
    applyGraphViewBox();
    return;
  }

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const pos of positions.values()) {
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + nodeW);
    maxY = Math.max(maxY, pos.y + nodeH);
  }

  const padX = 120;
  const padY = 90;
  state.graphView = {
    x: clamp(minX - padX, -280, canvasWidth - 220),
    y: clamp(minY - padY, -200, canvasHeight - 200),
    w: clamp(maxX - minX + padX * 2, 560, canvasWidth),
    h: clamp(maxY - minY + padY * 2, 380, canvasHeight),
  };
  applyGraphViewBox();
}

function drawGraph(options = {}) {
  const autoFit = Boolean(options.autoFit);
  const posts = state.eventPosts;
  const edges = state.eventEdges;
  const relationType = el.relationFilter.value;
  const filteredEdges = relationType ? edges.filter((e) => String(e.relation_type).includes(relationType)) : edges;

  el.graphSvg.innerHTML = "";
  applyGraphViewBox();
  if (!posts.length) return;

  const width = 1200;
  const height = 620;
  const leftPad = 90;
  const rightPad = 90;
  const topPad = 70;
  const nodeW = 230;
  const nodeH = 140;

  const min = new Date(posts[0].date).getTime();
  const max = new Date(posts[posts.length - 1].date).getTime();
  const span = Math.max(1, max - min);
  const positions = new Map();

  posts.forEach((post, i) => {
    const t = new Date(post.date).getTime();
    const ratio = span ? (t - min) / span : i / Math.max(1, posts.length - 1);
    const x = leftPad + ratio * (width - leftPad - rightPad - nodeW);
    const row = i % 3;
    const y = topPad + row * 160;
    positions.set(post.id, { x, y });
  });

  for (let i = 0; i < 6; i += 1) {
    const guideX = leftPad + ((width - leftPad - rightPad) * i) / 5;
    const guide = document.createElementNS(NS, "line");
    guide.setAttribute("x1", String(guideX));
    guide.setAttribute("y1", "32");
    guide.setAttribute("x2", String(guideX));
    guide.setAttribute("y2", "560");
    guide.setAttribute("class", "graph-time-guide");
    el.graphSvg.append(guide);
  }

  filteredEdges.forEach((edge) => {
    const from = positions.get(edge.source);
    const to = positions.get(edge.target);
    if (!from || !to) return;

    const line = document.createElementNS(NS, "line");
    line.setAttribute("x1", String(from.x + nodeW));
    line.setAttribute("y1", String(from.y + nodeH / 2));
    line.setAttribute("x2", String(to.x));
    line.setAttribute("y2", String(to.y + nodeH / 2));
    line.setAttribute("class", "graph-edge");
    line.dataset.source = String(edge.source);
    line.dataset.target = String(edge.target);
    line.dataset.relation = edge.relation_type || "";
    line.onmouseenter = () => line.classList.add("active");
    line.onmouseleave = () => line.classList.remove("active");
    el.graphSvg.append(line);
  });

  posts.forEach((post) => {
    const pos = positions.get(post.id);
    if (!pos) return;

    const group = document.createElementNS(NS, "g");
    const rootClass = post.is_root ? " root" : "";
    const selectedClass = state.selectedPost?.id === post.id ? " selected" : "";
    group.setAttribute("class", `graph-node${rootClass}${selectedClass}`);
    group.style.cursor = "pointer";
    group.onclick = () => selectPost(post);

    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", String(pos.x));
    rect.setAttribute("y", String(pos.y));
    rect.setAttribute("width", String(nodeW));
    rect.setAttribute("height", String(nodeH));
    group.append(rect);

    const clipPath = document.createElementNS(NS, "clipPath");
    const clipId = `node-clip-${String(post.id).replace(/[^a-zA-Z0-9_-]/g, "_")}`;
    clipPath.setAttribute("id", clipId);
    const clipRect = document.createElementNS(NS, "rect");
    clipRect.setAttribute("x", String(pos.x + 8));
    clipRect.setAttribute("y", String(pos.y + 8));
    clipRect.setAttribute("width", String(nodeW - 16));
    clipRect.setAttribute("height", String(nodeH - 16));
    clipPath.append(clipRect);
    group.append(clipPath);

    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(pos.x + 12));
    title.setAttribute("y", String(pos.y + 25));
    title.setAttribute("clip-path", `url(#${clipId})`);
    title.textContent = truncateText(post.title || "", 28);
    group.append(title);

    const dateText = document.createElementNS(NS, "text");
    dateText.setAttribute("x", String(pos.x + 12));
    dateText.setAttribute("y", String(pos.y + 46));
    dateText.setAttribute("class", "meta");
    dateText.setAttribute("clip-path", `url(#${clipId})`);
    dateText.textContent = formatDate(post.date);
    group.append(dateText);

    const metrics = document.createElementNS(NS, "text");
    metrics.setAttribute("x", String(pos.x + 12));
    metrics.setAttribute("y", String(pos.y + 70));
    metrics.setAttribute("class", "meta");
    metrics.setAttribute("clip-path", `url(#${clipId})`);
    metrics.textContent = `👁 ${compact(post.views)} · 💬 ${compact(post.comments_count)} · ⚡ ${formatInvolvement(post.involvement)}`;
    group.append(metrics);

    const source = document.createElementNS(NS, "text");
    source.setAttribute("x", String(pos.x + 12));
    source.setAttribute("y", String(pos.y + 95));
    source.setAttribute("class", "meta");
    source.setAttribute("clip-path", `url(#${clipId})`);
    source.textContent = `Источник: @${truncateText(post.channel_username || "unknown", 16)}`;
    group.append(source);

    el.graphSvg.append(group);
  });

  if (autoFit) {
    fitGraphViewToContent(positions, nodeW, nodeH, width, height);
  }

  renderTimeline(posts);
}

function applyGraphViewBox() {
  const v = state.graphView;
  el.graphSvg.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
}

function zoomGraph(clientX, clientY, zoomIn) {
  const rect = el.graphSvg.getBoundingClientRect();
  const px = clamp((clientX - rect.left) / rect.width, 0, 1);
  const py = clamp((clientY - rect.top) / rect.height, 0, 1);
  const factor = zoomIn ? 0.88 : 1.12;
  const nextW = clamp(state.graphView.w * factor, 420, 2200);
  const nextH = clamp(state.graphView.h * factor, 260, 1400);
  const anchorX = state.graphView.x + state.graphView.w * px;
  const anchorY = state.graphView.y + state.graphView.h * py;
  state.graphView.x = anchorX - nextW * px;
  state.graphView.y = anchorY - nextH * py;
  state.graphView.w = nextW;
  state.graphView.h = nextH;
  applyGraphViewBox();
}

function initGraphInteractions() {
  el.graphSvg.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomGraph(event.clientX, event.clientY, event.deltaY < 0);
  });

  el.graphSvg.addEventListener("pointerdown", (event) => {
    const targetElement = event.target;
    if (targetElement && typeof targetElement.closest === "function" && targetElement.closest(".graph-node")) {
      return;
    }
    state.drag.active = true;
    state.drag.startX = event.clientX;
    state.drag.startY = event.clientY;
    state.drag.startViewX = state.graphView.x;
    state.drag.startViewY = state.graphView.y;
    el.graphSvg.setPointerCapture(event.pointerId);
  });

  el.graphSvg.addEventListener("pointermove", (event) => {
    if (!state.drag.active) return;
    const rect = el.graphSvg.getBoundingClientRect();
    const dx = ((event.clientX - state.drag.startX) / rect.width) * state.graphView.w;
    const dy = ((event.clientY - state.drag.startY) / rect.height) * state.graphView.h;
    state.graphView.x = state.drag.startViewX - dx;
    state.graphView.y = state.drag.startViewY - dy;
    applyGraphViewBox();
  });

  const stopDrag = (event) => {
    if (!state.drag.active) return;
    state.drag.active = false;
    if (event?.pointerId != null) {
      el.graphSvg.releasePointerCapture(event.pointerId);
    }
  };

  el.graphSvg.addEventListener("pointerup", stopDrag);
  el.graphSvg.addEventListener("pointercancel", stopDrag);
}

function renderDetails() {
  if (!state.selectedEvent || !state.selectedPost) {
    hideDetails();
    return;
  }

  showDetails();
  el.detailTitle.textContent = state.selectedEvent.title;
  el.detailDate.textContent = formatDate(state.selectedEvent.started_at);
  el.detailMetrics.innerHTML = `
    <span class="metric-pill">👁 ${compact(state.selectedEvent.views)}</span>
    <span class="metric-pill">💬 ${compact(state.selectedEvent.comments_count)}</span>
    <span class="metric-pill">⚡ ${formatInvolvement(state.selectedEvent.involvement)}</span>
    <span class="metric-pill">@${escapeHtml(state.selectedEvent.channel_username || "-")}</span>
  `;

  el.tabPosts.innerHTML = state.eventPosts
    .map(
      (post) => `
      <div class="post-link ${state.selectedPost?.id === post.id ? "active" : ""}" data-post-id="${escapeHtml(post.id)}">
        <strong>${escapeHtml(post.title || "Без заголовка")}</strong>
        <div class="source-line">${formatDate(post.date)} · @${escapeHtml(post.channel_username || "-")}</div>
        <div class="source-line">${escapeHtml((post.text_preview || "").slice(0, 180))}</div>
      </div>
    `,
    )
    .join("");

  [...el.tabPosts.querySelectorAll(".post-link")].forEach((node) => {
    node.onclick = () => {
      const post = state.eventPosts.find((p) => String(p.id) === node.dataset.postId);
      if (post) selectPost(post);
    };
  });

  if (state.comments.length) {
    el.tabComments.innerHTML = state.comments
      .slice(0, 200)
      .map(
        (comment) => `
          <div>
            <strong>${escapeHtml(comment.author_username || comment.author_id || "user")}:</strong>
            ${escapeHtml(comment.text || "")}
          </div>
          <hr />
        `,
      )
      .join("");
  } else {
    el.tabComments.innerHTML = "<div class='muted'>Комментарии не загружены.</div>";
  }

  el.tabReport.textContent = state.report?.content || "Мини-отчет пока недоступен.";

  const uniqueSources = [...new Set(state.eventPosts.map((p) => p.channel_username).filter(Boolean))];
  el.tabSources.innerHTML = uniqueSources.length
    ? uniqueSources.map((source) => `<div class="source-line">@${escapeHtml(source)}</div>`).join("")
    : "<div class='muted'>Источники не определены.</div>";

  activateTab(state.activeTab);
}

function activateTab(tab) {
  state.activeTab = tab;
  [...document.querySelectorAll(".tab")].forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
  const map = {
    posts: el.tabPosts,
    comments: el.tabComments,
    report: el.tabReport,
    sources: el.tabSources,
  };
  Object.entries(map).forEach(([key, panel]) => panel.classList.toggle("hidden", key !== tab));
}

async function loadComments(postId) {
  if (isSyntheticPostId(postId)) {
    state.comments = [];
    return;
  }
  try {
    state.comments = await api(`/api/posts/${postId}/comments`);
  } catch {
    state.comments = [];
  }
}

async function loadReport(postId) {
  if (isSyntheticPostId(postId)) {
    state.report = { status: "pending", content: "Отчет для синтетического узла недоступен." };
    return;
  }
  try {
    state.report = await api(`/api/reports/${postId}`);
  } catch {
    state.report = { status: "pending", content: "Отчет пока не сгенерирован." };
  }
}

async function selectPost(post) {
  state.selectedPost = post;
  await Promise.all([loadComments(post.id), loadReport(post.id)]);
  drawGraph({ autoFit: false });
  renderDetails();
  openDetailsPane();
}

async function selectEvent(event, opts = {}) {
  state.selectedEvent = event;
  renderEventsList();
  setStatus("");
  el.graphTitle.textContent = event.title;
  el.graphSubtitle.textContent = `${formatDate(event.started_at)} · @${event.channel_username || "unknown"}`;

  await loadEventGraph(event);
  drawGraph({ autoFit: true });
  await selectPost(state.selectedPost);
  renderDetails();
  if (!opts.silentOpen) openDetailsPane();
}

async function refreshCommentsForSelected() {
  const targetPostId = getActionablePostId();
  if (targetPostId == null) {
    setStatus("Для синтетического узла обновление комментариев недоступно.");
    return;
  }
  el.refreshCommentsBtn.disabled = true;
  setStatus("Обновляю комментарии...");
  try {
    const result = await api(`/api/posts/${targetPostId}/comments/update`, { method: "POST" });
    if (result?.status === "ok") {
      await loadComments(targetPostId);
      renderDetails();
      setStatus(`Комментарии обновлены: ${num(result.comments_saved || 0)}.`, true);
      return;
    }

    const status = result?.status || "unknown";
    if (status === "no_discussion") {
      setStatus("У поста нет дискуссионного треда в Telegram.");
    } else if (status === "entity_error") {
      setStatus("Не удалось получить сущность канала для обновления комментариев.");
    } else if (status === "flood_wait") {
      setStatus(`Telegram flood-wait: ${num(result.wait_seconds || 0)} сек.`);
    } else if (status === "rpc_error" || status === "discussion_error") {
      setStatus(`Ошибка Telegram API: ${status}.`);
    } else {
      setStatus(`Комментарии не обновлены: ${status}.`);
    }
  } catch (error) {
    setStatus(`Ошибка обновления комментариев: ${error.message}`);
  } finally {
    el.refreshCommentsBtn.disabled = false;
  }
}

async function regenerateReport() {
  const targetPostId = getActionablePostId();
  if (targetPostId == null) {
    setStatus("Для синтетического узла генерация отчета недоступна.");
    return;
  }
  el.generateReportBtn.disabled = true;
  setStatus("Обновляю отчет...");
  try {
    state.report = await api(`/api/reports/${targetPostId}/update`, { method: "POST" });
    await loadReport(targetPostId);
    renderDetails();
    setStatus("Отчет обновлен.", true);
  } catch (error) {
    setStatus(`Ошибка генерации отчета: ${error.message}`);
  } finally {
    el.generateReportBtn.disabled = false;
  }
}

async function copyMarkdown() {
  const text = state.report?.content || "";
  if (!text) return;
  await navigator.clipboard.writeText(text);
  setStatus("Markdown скопирован.", true);
}

function exportStub(type) {
  setStatus(`Экспорт ${type} будет подключен при добавлении backend-эндпоинта.`, true);
}

function toggleTheme() {
  document.body.classList.toggle("dark");
  const dark = document.body.classList.contains("dark");
  el.themeToggle.textContent = dark ? "☀" : "☾";
}

function bind() {
  el.applyBtn.onclick = () => loadEvents();
  el.resetBtn.onclick = () => {
    initDates();
    el.minComments.value = "0";
    el.topLimit.value = "25";
    el.categoryFilter.value = "";
    [...el.channelFilter.options].forEach((opt) => {
      opt.selected = false;
    });
    renderChannelDropdownOptions();
    el.channelDropdownMenu.classList.add("hidden");
    el.eventsSearch.value = "";
    loadEvents();
  };

  el.eventsSearch.oninput = () => {
    applyFiltersAndRender();
  };
  el.channelFilter.onchange = () => applyFiltersAndRender();
  el.categoryFilter.onchange = () => applyFiltersAndRender();
  el.minComments.oninput = () => applyFiltersAndRender();
  el.relationFilter.onchange = () => drawGraph({ autoFit: true });
  el.fitViewBtn.onclick = () => {
    drawGraph({ autoFit: true });
    setStatus("Граф центрирован.", true);
  };
  el.refreshCommentsBtn.onclick = refreshCommentsForSelected;
  el.generateReportBtn.onclick = regenerateReport;
  el.copyMdBtn.onclick = copyMarkdown;
  el.exportPdfBtn.onclick = () => exportStub("PDF");
  el.exportDocxBtn.onclick = () => exportStub("DOCX");
  el.themeToggle.onclick = toggleTheme;
  el.detailsToggle.onclick = openDetailsPane;
  el.closeDetailsBtn.onclick = closeDetailsPane;
  el.channelDropdownBtn.onclick = () => {
    el.channelDropdownMenu.classList.toggle("hidden");
  };
  document.addEventListener("click", (event) => {
    if (!el.channelDropdown.contains(event.target)) {
      el.channelDropdownMenu.classList.add("hidden");
    }
  });

  [...document.querySelectorAll(".tab")].forEach((btn) => {
    btn.onclick = () => activateTab(btn.dataset.tab);
  });
}

async function init() {
  initDates();
  bind();
  initGraphInteractions();
  applyGraphViewBox();
  await loadChannels();
  await loadEvents();
}

init().catch((error) => {
  el.eventsList.innerHTML = `<div class='muted'>Критическая ошибка инициализации: ${escapeHtml(error.message)}</div>`;
});
