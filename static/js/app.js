const state = {
  items: [],
  groupedByOrigin: {},
  selectedOrigin: 'youtube_video',
  selectedContentId: null,
  channels: [],
  blogs: [],
  selectedChannel: null,
  selectedBlog: null,
  youtubeSort: { key: 'date', dir: 'desc' },
  channelSort: { key: 'date', dir: 'desc' },
  blogSort: { key: 'date', dir: 'desc' },
  statusPollers: {},
  promptCache: {},
  promptKeys: [],
};

const SOURCE_OPTIONS = ['youtube_video', 'youtube_channel', 'blog', 'settings'];

const ORIGIN_LABELS = {
  youtube_video: 'Individual YouTube',
  youtube_channel: 'YouTube Channels',
  blog: 'Blogs',
  blog_article: 'Blogs',
  settings: 'Settings',
};

const loadingOverlay = document.getElementById('loading-overlay');
const searchInput = document.getElementById('search-input');
const sourceList = document.getElementById('source-list');
const summaryList = document.getElementById('summary-list');
const emptyState = document.getElementById('empty-state');
const summarySection = document.querySelector('.summary-section');
const toastContainer = document.getElementById('toast-container');
const channelSection = document.getElementById('channel-section');
const channelList = document.getElementById('channel-list');
const blogSection = document.getElementById('blog-section');
const blogList = document.getElementById('blog-list');
const settingsPanel = document.getElementById('settings-panel');
const settingsSave = document.getElementById('settings-save');
const settingsStatus = document.getElementById('settings-status');
const openaiApiKey = document.getElementById('openai-api-key');
const openaiApiKeyHint = document.getElementById('openai-api-key-hint');
const openaiModel = document.getElementById('openai-model');
const openaiModelCustom = document.getElementById('openai-model-custom');
const promptKeySelect = document.getElementById('prompt-key');
const promptSystem = document.getElementById('prompt-system');
const promptUser = document.getElementById('prompt-user');
const promptSave = document.getElementById('prompt-save');
const promptStatus = document.getElementById('prompt-status');

async function fetchJson(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const payload = await response.json();
    return { response, payload };
  } finally {
    window.clearTimeout(timer);
  }
}

async function loadData() {
  showLoading();
  try {
    const [itemsResult, channelsResult, blogsResult, settingsResult, promptKeysResult] = await Promise.all([
      fetchJson('/api/items'),
      fetchJson('/api/channels'),
      fetchJson('/api/blogs'),
      fetchJson('/api/settings'),
      fetchJson('/api/prompts'),
    ]);
    const payload = itemsResult.payload;
    const channelsPayload = channelsResult.response.ok ? channelsResult.payload : { channels: [] };
    const blogsPayload = blogsResult.response.ok ? blogsResult.payload : { blogs: [] };
    const settingsPayload = settingsResult.response.ok ? settingsResult.payload : { openai_model: null, has_api_key: false };
    const promptKeysPayload = promptKeysResult.response.ok ? promptKeysResult.payload : { keys: [] };

    state.items = payload.items || [];
    state.groupedByOrigin = payload.grouped_origin || {};
    state.channels = channelsPayload.channels || [];
    state.blogs = blogsPayload.blogs || [];
    state.promptKeys = promptKeysPayload.keys || [];

    renderSources();
    renderStats(payload.stats || {});
    renderChannels();
    renderBlogs();
    renderList();
    hydrateSettings(settingsPayload);
    hydratePromptKeys();
    refreshPromptEditor();
  } catch (error) {
    console.error('Failed to load items', error);
    alert('Failed to load items. Check the server logs for details.');
  } finally {
    hideLoading();
  }
}

async function refreshPromptEditor() {
  if (!settingsPanel) return;
  if (state.selectedOrigin !== 'settings') {
    return;
  }
  const key = promptKeySelect?.value || 'youtube_video';
  if (state.promptCache[key]) {
    fillPromptEditor(state.promptCache[key]);
    return;
  }
  try {
    const { response, payload } = await fetchJson(`/api/prompts/${key}`);
    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || 'Unable to load prompt.');
    }
    state.promptCache[key] = payload;
    fillPromptEditor(payload);
  } catch (error) {
    console.error('Failed to load prompt', error);
  }
}

function fillPromptEditor(payload) {
  if (!promptSystem || !promptUser) return;
  const override = payload.override || {};
  const base = payload.default || {};
  promptSystem.value = override.system || base.system || '';
  promptUser.value = override.user || base.user || '';
}

async function savePromptEditor() {
  if (!promptSystem || !promptUser || !promptSave) return;
  const key = promptKeySelect?.value || 'youtube_video';
  const system = promptSystem.value.trim();
  const user = promptUser.value.trim();
  if (!system || !user) {
    showPromptStatus('Both system and user prompts are required.', 'warning');
    return;
  }
  promptSave.disabled = true;
  showPromptStatus('Saving…', 'info');
  try {
    const response = await fetch(`/api/prompts/${key}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system, user }),
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || 'Unable to save prompt.');
    }
    state.promptCache[key] = {
      status: 'ok',
      default: state.promptCache[key]?.default,
      override: payload.override,
    };
    showPromptStatus('Prompt updated. New summaries will use the latest version.', 'success');
  } catch (error) {
    console.error('Failed to save prompt', error);
    showPromptStatus(error.message || 'Failed to save prompt.', 'warning');
  } finally {
    promptSave.disabled = false;
  }
}

function showPromptStatus(message, tone) {
  if (!promptStatus) return;
  promptStatus.textContent = message;
  promptStatus.className = `prompt-status ${tone || ''}`.trim();
}

async function saveSettings() {
  if (!settingsSave || !openaiModel) return;
  const modelValue = openaiModel.value === 'custom' ? openaiModelCustom.value.trim() : openaiModel.value;
  const apiKey = openaiApiKey?.value.trim() || '';
  if (!modelValue) {
    showSettingsStatus('Model is required.', 'warning');
    return;
  }
  settingsSave.disabled = true;
  showSettingsStatus('Saving…', 'info');
  try {
    const response = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ openai_model: modelValue, openai_api_key: apiKey }),
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || 'Unable to save settings.');
    }
    showSettingsStatus('Settings updated.', 'success');
    if (openaiApiKey) {
      openaiApiKey.value = '';
    }
  } catch (error) {
    console.error('Failed to save settings', error);
    showSettingsStatus(error.message || 'Failed to save settings.', 'warning');
  } finally {
    settingsSave.disabled = false;
  }
}

function showSettingsStatus(message, tone) {
  if (!settingsStatus) return;
  settingsStatus.textContent = message;
  settingsStatus.className = `prompt-status ${tone || ''}`.trim();
}

function renderSources() {
  if (!sourceList) return;
  sourceList.innerHTML = '';

  const availableOrigins = SOURCE_OPTIONS;

  if (!availableOrigins.includes(state.selectedOrigin)) {
    const fallback = availableOrigins.find((origin) => (state.groupedByOrigin[origin] || []).length) || availableOrigins[0];
    state.selectedOrigin = fallback;
  }

  availableOrigins.forEach((origin) => {
    const li = document.createElement('li');
    li.dataset.origin = origin;
    if (origin !== 'settings' && !(state.groupedByOrigin[origin] || []).length) {
      li.classList.add('empty');
    }
    if (origin === state.selectedOrigin) {
      li.classList.add('active');
    }
    const label = document.createElement('span');
    label.textContent = ORIGIN_LABELS[origin] || titleCase(origin.replace('_', ' '));
    li.appendChild(label);

    if (origin !== 'settings') {
      const addBtn = document.createElement('button');
      addBtn.className = 'source-add';
      addBtn.type = 'button';
      addBtn.textContent = '+';
      addBtn.title = `Add ${ORIGIN_LABELS[origin] || titleCase(origin)}`;
      addBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        addSourceUrl(origin);
      });
      li.appendChild(addBtn);
    }

    li.addEventListener('click', () => {
      state.selectedOrigin = origin;
      renderSources();
      renderChannels();
      renderBlogs();
      renderList();
      refreshPromptEditor();
    });

    sourceList.appendChild(li);
  });
}

function renderStats(stats) {
  const total = document.getElementById('stat-total');
  const latest = document.getElementById('stat-latest');
  const origins = document.getElementById('stat-origins');

  if (total) total.textContent = stats.total_items ?? '--';
  if (latest) latest.textContent = stats.latest_published_at ?? '--';

  if (origins) {
    origins.innerHTML = '';
    const data = stats.by_origin || {};
    Object.entries(data).forEach(([origin, count]) => {
      const li = document.createElement('li');
      li.className = 'stat-pill';
      li.textContent = `${ORIGIN_LABELS[origin] || titleCase(origin)} ${count}`;
      origins.appendChild(li);
    });
  }
}

function renderChannels() {
  if (!channelSection || !channelList) return;
  if (state.selectedOrigin !== 'youtube_channel') {
    channelSection.style.display = 'none';
    state.selectedChannel = null;
    return;
  }
  channelSection.style.display = 'block';
  channelList.innerHTML = '';

  const allItem = document.createElement('li');
  allItem.textContent = 'All channels';
  allItem.className = 'channel-pill channel-all';
  if (!state.selectedChannel) {
    allItem.classList.add('active');
  }
  allItem.addEventListener('click', () => {
    state.selectedChannel = null;
    renderChannels();
    renderList();
  });
  channelList.appendChild(allItem);

  if (!state.channels.length) {
    const empty = document.createElement('li');
    empty.textContent = 'No channels found in reading list.';
    channelList.appendChild(empty);
    return;
  }

  state.channels.forEach((channel) => {
    const li = document.createElement('li');
    li.className = 'channel-pill';
    if (state.selectedChannel === channel.name) {
      li.classList.add('active');
    }
    li.textContent = channel.name;

    li.addEventListener('click', (event) => {
      event.preventDefault();
      state.selectedChannel = state.selectedChannel === channel.name ? null : channel.name;
      renderChannels();
      renderList();
    });

    channelList.appendChild(li);
  });
}

function renderBlogs() {
  if (!blogSection || !blogList) return;
  if (state.selectedOrigin !== 'blog') {
    blogSection.style.display = 'none';
    state.selectedBlog = null;
    return;
  }
  blogSection.style.display = 'block';
  blogList.innerHTML = '';

  const allItem = document.createElement('li');
  allItem.textContent = 'All sites';
  allItem.className = 'channel-pill channel-all';
  if (!state.selectedBlog) {
    allItem.classList.add('active');
  }
  allItem.addEventListener('click', () => {
    state.selectedBlog = null;
    renderBlogs();
    renderList();
  });
  blogList.appendChild(allItem);

  if (!state.blogs.length) {
    const empty = document.createElement('li');
    empty.textContent = 'No blog sites found in reading list.';
    blogList.appendChild(empty);
    return;
  }

  state.blogs.forEach((blog) => {
    const li = document.createElement('li');
    li.className = 'channel-pill';
    if (state.selectedBlog === blog.site_key) {
      li.classList.add('active');
    }
    li.textContent = blog.name;
    li.addEventListener('click', (event) => {
      event.preventDefault();
      state.selectedBlog = state.selectedBlog === blog.site_key ? null : blog.site_key;
      renderBlogs();
      renderList();
    });
    blogList.appendChild(li);
  });
}

function hydrateSettings(payload) {
  if (!openaiApiKey || !openaiModel) return;
  if (payload?.openai_model) {
    const hasOption = [...openaiModel.options].some((opt) => opt.value === payload.openai_model);
    if (hasOption) {
      openaiModel.value = payload.openai_model;
      openaiModelCustom.value = '';
    } else {
      openaiModel.value = 'custom';
      openaiModelCustom.value = payload.openai_model;
    }
  }
  if (openaiModelCustom) {
    openaiModelCustom.style.display = openaiModel.value === 'custom' ? 'block' : 'none';
  }
  if (openaiApiKeyHint) {
    openaiApiKeyHint.textContent = payload?.has_api_key
      ? 'API key set. Enter a new one to replace it.'
      : 'No API key stored yet.';
  }
}

function hydratePromptKeys() {
  if (!promptKeySelect) return;
  promptKeySelect.innerHTML = '';
  const keys = state.promptKeys.length ? state.promptKeys : ['youtube_video', 'blog_post'];
  keys.forEach((key) => {
    const option = document.createElement('option');
    option.value = key;
    option.textContent = titleCase(key.replace('_', ' '));
    promptKeySelect.appendChild(option);
  });
  if (!promptKeySelect.value && keys.length) {
    promptKeySelect.value = keys[0];
  }
}

function renderList() {
  if (!summaryList) return;
  const panelTitle = document.getElementById('panel-title');
  const panelSubtitle = document.getElementById('panel-subtitle');

  const origin = state.selectedOrigin;
  const originLabel = ORIGIN_LABELS[origin] || titleCase(origin);

  if (panelTitle) panelTitle.textContent = originLabel;

  if (origin === 'settings') {
    if (summarySection) summarySection.style.display = 'none';
    if (settingsPanel) settingsPanel.style.display = 'block';
    if (panelSubtitle) panelSubtitle.textContent = 'Configure models, prompts, and API credentials';
    return;
  }

  if (settingsPanel) settingsPanel.style.display = 'none';
  if (summarySection) summarySection.style.display = 'block';

  let items = state.items.filter((item) => (item.origin || item.source_type) === origin);

  const query = (searchInput?.value || '').toLowerCase().trim();
  if (query) {
    items = items.filter((item) => {
      const haystack = [
        item.title,
        item.author,
        item.source_type,
        (item.tags || []).join(' '),
        (item.categories || []).join(' '),
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    });
  }

  if (origin === 'youtube_channel' && state.selectedChannel) {
    items = items.filter((item) => item.author === state.selectedChannel);
  }
  if (origin === 'blog' && state.selectedBlog) {
    items = items.filter((item) => item.site_key === state.selectedBlog);
  }

  if (panelSubtitle) {
    let suffix = 'sorted by latest';
    if (origin === 'youtube_video') {
      suffix = `sorted by ${state.youtubeSort.key} (${state.youtubeSort.dir})`;
    } else if (origin === 'youtube_channel') {
      suffix = `sorted by ${state.channelSort.key} (${state.channelSort.dir})`;
    } else if (origin === 'blog') {
      suffix = `sorted by ${state.blogSort.key} (${state.blogSort.dir})`;
    }
    panelSubtitle.textContent = items.length
      ? `${items.length} item${items.length === 1 ? '' : 's'} ${suffix}`
      : 'No items available';
  }

  summaryList.innerHTML = '';
  if (!items.length) {
    if (emptyState) emptyState.style.display = 'block';
    return;
  }
  if (emptyState) emptyState.style.display = 'none';

  if (!items.find((item) => item.content_id === state.selectedContentId)) {
    state.selectedContentId = items[0].content_id;
  }

  if (origin === 'youtube_video') {
    renderVideoTable(items);
  } else if (origin === 'youtube_channel') {
    renderChannelTable(items);
  } else {
    renderBlogTable(items);
  }
}

function createIconButton({ label, icon, action, onClick, tone }) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `icon-btn${tone ? ` icon-btn-${tone}` : ''}`;
  button.dataset.action = action;
  button.dataset.label = label;
  button.dataset.tooltip = label;
  button.dataset.icon = icon;
  button.innerHTML = `<i class="${icon}"></i>`;
  if (onClick) {
    button.onclick = onClick;
  }
  return button;
}

function setIconButtonState(button, { label, icon, spinning = false }) {
  const nextIcon = icon || button.dataset.icon || 'fas fa-circle';
  button.dataset.label = label;
  button.dataset.tooltip = label;
  button.innerHTML = `<i class="${nextIcon}${spinning ? ' fa-spin' : ''}"></i>`;
  button.dataset.icon = nextIcon;
}

function getTagColor(tag) {
  let hash = 0;
  for (let i = 0; i < tag.length; i += 1) {
    hash = (hash * 31 + tag.charCodeAt(i)) % 360;
  }
  const hue = hash;
  return {
    background: `hsl(${hue} 70% 88%)`,
    text: `hsl(${hue} 35% 28%)`,
  };
}

function renderTagCell(tagCell, tags) {
  const cleanTags = (tags || []).filter(Boolean);
  if (!cleanTags.length) {
    tagCell.textContent = '--';
    return;
  }
  const wrapper = document.createElement('div');
  wrapper.className = 'tag-list';
  cleanTags.slice(0, 6).forEach((tag) => {
    const pill = document.createElement('span');
    const colors = getTagColor(tag);
    pill.className = 'tag-pill';
    pill.textContent = tag;
    pill.style.backgroundColor = colors.background;
    pill.style.color = colors.text;
    wrapper.appendChild(pill);
  });
  tagCell.appendChild(wrapper);
}

function renderVideoTable(items) {
  summaryList.innerHTML = '';
  const table = document.createElement('table');
  table.className = 'video-table';

  const thead = document.createElement('thead');
  thead.innerHTML = `
    <tr>
      <th data-sort="date" class="sortable">Date</th>
      <th data-sort="title" class="sortable">Title</th>
      <th data-sort="channel" class="sortable">Channel</th>
      <th>Tags</th>
      <th>Actions</th>
    </tr>
  `;
  table.appendChild(thead);

  const sortableHeaders = thead.querySelectorAll('.sortable');
  sortableHeaders.forEach((header) => {
    const key = header.dataset.sort;
    if (state.youtubeSort.key === key) {
      header.classList.add(state.youtubeSort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
    header.addEventListener('click', () => {
      if (state.youtubeSort.key === key) {
        state.youtubeSort.dir = state.youtubeSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.youtubeSort.key = key;
        state.youtubeSort.dir = 'asc';
      }
      renderList();
    });
  });

  items = sortYouTubeItems(items);

  const tbody = document.createElement('tbody');
  items.forEach((item) => {
    const row = document.createElement('tr');
    row.className = 'video-row';
    row.dataset.contentId = item.content_id;
    if (item.content_id === state.selectedContentId) {
      row.classList.add('selected');
    }

    const dateCell = document.createElement('td');
    dateCell.textContent = item.published_display;

    const titleCell = document.createElement('td');
    const titleLink = document.createElement('a');
    titleLink.href = item.original_url;
    titleLink.target = '_blank';
    titleLink.rel = 'noopener';
    titleLink.textContent = item.title;
    titleLink.className = 'summary-title';
    titleCell.appendChild(titleLink);

    const channelCell = document.createElement('td');
    if (item.author) {
      if (item.channel_url) {
        const channelLink = document.createElement('a');
        channelLink.href = item.channel_url;
        channelLink.target = '_blank';
        channelLink.rel = 'noopener';
        channelLink.textContent = item.author;
        channelCell.appendChild(channelLink);
      } else {
        channelCell.textContent = item.author;
      }
    } else {
      channelCell.textContent = '--';
    }

    const tagCell = document.createElement('td');
    renderTagCell(tagCell, item.tags || []);

    const actionsCell = document.createElement('td');
    const actions = document.createElement('div');
    actions.className = 'summary-actions';

    const body = document.createElement('div');
    body.className = 'summary-body';
    body.dataset.contentId = item.content_id;
    body.innerHTML = renderSummaryHtml(item.summary);
    if (item.summary) {
      body.classList.add('collapsed');
    }

    const detailRow = document.createElement('tr');
    detailRow.className = 'video-detail';
    detailRow.dataset.contentId = item.content_id;
    const detailCell = document.createElement('td');
    detailCell.colSpan = 5;
    detailCell.appendChild(body);
    detailRow.appendChild(detailCell);

    const hasSummary = Boolean(item.summary);
    const transcriptAvailable = item.transcript_available !== false;
    const transcriptError = item.transcript_error || null;

    const shouldShowSummaryBtn = hasSummary || transcriptAvailable;
    if (shouldShowSummaryBtn) {
      const summaryBtn = createIconButton({
        label: hasSummary ? 'Summary' : 'Summarize',
        icon: 'fas fa-align-left',
        action: hasSummary ? 'toggle-summary' : 'summarize',
        onClick: hasSummary
          ? () => toggleSummary(body, summaryBtn, true, detailRow)
          : () => triggerSummarization(item.content_id, summaryBtn, { isInitial: true }),
      });
      summaryBtn.dataset.contentId = item.content_id;
      actions.appendChild(summaryBtn);
    }

    if (hasSummary) {
      const regenBtn = createIconButton({
        label: 'Re-summarize',
        icon: 'fas fa-rotate-right',
        action: 'regenerate-summary',
        tone: 'accent',
        onClick: () => triggerSummarization(item.content_id, regenBtn),
      });
      regenBtn.dataset.contentId = item.content_id;
      actions.appendChild(regenBtn);
    }

    if (!transcriptAvailable && item.source_type === 'youtube_video') {
      const fetchBtn = createIconButton({
        label: 'Fetch transcript',
        icon: 'fas fa-file-lines',
        action: 'fetch-transcript',
        onClick: () => triggerTranscriptFetch(item.content_id, fetchBtn),
      });
      fetchBtn.dataset.contentId = item.content_id;
      actions.appendChild(fetchBtn);
    }

    const tagBtn = createIconButton({
      label: 'Edit tags',
      icon: 'fas fa-tag',
      action: 'edit-tags',
      onClick: () => editTags(item),
    });
    tagBtn.dataset.contentId = item.content_id;
    actions.appendChild(tagBtn);

    const status = document.createElement('div');
    status.className = 'status';
    status.dataset.statusFor = item.content_id;
    if (!transcriptAvailable && transcriptError !== 'Transcript not downloaded. Fetch one at a time before summarizing.') {
      status.textContent = transcriptError || 'Transcript unavailable.';
    }
    actions.appendChild(status);

    actionsCell.appendChild(actions);

    row.appendChild(dateCell);
    row.appendChild(titleCell);
    row.appendChild(channelCell);
    row.appendChild(tagCell);
    row.appendChild(actionsCell);

    row.addEventListener('click', (event) => {
      if (event.target.closest('button') || event.target.closest('a')) {
        return;
      }
      setSelectedItem(item.content_id);
    });

    tbody.appendChild(row);
    tbody.appendChild(detailRow);
  });

  table.appendChild(tbody);
  summaryList.appendChild(table);
}

function sortYouTubeItems(items) {
  const { key, dir } = state.youtubeSort;
  const multiplier = dir === 'asc' ? 1 : -1;
  return [...items].sort((a, b) => {
    if (key === 'date') {
      return a.published_sort_key < b.published_sort_key ? 1 * multiplier : -1 * multiplier;
    }
    if (key === 'title') {
      return (a.title || '').localeCompare(b.title || '') * multiplier;
    }
    if (key === 'channel') {
      return (a.author || '').localeCompare(b.author || '') * multiplier;
    }
    return 0;
  });
}

function sortChannelItems(items) {
  const { key, dir } = state.channelSort;
  const multiplier = dir === 'asc' ? 1 : -1;
  return [...items].sort((a, b) => {
    if (key === 'date') {
      return a.published_sort_key < b.published_sort_key ? 1 * multiplier : -1 * multiplier;
    }
    if (key === 'title') {
      return (a.title || '').localeCompare(b.title || '') * multiplier;
    }
    if (key === 'channel') {
      return (a.author || '').localeCompare(b.author || '') * multiplier;
    }
    return 0;
  });
}

function sortBlogItems(items) {
  const { key, dir } = state.blogSort;
  const multiplier = dir === 'asc' ? 1 : -1;
  return [...items].sort((a, b) => {
    if (key === 'date') {
      return a.published_sort_key < b.published_sort_key ? 1 * multiplier : -1 * multiplier;
    }
    if (key === 'title') {
      return (a.title || '').localeCompare(b.title || '') * multiplier;
    }
    if (key === 'site') {
      return (a.site_name || '').localeCompare(b.site_name || '') * multiplier;
    }
    return 0;
  });
}

function renderChannelTable(items) {
  summaryList.innerHTML = '';
  const table = document.createElement('table');
  table.className = 'video-table channel-table';

  const thead = document.createElement('thead');
  thead.innerHTML = `
    <tr>
      <th data-sort="date" class="sortable">Date</th>
      <th data-sort="title" class="sortable">Video</th>
      <th data-sort="channel" class="sortable">Channel</th>
      <th>Tags</th>
      <th>Actions</th>
    </tr>
  `;
  table.appendChild(thead);

  const sortableHeaders = thead.querySelectorAll('.sortable');
  sortableHeaders.forEach((header) => {
    const key = header.dataset.sort;
    if (state.channelSort.key === key) {
      header.classList.add(state.channelSort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
    header.addEventListener('click', () => {
      if (state.channelSort.key === key) {
        state.channelSort.dir = state.channelSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.channelSort.key = key;
        state.channelSort.dir = 'asc';
      }
      renderList();
    });
  });

  items = sortChannelItems(items);

  const tbody = document.createElement('tbody');
  items.forEach((item) => {
    const row = document.createElement('tr');
    row.className = 'video-row';
    row.dataset.contentId = item.content_id;
    if (item.content_id === state.selectedContentId) {
      row.classList.add('selected');
    }

    const dateCell = document.createElement('td');
    dateCell.textContent = item.published_display;

    const titleCell = document.createElement('td');
    const titleLink = document.createElement('a');
    titleLink.href = item.original_url;
    titleLink.target = '_blank';
    titleLink.rel = 'noopener';
    titleLink.textContent = item.title;
    titleLink.className = 'summary-title';
    titleCell.appendChild(titleLink);

    const channelCell = document.createElement('td');
    channelCell.textContent = item.author || '--';

    const tagCell = document.createElement('td');
    renderTagCell(tagCell, item.tags || []);

    const actionsCell = document.createElement('td');
    const actions = document.createElement('div');
    actions.className = 'summary-actions';

    const body = document.createElement('div');
    body.className = 'summary-body';
    body.dataset.contentId = item.content_id;
    body.innerHTML = renderSummaryHtml(item.summary);
    if (item.summary) {
      body.classList.add('collapsed');
    }

    const detailRow = document.createElement('tr');
    detailRow.className = 'video-detail';
    detailRow.dataset.contentId = item.content_id;
    const detailCell = document.createElement('td');
    detailCell.colSpan = 5;
    detailCell.appendChild(body);
    detailRow.appendChild(detailCell);

    const hasSummary = Boolean(item.summary);
    const transcriptAvailable = item.transcript_available !== false;
    const transcriptError = item.transcript_error || null;

    const shouldShowSummaryBtn = hasSummary || transcriptAvailable;
    if (shouldShowSummaryBtn) {
      const summaryBtn = createIconButton({
        label: hasSummary ? 'Summary' : 'Summarize',
        icon: 'fas fa-align-left',
        action: hasSummary ? 'toggle-summary' : 'summarize',
        onClick: hasSummary
          ? () => toggleSummary(body, summaryBtn, true, detailRow)
          : () => triggerSummarization(item.content_id, summaryBtn, { isInitial: true }),
      });
      summaryBtn.dataset.contentId = item.content_id;
      actions.appendChild(summaryBtn);
    }

    if (hasSummary) {
      const regenBtn = createIconButton({
        label: 'Re-summarize',
        icon: 'fas fa-rotate-right',
        action: 'regenerate-summary',
        tone: 'accent',
        onClick: () => triggerSummarization(item.content_id, regenBtn),
      });
      regenBtn.dataset.contentId = item.content_id;
      actions.appendChild(regenBtn);
    }

    if (!transcriptAvailable && item.source_type === 'youtube_video') {
      const fetchBtn = createIconButton({
        label: 'Fetch transcript',
        icon: 'fas fa-file-lines',
        action: 'fetch-transcript',
        onClick: () => triggerTranscriptFetch(item.content_id, fetchBtn),
      });
      fetchBtn.dataset.contentId = item.content_id;
      actions.appendChild(fetchBtn);
    }

    const tagBtn = createIconButton({
      label: 'Edit tags',
      icon: 'fas fa-tag',
      action: 'edit-tags',
      onClick: () => editTags(item),
    });
    tagBtn.dataset.contentId = item.content_id;
    actions.appendChild(tagBtn);

    const status = document.createElement('div');
    status.className = 'status';
    status.dataset.statusFor = item.content_id;
    if (!transcriptAvailable && transcriptError !== 'Transcript not downloaded. Fetch one at a time before summarizing.') {
      status.textContent = transcriptError || 'Transcript unavailable.';
    }
    actions.appendChild(status);

    actionsCell.appendChild(actions);

    row.appendChild(dateCell);
    row.appendChild(titleCell);
    row.appendChild(channelCell);
    row.appendChild(tagCell);
    row.appendChild(actionsCell);

    row.addEventListener('click', (event) => {
      if (event.target.closest('button') || event.target.closest('a')) {
        return;
      }
      setSelectedItem(item.content_id);
    });

    tbody.appendChild(row);
    tbody.appendChild(detailRow);
  });

  table.appendChild(tbody);
  summaryList.appendChild(table);
}

function renderBlogTable(items) {
  summaryList.innerHTML = '';
  const table = document.createElement('table');
  table.className = 'video-table blog-table';

  const thead = document.createElement('thead');
  thead.innerHTML = `
    <tr>
      <th data-sort="date" class="sortable">Date</th>
      <th data-sort="title" class="sortable">Title</th>
      <th data-sort="site" class="sortable">Site</th>
      <th>Tags</th>
      <th>Actions</th>
    </tr>
  `;
  table.appendChild(thead);

  const sortableHeaders = thead.querySelectorAll('.sortable');
  sortableHeaders.forEach((header) => {
    const key = header.dataset.sort;
    if (state.blogSort.key === key) {
      header.classList.add(state.blogSort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
    header.addEventListener('click', () => {
      if (state.blogSort.key === key) {
        state.blogSort.dir = state.blogSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.blogSort.key = key;
        state.blogSort.dir = 'asc';
      }
      renderList();
    });
  });

  items = sortBlogItems(items);

  const tbody = document.createElement('tbody');
  items.forEach((item) => {
    const row = document.createElement('tr');
    row.className = 'video-row';
    row.dataset.contentId = item.content_id;
    if (item.content_id === state.selectedContentId) {
      row.classList.add('selected');
    }

    const dateCell = document.createElement('td');
    dateCell.textContent = item.published_display;

    const titleCell = document.createElement('td');
    const titleLink = document.createElement('a');
    titleLink.href = item.original_url;
    titleLink.target = '_blank';
    titleLink.rel = 'noopener';
    titleLink.textContent = item.title;
    titleLink.className = 'summary-title';
    titleCell.appendChild(titleLink);

    const siteCell = document.createElement('td');
    siteCell.textContent = item.site_name || '--';

    const tagCell = document.createElement('td');
    renderTagCell(tagCell, item.tags || []);

    const actionsCell = document.createElement('td');
    const actions = document.createElement('div');
    actions.className = 'summary-actions';

    const body = document.createElement('div');
    body.className = 'summary-body';
    body.dataset.contentId = item.content_id;
    body.innerHTML = renderSummaryHtml(item.summary);
    if (item.summary) {
      body.classList.add('collapsed');
    }

    const detailRow = document.createElement('tr');
    detailRow.className = 'video-detail';
    detailRow.dataset.contentId = item.content_id;
    const detailCell = document.createElement('td');
    detailCell.colSpan = 5;
    detailCell.appendChild(body);
    detailRow.appendChild(detailCell);

    const hasSummary = Boolean(item.summary);

    const summaryBtn = createIconButton({
      label: hasSummary ? 'Summary' : 'Summarize',
      icon: 'fas fa-align-left',
      action: hasSummary ? 'toggle-summary' : 'summarize',
      onClick: hasSummary
        ? () => toggleSummary(body, summaryBtn, true, detailRow)
        : () => triggerSummarization(item.content_id, summaryBtn, { isInitial: true }),
    });
    summaryBtn.dataset.contentId = item.content_id;
    actions.appendChild(summaryBtn);

    if (hasSummary) {
      const regenBtn = createIconButton({
        label: 'Re-summarize',
        icon: 'fas fa-rotate-right',
        action: 'regenerate-summary',
        tone: 'accent',
        onClick: () => triggerSummarization(item.content_id, regenBtn),
      });
      regenBtn.dataset.contentId = item.content_id;
      actions.appendChild(regenBtn);
    }

    const tagBtn = createIconButton({
      label: 'Edit tags',
      icon: 'fas fa-tag',
      action: 'edit-tags',
      onClick: () => editTags(item),
    });
    tagBtn.dataset.contentId = item.content_id;
    actions.appendChild(tagBtn);

    const status = document.createElement('div');
    status.className = 'status';
    status.dataset.statusFor = item.content_id;
    actions.appendChild(status);

    actionsCell.appendChild(actions);

    row.appendChild(dateCell);
    row.appendChild(titleCell);
    row.appendChild(siteCell);
    row.appendChild(tagCell);
    row.appendChild(actionsCell);

    row.addEventListener('click', (event) => {
      if (event.target.closest('button') || event.target.closest('a')) {
        return;
      }
      setSelectedItem(item.content_id);
    });

    tbody.appendChild(row);
    tbody.appendChild(detailRow);
  });

  table.appendChild(tbody);
  summaryList.appendChild(table);
}

function createSummaryListItem(item) {
  const li = document.createElement('li');
  li.className = 'summary-item';
  li.setAttribute('data-content-id', item.content_id);
  if (item.content_id === state.selectedContentId) {
    li.classList.add('selected');
  }

  const titleLink = document.createElement('a');
  titleLink.href = item.original_url;
  titleLink.target = '_blank';
  titleLink.rel = 'noopener';
  titleLink.textContent = item.title;
  titleLink.className = 'summary-title';

  const header = document.createElement('div');
  header.className = 'summary-item-header';
  header.innerHTML = `
    <span class="summary-date">${item.published_display}</span>
  `;
  header.appendChild(titleLink);

  const meta = document.createElement('div');
  meta.className = 'summary-meta';
  const originLabel = ORIGIN_LABELS[item.origin] || titleCase(item.origin || item.source_type);
  const metaParts = [];

  if (item.author) {
    if (item.channel_url) {
      metaParts.push(`<a href="${item.channel_url}" target="_blank" rel="noopener">${item.author}</a>`);
    } else {
      metaParts.push(item.author);
    }
  }

  if (originLabel) {
    metaParts.push(originLabel);
  }

  const categoryParts = (item.categories || [])
    .filter(Boolean)
    .filter((category) => category !== originLabel);
  if (categoryParts.length) {
    metaParts.push(categoryParts.join(', '));
  }

  if (item.tags && item.tags.length) {
    metaParts.push(`Tags: ${item.tags.join(', ')}`);
  }

  meta.innerHTML = metaParts.join(' • ');

  const body = document.createElement('div');
  body.className = 'summary-body';
  body.dataset.contentId = item.content_id;
  body.innerHTML = renderSummaryHtml(item.summary);
  if (item.summary) {
    body.classList.add('collapsed');
  }

  const actions = document.createElement('div');
  actions.className = 'summary-actions';

  const hasSummary = Boolean(item.summary);
  const transcriptAvailable = item.transcript_available !== false;
  const transcriptError = item.transcript_error || null;

  const summaryBtn = createIconButton({
    label: hasSummary ? 'Summary' : 'Summarize',
    icon: 'fas fa-align-left',
    action: hasSummary ? 'toggle-summary' : 'summarize',
    onClick: hasSummary
      ? () => toggleSummary(body, summaryBtn, true)
      : () => triggerSummarization(item.content_id, summaryBtn, { isInitial: true }),
  });
  summaryBtn.dataset.contentId = item.content_id;
  if (!hasSummary && !transcriptAvailable && item.source_type === 'youtube_video') {
    summaryBtn.disabled = true;
  }

  let regenBtn = null;
  if (hasSummary) {
    regenBtn = createIconButton({
      label: 'Re-summarize',
      icon: 'fas fa-rotate-right',
      action: 'regenerate-summary',
      tone: 'accent',
      onClick: () => triggerSummarization(item.content_id, regenBtn),
    });
    regenBtn.dataset.contentId = item.content_id;
  }

  const status = document.createElement('div');
  status.className = 'status';
  status.dataset.statusFor = item.content_id;

  actions.appendChild(summaryBtn);
  if (!transcriptAvailable && item.source_type === 'youtube_video') {
    const fetchBtn = createIconButton({
      label: 'Fetch transcript',
      icon: 'fas fa-file-lines',
      action: 'fetch-transcript',
      onClick: () => triggerTranscriptFetch(item.content_id, fetchBtn),
    });
    fetchBtn.dataset.contentId = item.content_id;
    actions.appendChild(fetchBtn);
  }

  const tagBtn = createIconButton({
    label: 'Edit tags',
    icon: 'fas fa-tag',
    action: 'edit-tags',
    onClick: () => editTags(item),
  });
  tagBtn.dataset.contentId = item.content_id;
  actions.appendChild(tagBtn);

  li.appendChild(header);
  li.appendChild(meta);
  li.appendChild(actions);
  if (regenBtn) {
    const regenContainer = document.createElement('div');
    regenContainer.className = 'summary-regen-container';
    regenContainer.appendChild(regenBtn);
    body.prepend(regenContainer);
  }
  if (!transcriptAvailable) {
    body.innerHTML = `<p class="no-transcript">${transcriptError || 'Transcript unavailable for this video.'}</p>`;
    body.classList.remove('collapsed');
  }
  li.appendChild(body);
  li.appendChild(status);

  if (!transcriptAvailable && transcriptError) {
    status.textContent = transcriptError;
  }

  li.addEventListener('click', (event) => {
    if (event.target.closest('button') || event.target.closest('a')) {
      return;
    }
    setSelectedItem(item.content_id);
  });

  return li;
}

function renderSummaryHtml(summary) {
  if (!summary) {
    return '<p>No summary yet. Use the button above to generate one.</p>';
  }

  const escaped = summary.replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const lines = escaped.split(/\n+/);
  let html = '';
  let inList = false;

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      return;
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (!inList) {
        html += '<ul>';
        inList = true;
      }
      html += `<li>${formatInline(trimmed.replace(/^[-*]\s*/, ''))}</li>`;
    } else {
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      html += `<p>${formatInline(trimmed)}</p>`;
    }
  });

  if (inList) {
    html += '</ul>';
  }

  return html;
}

function toggleSummary(body, button, hasSummary, detailRow = null) {
  if (!hasSummary) {
    return;
  }
  if (detailRow) {
    const isOpen = detailRow.classList.contains('open');
    detailRow.classList.toggle('open');
    setIconButtonState(button, {
      label: isOpen ? 'Summary' : 'Hide Summary',
      icon: isOpen ? 'fas fa-align-left' : 'fas fa-eye-slash',
    });
    return;
  }
  const wasCollapsed = body.classList.contains('collapsed');
  body.classList.toggle('collapsed');
  setIconButtonState(button, {
    label: wasCollapsed ? 'Hide Summary' : 'Summary',
    icon: wasCollapsed ? 'fas fa-eye-slash' : 'fas fa-align-left',
  });
}

function formatInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');
}

function parseTagInput(text) {
  if (!text) {
    return [];
  }
  return text
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length);
}

async function editTags(item) {
  if (!item) return;
  const current = (item.tags || []).join(', ');
  const input = window.prompt('Edit tags (comma separated):', current);
  if (input === null) {
    return;
  }
  const tags = parseTagInput(input);
  try {
    const response = await fetch(`/api/items/${item.content_id}/tags`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags }),
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || 'Unable to save tags.');
    }
    showToast('Tags updated.', 'success');
    await loadData();
  } catch (error) {
    console.error('Failed to update tags', error);
    alert(error.message || 'Failed to update tags.');
  }
}

async function triggerTranscriptFetch(contentId, button) {
  if (!contentId) return;
  const originalLabel = button.dataset.label || 'Fetch transcript';
  const originalIcon = button.dataset.icon || 'fas fa-file-lines';
  const status = document.querySelector(`.status[data-status-for="${contentId}"]`);
  let succeeded = false;
  if (status) {
    status.textContent = 'Fetching transcript…';
    status.classList.add('loading');
  }
  button.disabled = true;
  setIconButtonState(button, { label: 'Fetching…', icon: 'fas fa-spinner', spinning: true });
  try {
    const response = await fetch(`/api/items/${contentId}/transcripts`, { method: 'POST' });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.message || 'Failed to fetch transcript.');
    }
    await loadData();
    succeeded = true;
    showToast('Transcript fetched.', 'success');
  } catch (error) {
    console.error('Failed to fetch transcript', error);
    alert(error.message || 'Failed to fetch transcript. Check server logs for details.');
  } finally {
    if (status) {
      status.classList.remove('loading');
      if (!succeeded) {
        status.textContent = '';
      }
    }
    button.disabled = false;
    setIconButtonState(button, { label: originalLabel, icon: originalIcon });
  }
}

function setSelectedItem(contentId) {
  state.selectedContentId = contentId;
  document.querySelectorAll('.summary-item.selected, .video-row.selected').forEach((item) => {
    item.classList.remove('selected');
  });
  const selected = document.querySelector(
    `.summary-item[data-content-id="${contentId}"], .video-row[data-content-id="${contentId}"]`
  );
  if (selected) {
    selected.classList.add('selected');
  }
}

function getSelectedItemElement() {
  let selected = document.querySelector('.summary-item.selected, .video-row.selected');
  if (!selected) {
    const first = document.querySelector('.summary-item, .video-row');
    if (first) {
      setSelectedItem(first.dataset.contentId);
      selected = first;
    }
  }
  return selected;
}

function getItemById(contentId) {
  return state.items.find((item) => item.content_id === contentId);
}

function shouldIgnoreKey(event) {
  if (event.metaKey || event.ctrlKey || event.altKey) {
    return true;
  }
  const active = document.activeElement;
  if (!active) {
    return false;
  }
  const tag = active.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || active.isContentEditable;
}

function handleKeyboardShortcuts(event) {
  if (shouldIgnoreKey(event)) {
    return;
  }
  if (event.key !== 't' && event.key !== 's') {
    return;
  }
  const selected = getSelectedItemElement();
  if (!selected) {
    return;
  }
  const contentId = selected.dataset.contentId;
  const item = getItemById(contentId);
  if (!item) {
    return;
  }

  if (event.key === 't') {
    if (item.source_type !== 'youtube_video') {
      showToast('Select a YouTube video to fetch a transcript.', 'warning');
      return;
    }
    if (item.transcript_available !== false) {
      showToast('Transcript already available.', 'info');
      return;
    }
    const fetchBtn = selected.querySelector('[data-action="fetch-transcript"]');
    if (fetchBtn) {
      triggerTranscriptFetch(contentId, fetchBtn);
    } else {
      showToast('Transcript fetch not available for this item.', 'warning');
    }
  }

  if (event.key === 's') {
    if (!item.summary) {
      if (item.transcript_available === false) {
        showToast('Fetch the transcript before summarizing.', 'warning');
        return;
      }
      const summaryBtn = selected.querySelector('[data-action="summarize"]');
      if (summaryBtn) {
        triggerSummarization(contentId, summaryBtn, { isInitial: true });
      }
      return;
    }
    const regenBtn = selected.querySelector('[data-action="regenerate-summary"]');
    if (regenBtn) {
      triggerSummarization(contentId, regenBtn);
    } else {
      showToast('Summary already available.', 'info');
    }
  }
}

function showToast(message, type = 'info') {
  if (!toastContainer) {
    return;
  }
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => {
      toast.remove();
    }, 200);
  }, 2500);
}

document.addEventListener('keydown', handleKeyboardShortcuts);

function getSummaryControls(contentId) {
  const body = document.querySelector(`.summary-body[data-content-id="${contentId}"]`);
  const summaryButton =
    document.querySelector(`[data-action="summarize"][data-content-id="${contentId}"]`) ||
    document.querySelector(`[data-action="toggle-summary"][data-content-id="${contentId}"]`);
  const regenButton = document.querySelector(
    `[data-action="regenerate-summary"][data-content-id="${contentId}"]`
  );
  const detailRow = document.querySelector(`.video-detail[data-content-id="${contentId}"]`);
  return { body, summaryButton, regenButton, detailRow };
}

async function triggerSummarization(contentId, button, options = {}) {
  const { isInitial = false } = options;
  const { body, summaryButton, regenButton, detailRow } = getSummaryControls(contentId);

  const originalLabel = button.dataset.label || 'Summarize';
  const originalIcon = button.dataset.icon || 'fas fa-align-left';
  button.disabled = true;
  setIconButtonState(button, { label: 'Queued…', icon: 'fas fa-spinner', spinning: true });
  updateStatus(contentId, 'Queued');

  if (summaryButton && summaryButton !== button) {
    summaryButton.disabled = true;
    if (isInitial) {
      setIconButtonState(summaryButton, { label: 'Summarizing…', icon: 'fas fa-spinner', spinning: true });
    }
  }
  if (regenButton && regenButton !== button) {
    regenButton.disabled = true;
  }

  try {
    const response = await fetch(`/api/items/${contentId}/summaries`, {
      method: 'POST',
    });
    const payload = await response.json();
    if (payload.status === 'error') {
      alert(payload.message || 'Unable to start summarization');
      button.disabled = false;
      setIconButtonState(button, { label: originalLabel, icon: originalIcon });
      if (summaryButton && summaryButton !== button) {
        summaryButton.disabled = false;
        if (isInitial) {
          setIconButtonState(summaryButton, { label: 'Summarize', icon: 'fas fa-align-left' });
        }
      }
      if (regenButton && regenButton !== button) {
        regenButton.disabled = false;
      }
      updateStatus(contentId, payload.message || 'Error');
      return;
    }
    setIconButtonState(button, { label: 'Summarizing…', icon: 'fas fa-spinner', spinning: true });
    startStatusPolling(contentId, button, { label: originalLabel, icon: originalIcon }, { isInitial });
  } catch (error) {
    console.error('Failed to queue summary', error);
    alert('Failed to queue summarization');
    button.disabled = false;
    setIconButtonState(button, { label: originalLabel, icon: originalIcon });
    if (summaryButton && summaryButton !== button) {
      summaryButton.disabled = false;
      if (isInitial) {
        setIconButtonState(summaryButton, { label: 'Summarize', icon: 'fas fa-align-left' });
      }
    }
    if (regenButton && regenButton !== button) {
      regenButton.disabled = false;
    }
    updateStatus(contentId, 'Error');
  }
}

async function addSourceUrl(origin) {
  const label = ORIGIN_LABELS[origin] || titleCase(origin);
  const url = (window.prompt(`Add ${label} URL:`) || '').trim();
  if (!url) {
    return;
  }

  try {
    const response = await fetch('/api/items/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, origin }),
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') {
      const details = payload.logs ? `\n\nDetails:\n${payload.logs}` : '';
      alert((payload.message || 'Unable to add URL.') + details);
      return;
    }
    state.selectedOrigin = origin;
    await loadData();
    if (payload.logs && payload.logs.includes('⚠️')) {
      alert(`Completed with warnings:\n${payload.logs}`);
    }
  } catch (error) {
    console.error('Failed to add URL', error);
    alert('Failed to add URL. Check logs for details.');
  }
}

function startStatusPolling(contentId, button, originalState, options = {}) {
  const { isInitial = false } = options;
  const { body, summaryButton, regenButton, detailRow } = getSummaryControls(contentId);

  if (state.statusPollers[contentId]) {
    clearInterval(state.statusPollers[contentId]);
  }
  state.statusPollers[contentId] = setInterval(async () => {
    const status = await fetch(`/api/items/${contentId}/status`).then((res) => res.json());
    if (status.status === 'complete') {
      clearInterval(state.statusPollers[contentId]);
      delete state.statusPollers[contentId];
      updateStatus(contentId, 'Complete');
      button.disabled = false;
      setIconButtonState(button, { label: originalState.label, icon: originalState.icon });
      if (summaryButton) {
        summaryButton.disabled = false;
        setIconButtonState(summaryButton, { label: 'Summary', icon: 'fas fa-align-left' });
        summaryButton.onclick = () => toggleSummary(body, summaryButton, true, detailRow);
      }
      if (regenButton) {
        regenButton.disabled = false;
      }
      if (body) {
        body.classList.add('collapsed');
      }
      if (detailRow) {
        detailRow.classList.remove('open');
      }
      loadData();
    } else if (status.status === 'error') {
      clearInterval(state.statusPollers[contentId]);
      delete state.statusPollers[contentId];
      updateStatus(contentId, status.message || 'Error');
      button.disabled = false;
      setIconButtonState(button, { label: originalState.label, icon: originalState.icon });
      if (summaryButton) {
        summaryButton.disabled = false;
        if (isInitial) {
          setIconButtonState(summaryButton, { label: 'Summarize', icon: 'fas fa-align-left' });
        }
      }
      if (regenButton) {
        regenButton.disabled = false;
      }
    } else {
      updateStatus(contentId, status.status || 'Running');
    }
  }, 2000);
}

function updateStatus(contentId, message) {
  const statusNode = document.querySelector(`[data-status-for="${contentId}"]`);
  if (statusNode) {
    statusNode.textContent = message;
  }
}

function showLoading() {
  if (loadingOverlay) {
    loadingOverlay.style.display = 'flex';
  }
}

function hideLoading() {
  if (loadingOverlay) {
    loadingOverlay.style.display = 'none';
  }
}

async function refreshData() {
  showLoading();
  try {
    const { response, payload } = await fetchJson('/api/refresh', { method: 'POST' }, 60000);
    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || 'Refresh failed.');
    }
    await loadData();
    showToast('Refresh complete.', 'success');
  } catch (error) {
    console.error('Failed to refresh', error);
    alert(error.message || 'Failed to refresh. Check server logs for details.');
  } finally {
    hideLoading();
  }
}

function titleCase(text) {
  return text
    .replace(/_/g, ' ')
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

if (searchInput) {
  searchInput.addEventListener('input', () => {
    window.clearTimeout(searchInput._timer);
    searchInput._timer = window.setTimeout(renderList, 200);
  });
}

if (promptSave) {
  promptSave.addEventListener('click', savePromptEditor);
}

if (settingsSave) {
  settingsSave.addEventListener('click', saveSettings);
}

if (promptKeySelect) {
  promptKeySelect.addEventListener('change', () => {
    refreshPromptEditor();
  });
}

if (openaiModel) {
  openaiModel.addEventListener('change', () => {
    if (!openaiModelCustom) return;
    const isCustom = openaiModel.value === 'custom';
    openaiModelCustom.style.display = isCustom ? 'block' : 'none';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  loadData();
});
