/* 前端逻辑。
   数据流很直接：REST 拿列表和详情，SSE 收实时事件，收到就重画对应面板。 */

const STAGES = [
  { key: 'verify', name: '验签', note: '校验平台签名，拦掉伪造回调' },
  { key: 'parse', name: '格式转换', note: '平台消息体转内部标准格式' },
  { key: 'dedupe', name: '幂等去重', note: '按事件 ID 判断是不是重复投递' },
  { key: 'store', name: '入库', note: '落库，同时记一条流转追踪' },
  { key: 'push', name: '实时推送', note: 'SSE 推到浏览器，不用轮询' },
  { key: 'display', name: '展示', note: '消息出现在统一入口' },
  { key: 'process', name: '处理', note: '用户读完，标记已处理' },
  { key: 'send', name: '发送', note: '调平台 API，把回复真正发出去' },
  { key: 'receipt', name: '回执', note: '平台确认，闭环收口' },
];

const STATUS_ORDER = ['received', 'stored', 'displayed', 'processed', 'replying', 'replied', 'confirmed'];

const state = {
  messages: [],
  selectedId: null,
  detail: null,
  filter: '',
  logCount: 0,
  overview: null,
};

const $ = (id) => document.getElementById(id);

/* ---------------------------------------------------------------- 网络 */

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...options,
  });

  if (res.status === 401) {
    showLogin();
    throw new Error('未登录');
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `请求失败 ${res.status}`);
  return data;
}

/* ---------------------------------------------------------------- 登录 */

function showLogin() {
  $('app').classList.add('hidden');
  $('login-layer').classList.remove('hidden');
}

function showApp() {
  $('login-layer').classList.add('hidden');
  $('app').classList.remove('hidden');
}

$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('login-error').textContent = '';
  try {
    await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username: $('username').value, password: $('password').value }),
    });
    showApp();
    await boot();
  } catch (err) {
    $('login-error').textContent = err.message;
  }
});

/* ---------------------------------------------------------------- 启动 */

async function boot() {
  await loadOverview();
  await loadMessages();
  if (state.messages.length && !state.selectedId) {
    selectMessage(state.messages[0].id);
  }
  connectStream();
}

async function loadOverview() {
  try {
    state.overview = await api('/api/overview');
    renderPlatforms();
    renderStats();
  } catch (e) { /* 未登录时会在 api 里跳登录 */ }
}

async function loadMessages() {
  const url = state.filter ? `/api/messages?platform=${state.filter}` : '/api/messages';
  const data = await api(url);
  state.messages = data.items;
  renderList();
}

/* ---------------------------------------------------------------- 渲染：平台 */

function renderPlatforms() {
  const box = $('platform-chips');
  if (!state.overview) return;

  box.innerHTML = state.overview.platforms.map((p) => `
    <div class="platform-chip">
      <span class="platform-dot" style="background:${p.color}"></span>
      ${p.label}
    </div>
  `).join('');

  $('mode-badge').textContent = state.overview.mode === 'real' ? '真实模式' : '模拟模式';
}

/* ---------------------------------------------------------------- 渲染：列表 */

function renderList() {
  const box = $('message-list');

  if (!state.messages.length) {
    box.innerHTML = '<div class="empty">还没有消息，点右上角「模拟新消息」</div>';
    return;
  }

  box.innerHTML = state.messages.map((m) => {
    const active = m.id === state.selectedId ? 'active' : '';
    const initial = m.sender.name.slice(0, 1);
    return `
      <div class="message-card ${active}" data-id="${m.id}">
        <div class="card-top">
          <div class="card-avatar" style="background:${m.platform_color}">${initial}</div>
          <span class="card-sender">${escapeHtml(m.sender.name)}</span>
          <span class="card-conv">${escapeHtml(m.conversation.name)}</span>
          <span class="card-time">${m.created_at.slice(11, 16)}</span>
        </div>
        <div class="card-text">${escapeHtml(m.summary)}</div>
        <div class="card-foot">
          <span class="platform-tag" style="background:${m.platform_color}">${m.platform_label}</span>
          <span class="status-tag s-${m.status}">${m.status_label}</span>
        </div>
      </div>
    `;
  }).join('');

  box.querySelectorAll('.message-card').forEach((card) => {
    card.addEventListener('click', () => selectMessage(card.dataset.id));
  });
}

/* ---------------------------------------------------------------- 选中与详情 */

async function selectMessage(id) {
  state.selectedId = id;
  renderList();

  const data = await api(`/api/messages/${id}`);
  state.detail = data;
  renderDetail();
  renderPipeline();
  renderTimeline();

  // 还没展示过的消息，自动推进到 displayed，闭环流程才完整
  if (data.message.status === 'stored') {
    try {
      await api(`/api/messages/${id}/display`, { method: 'POST' });
      const fresh = await api(`/api/messages/${id}`);
      state.detail = fresh;
      renderDetail();
      renderPipeline();
      renderTimeline();
    } catch (e) { /* 忽略，保持当前状态 */ }
    await loadMessages();
    await loadOverview();
  }
}

function renderDetail() {
  if (!state.detail) return;
  const m = state.detail.message;
  const color = m.platform === 'feishu' ? 'var(--feishu)' : 'var(--dingtalk)';

  $('detail-status').innerHTML = `<span class="status-tag s-${m.status}">${state.detail.status_label}</span>`;
  $('detail-footer').classList.remove('hidden');

  const contentHtml = m.msg_type === 'text'
    ? `<div class="detail-content">${escapeHtml(m.content.text || '')}</div>`
    : `<div class="detail-content file">
         <div class="detail-file-box">${escapeHtml((m.content.file_name || 'F').slice(-3))}</div>
         <div>
           <div>${escapeHtml(m.content.file_name || '未命名文件')}</div>
           <div class="detail-meta">文件消息，发送时走素材上传再发消息</div>
         </div>
       </div>`;

  $('detail-body').innerHTML = `
    <div class="detail-sender">
      <div class="detail-avatar" style="background:${color}">${escapeHtml(m.sender.name.slice(0, 1))}</div>
      <div>
        <div class="detail-name">${escapeHtml(m.sender.name)}</div>
        <div class="detail-meta">${escapeHtml(m.conversation.name)} · ${m.created_at}</div>
      </div>
    </div>
    ${contentHtml}
    <div class="detail-facts">
      <div class="fact"><div class="fact-key">来源平台</div><div class="fact-val">${m.platform === 'feishu' ? '飞书' : '钉钉'}</div></div>
      <div class="fact"><div class="fact-key">消息类型</div><div class="fact-val">${m.msg_type === 'text' ? '文本' : '文件'}</div></div>
      <div class="fact"><div class="fact-key">会话 ID</div><div class="fact-val">${escapeHtml(m.conversation.id)}</div></div>
      <div class="fact"><div class="fact-key">当前状态</div><div class="fact-val">${state.detail.status_label}</div></div>
    </div>
  `;

  // 状态决定哪些按钮可用
  const status = m.status;
  const canProcess = ['displayed', 'stored'].includes(status);
  const canReply = ['processed', 'replied', 'send_failed', 'displayed'].includes(status);
  const canConfirm = status === 'replied';

  $('btn-process').disabled = !canProcess;
  $('btn-reply').disabled = !canReply;
  $('btn-confirm').disabled = !canConfirm;
  $('btn-process').style.opacity = canProcess ? 1 : .45;
  $('btn-reply').style.opacity = canReply ? 1 : .45;
  $('btn-confirm').style.opacity = canConfirm ? 1 : .45;
}

/* ---------------------------------------------------------------- 流水线 */

function stageStates(m) {
  const status = m.status;
  const idx = STATUS_ORDER.indexOf(status);
  const states = {};

  states.verify = status === 'parse_failed' ? 'fail' : 'ok';
  states.parse = status === 'parse_failed' ? 'fail' : 'ok';
  states.dedupe = 'ok';
  states.store = 'ok';
  states.push = 'ok';
  states.display = idx >= 2 ? 'ok' : (m.id === state.selectedId ? 'active' : 'pending');
  states.process = idx >= 3 ? 'ok' : (status === 'displayed' ? 'pending' : 'pending');
  states.send = (status === 'replying') ? 'active'
    : (['replied', 'confirmed'].includes(status)) ? 'ok'
    : (['send_failed', 'dead'].includes(status)) ? 'fail' : 'pending';
  states.receipt = status === 'confirmed' ? 'ok' : 'pending';

  return states;
}

function renderPipeline() {
  const box = $('pipeline');

  if (!state.detail) {
    box.innerHTML = '<div class="empty">选一条消息，这里会显示它走到哪一步</div>';
    return;
  }

  const m = state.detail.message;
  const states = stageStates(m);

  box.innerHTML = STAGES.map((s, i) => {
    const st = states[s.key] || 'pending';
    const lineOk = st === 'ok' ? 'ok' : '';
    const dim = st === 'pending' ? 'dim' : '';
    const last = i === STAGES.length - 1;
    return `
      <div class="stage">
        <div class="stage-rail">
          <div class="stage-dot ${st}"></div>
          ${last ? '' : `<div class="stage-line ${lineOk}"></div>`}
        </div>
        <div class="stage-body">
          <div class="stage-name ${dim}">${s.name}</div>
          <div class="stage-note">${s.note}</div>
        </div>
      </div>
    `;
  }).join('');
}

function renderTimeline() {
  const box = $('timeline');
  if (!state.detail || !state.detail.traces.length) {
    box.innerHTML = '<div class="empty small">暂无记录</div>';
    return;
  }

  const labelMap = {
    received: '已接收', parse_failed: '解析失败', stored: '已入库', displayed: '已展示',
    processed: '已处理', replying: '回复中', replied: '已发送', send_failed: '发送失败',
    confirmed: '已确认', ignored: '已忽略', dead: '已归档', duplicate: '重复丢弃',
    send_retry: '重试中',
  };

  box.innerHTML = state.detail.traces.map((t) => {
    const kind = ['finished'].includes(t.status) ? 'ok'
      : ['parse_failed', 'send_failed', 'dead', 'duplicate', 'send_retry'].includes(t.status) ? 'fail' : '';
    return `
      <div class="tl-item">
        <div class="tl-dot ${kind}"></div>
        <div>
          <div class="tl-text">${labelMap[t.status] || t.status}${t.note ? ' · ' + escapeHtml(t.note) : ''}</div>
          <div class="tl-time">${t.at}</div>
        </div>
      </div>
    `;
  }).join('');
}

/* ---------------------------------------------------------------- 统计 */

function renderStats() {
  if (!state.overview) return;
  const s = state.overview.stats;
  const cards = [
    { num: s.total, label: '累计消息' },
    { num: (s.by_platform.feishu || 0), label: '来自飞书' },
    { num: (s.by_platform.dingtalk || 0), label: '来自钉钉' },
    { num: (s.by_status.replied || 0) + (s.by_status.confirmed || 0), label: '已回复' },
  ];

  $('stats').innerHTML = cards.map((c) => `
    <div class="stat">
      <div class="stat-num">${c.num}</div>
      <div class="stat-label">${c.label}</div>
    </div>
  `).join('');
}

/* ---------------------------------------------------------------- 操作 */

async function doReply() {
  if (!state.selectedId) return;
  const text = $('reply-input').value.trim();
  if (!text) { alert('先写点回复内容'); return; }

  $('btn-reply').disabled = true;
  try {
    const res = await api(`/api/messages/${state.selectedId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ text, simulate_failure: $('simulate-failure').checked }),
    });

    $('reply-input').value = '';
    await refreshDetail();
    await loadMessages();
    await loadOverview();

    if (!res.ok) {
      alert(`发送失败：${res.error || '未知原因'}。消息已转到人工补发队列。`);
    }
  } catch (err) {
    alert(err.message);
  } finally {
    $('btn-reply').disabled = false;
  }
}

async function refreshDetail() {
  if (!state.selectedId) return;
  const data = await api(`/api/messages/${state.selectedId}`);
  state.detail = data;
  renderDetail();
  renderPipeline();
  renderTimeline();
}

/* ---------------------------------------------------------------- SSE */

let stream = null;

function connectStream() {
  if (stream) stream.close();
  stream = new EventSource('/api/stream');

  stream.onmessage = (e) => {
    const evt = JSON.parse(e.data);
    handleEvent(evt);
  };

  stream.onerror = () => {
    // 浏览器会自动重连，这里不动，避免重复建连
  };
}

async function handleEvent(evt) {
  if (evt.type === 'pipeline' && evt.status !== 'start') {
    // 只记有结果的那一步，开始信号不入日志，否则每条消息会多出四五行
    pushLog(evt.stage, evt.detail || '', evt.status);
  }

  if (evt.type === 'message') {
    await loadMessages();
    await loadOverview();
    if (!state.selectedId) {
      selectMessage(evt.payload.id);
    } else if (evt.payload.id === state.selectedId) {
      await refreshDetail();
    }
    return;
  }

  if (evt.type === 'sent' || evt.type === 'confirmed') {
    await loadMessages();
    await loadOverview();
    if (state.selectedId === evt.message_id) await refreshDetail();
  }
}

/* ---------------------------------------------------------------- 日志 */

const STAGE_NAME = {
  verify: '验签', parse: '转换', dedupe: '去重', store: '入库',
  push: '推送', display: '展示', process: '处理', send: '发送', receipt: '回执',
};

function pushLog(stage, detail, status) {
  const box = $('log-list');
  const placeholder = box.querySelector('.log-empty');
  if (placeholder) placeholder.remove();

  const row = document.createElement('div');
  row.className = `log-row ${status === 'fail' ? 'fail' : status === 'ok' ? 'ok' : ''}`;

  const time = new Date().toTimeString().slice(0, 8);
  row.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-stage">${STAGE_NAME[stage] || stage}</span>
    <span class="log-detail">${escapeHtml(detail || '')}</span>
  `;

  box.appendChild(row);
  while (box.children.length > 60) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;

  state.logCount += 1;
  $('log-count').textContent = `${state.logCount} 条`;
}

/* ---------------------------------------------------------------- 工具 */

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/* ---------------------------------------------------------------- 事件绑定 */

$('filters').addEventListener('click', (e) => {
  const btn = e.target.closest('.chip');
  if (!btn) return;
  $('filters').querySelectorAll('.chip').forEach((c) => c.classList.remove('active'));
  btn.classList.add('active');
  state.filter = btn.dataset.platform;
  loadMessages();
});

$('btn-push').addEventListener('click', async () => {
  try {
    const plat = Math.random() < 0.5 ? 'feishu' : 'dingtalk';
    await api('/api/mock/push', { method: 'POST', body: JSON.stringify({ platform: plat }) });
  } catch (err) { alert(err.message); }
});

$('btn-duplicate').addEventListener('click', async () => {
  try {
    await api('/api/mock/duplicate', {
      method: 'POST',
      body: JSON.stringify({ platform: state.filter || 'feishu' }),
    });
  } catch (err) { alert(err.message); }
});

$('btn-reset').addEventListener('click', async () => {
  if (!confirm('清空所有演示数据？')) return;
  await api('/api/reset', { method: 'POST' });
  state.selectedId = null;
  state.detail = null;
  state.logCount = 0;
  $('log-list').innerHTML = '';
  $('log-count').textContent = '0 条';
  $('pipeline').innerHTML = '<div class="empty">选一条消息，这里会显示它走到哪一步</div>';
  $('timeline').innerHTML = '<div class="empty small">暂无记录</div>';
  $('detail-body').innerHTML = '<div class="empty tall">从左边选一条消息</div>';
  $('detail-footer').classList.add('hidden');
  $('detail-status').textContent = '';
  await loadMessages();
  await loadOverview();
});

$('btn-process').addEventListener('click', async () => {
  if (!state.selectedId) return;
  try {
    await api(`/api/messages/${state.selectedId}/process`, { method: 'POST' });
    await refreshDetail();
    await loadMessages();
    await loadOverview();
  } catch (err) { alert(err.message); }
});

$('btn-reply').addEventListener('click', doReply);

$('btn-confirm').addEventListener('click', async () => {
  if (!state.selectedId) return;
  try {
    await api(`/api/messages/${state.selectedId}/confirm`, { method: 'POST' });
    await refreshDetail();
    await loadMessages();
    await loadOverview();
  } catch (err) { alert(err.message); }
});

/* 启动：
   如果服务端已经把首屏数据渲染进来，直接用它画，不再等接口；
   否则走一次接口探测，判断当前是不是已登录。 */
(async () => {
  const seed = window.__BOOT__;

  if (seed && seed.messages) {
    showApp();
    state.messages = seed.messages;
    state.overview = seed.overview;

    renderPlatforms();
    renderStats();

    if (seed.detail) {
      state.selectedId = seed.detail.message.id;
      state.detail = seed.detail;
      renderList();
      renderDetail();
      renderPipeline();
      renderTimeline();
    } else {
      renderList();
    }

    connectStream();
    loadOverview().catch(() => {});
    return;
  }

  try {
    await api('/api/overview');
    showApp();
    await boot();
  } catch (e) {
    showLogin();
  }
})();
