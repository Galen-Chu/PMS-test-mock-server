/* PMS 測試主控台 — vanilla SPA（對齊原型 PMS Test Console 狀態模型）
 * 結構：state → render；使用者操作改 state 後重渲染。
 * 三頁：①設定(環境卡+案例矩陣+啟動) ②監控(步驟條+逐案例) ③結果(5 子檢視)
 * API:GET /environments /scenarios;POST /runs(202 立即回)→polling GET /runs/<id>。
 */
'use strict';

const API = '';
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;          // null/false → 不設屬性
    if (k === 'class') e.className = v;
    else if (k === 'onclick') e.onclick = v;
    else if (k === 'text') e.textContent = v;
    else if (k === 'disabled') e.disabled = !!v;      // 布林屬性正確處理
    else e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    e.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
  }
  return e;
};

// ---- 全域狀態 ----
const state = {
  activeTab: 'setup',
  environments: [],        // [{id,desc,color,ready,pms_url}]
  env: null,               // 當前選環境 id
  modules: [],             // [{module,label,vendors:[{id,label,scenarios:[{id,name,endpoint,implemented}]}]}]
  activeVendor: {},        // module → 當前選廠商 id
  expanded: {},            // module → bool
  checked: {},             // case_id → bool
  runStep: 'idle',         // idle / running / done
  caseResults: [],         // CaseResult[]
  runId: null,
  resultsView: 'summary',
  selectedCase: null,      // 結果頁「案例檢視」選中的 case_id
  caseDetailTab: 'http',   // 案例明細內部分頁:http / json / error / snapshot
  pollTimer: null,
  launchMsg: null,
  tunnel: null,         // /tunnel/status 結果(對外隧道卡)
  tunnelBusy: false,
};

// ---- API client ----
const api = {
  getEnvironments: () => fetch(API + '/environments').then(r => r.json()),
  getScenarios: () => fetch(API + '/scenarios').then(r => r.json()),
  startRun: (env, ids) => fetch(API + '/runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ environment: env, scenario_ids: ids }),
  }).then(r => r.json()),
  getRun: (id) => fetch(API + `/runs/${id}`).then(r => r.json()),
  getResults: (id) => fetch(API + `/runs/${id}/results`).then(r => r.json()),
  getTunnelStatus: () => fetch(API + '/tunnel/status').then(r => r.json()),
  startTunnel: () => fetch(API + '/tunnel/start', { method: 'POST' }).then(r => r.json()),
  stopTunnel: () => fetch(API + '/tunnel/stop', { method: 'POST' }).then(r => r.json()),
};

// ---- 初始化 ----
async function init() {
  const [envs, mods] = await Promise.all([api.getEnvironments(), api.getScenarios()]);
  state.environments = envs;
  state.modules = mods;
  state.env = envs[0]?.id || 'LOCAL_OFFLINE';
  // 預設勾選所有已實作案例(遍歷模組→廠商→案例);每模組預設選第一個廠商
  for (const m of mods) {
    state.activeVendor[m.module] = m.vendors[0]?.id;
    for (const v of m.vendors) for (const s of v.scenarios) if (s.implemented) state.checked[s.id] = true;
  }
  render();
  // 對外隧道狀態非同步補載(失敗不影響主控台)
  api.getTunnelStatus().then(t => { state.tunnel = t; render(); }).catch(() => {});
}

// ---- 渲染入口 ----
function render() {
  const app = document.getElementById('app');
  app.textContent = '';
  app.appendChild(renderLayout());
}

function renderLayout() {
  const envMeta = state.environments.find(e => e.id === state.env) || {};
  return el('div', { class: 'layout' },
    renderSidebar(),
    el('div', { class: 'main' },
      el('div', { class: 'topbar' },
        el('div', { class: 'title', text: pageTitle() }),
        el('div', { class: 'env-pill' },
          el('span', { class: 'env-dot', style: `background:${envMeta.color || '#9aa0ac'}` }),
          el('span', { text: state.env || '' }),
        ),
      ),
      el('div', { class: 'content' },
        state.activeTab === 'setup' ? renderSetup()
          : state.activeTab === 'monitor' ? renderMonitor()
          : renderResults(),
      ),
    ),
  );
}

function pageTitle() {
  return state.activeTab === 'setup' ? '環境 / 案例設定'
    : state.activeTab === 'monitor' ? '執行監控' : '結果分析';
}

function renderSidebar() {
  const mk = (tab, label, dotColor) => el('div', {
    class: 'nav-item ' + (state.activeTab === tab ? 'active' : ''),
    onclick: () => { state.activeTab = tab; render(); },
  }, el('span', { text: label }),
    dotColor ? el('span', { class: 'nav-dot ' + (dotColor === 'green' ? 'green' : '') }) : null,
  );
  return el('div', { class: 'sidebar' },
    el('h1', { text: '🎛️ PMS 測試主控台' }),
    mk('setup', '① 環境/案例設定'),
    mk('monitor', '② 執行監控', state.runStep === 'running' && state.activeTab !== 'monitor' ? 'blue' : null),
    mk('results', '③ 結果分析', state.runStep === 'done' && state.activeTab !== 'results' ? 'green' : null),
    el('div', { class: 'foot' }, document.createTextNode('mock-server v.next'), el('br'), document.createTextNode('三分頁常駐・自由切換')),
  );
}

// ---- ① 設定頁 ----
function renderSetup() {
  const envMeta = state.environments.find(e => e.id === state.env) || {};
  const totalSelected = Object.values(state.checked).filter(Boolean).length;
  const page = el('div', { class: 'page' });

  // 環境卡（兩列，照 ENV_UI_ROWS 順序已由後端給）
  const envWrap = el('div');
  envWrap.appendChild(el('div', { class: 'section-label', text: '戰場環境' }));
  const grid = el('div', { class: 'env-grid' });
  for (const e of state.environments) {
    grid.appendChild(el('div', {
      class: 'env-card ' + (state.env === e.id ? 'active' : '') + (e.ready ? '' : ' not-ready'),
      onclick: () => { state.env = e.id; render(); },
      style: state.env === e.id ? `border-color:${e.color}` : '',
    },
      el('div', { class: 'row1' },
        el('span', { class: 'dot', style: `background:${e.color}` }),
        el('span', { class: 'id', text: e.id }),
      ),
      el('div', { class: 'desc', text: e.desc }),
    ));
  }
  envWrap.appendChild(grid);
  page.appendChild(envWrap);

  // 🌐 對外隧道卡(真實環境串接:ngrok 狀態/啟停/各廠商註冊 URL)
  page.appendChild(renderTunnelCard());

  // 真實環境提示卡
  if (state.env && state.env.startsWith('REAL_')) {
    const ready = !!envMeta.ready;
    page.appendChild(el('div', { class: 'notice ' + (ready ? 'ready' : 'not-ready') },
      el('span', { class: 'ico', text: ready ? '🌐' : '⚠️' }),
      el('div', {},
        el('div', { class: 'nt-title', text: ready ? '真實環境測試前請確認' : '此環境尚未設定，無法測試' }),
        el('div', { class: 'nt-body', text: ready
          ? `即將對 ${state.env} 真實 PMS 資料庫發送請求，請先確認該環境服務已啟動、URL 與認證憑證有效，避免產生髒資料。`
          : `${state.env} 尚未設定 PMS API URL 與認證資訊，請聯繫後端於 config 補上此環境參數後再測試。` }),
        el('div', { class: 'url-box' },
          el('span', { class: 'lbl', text: 'PMS API URL' }),
          el('span', { class: 'nt-url', style: `color:${ready ? '#e7e9ee' : '#ff5f56'}`, text: envMeta.pms_url || '（尚未設定）' }),
        ),
      ),
    ));
  }

  // 案例矩陣
  const matrix = el('div');
  matrix.appendChild(el('div', { class: 'matrix-head' },
    el('div', { class: 'section-label', text: '模組 × 廠商 × 測試案例', style: 'margin:0' }),
    el('div', { class: 'sel', text: `已選 ${totalSelected} 案例` }),
  ));
  const stack = el('div', { class: 'list-stack' });
  for (const m of state.modules) {
    // 該模組所有廠商的案例合計
    const allScenarios = m.vendors.flatMap(v => v.scenarios);
    const selCount = allScenarios.filter(s => state.checked[s.id]).length;
    const expanded = state.expanded[m.module];
    const mod = el('div', { class: 'module' },
      el('div', { class: 'module-head', onclick: () => { state.expanded[m.module] = !expanded; render(); } },
        el('div', { class: 'left' },
          el('span', { class: 'label', text: m.label || moduleLabel(m.module) }),
        ),
        el('div', { style: 'display:flex;align-items:center;gap:12px' },
          el('span', { class: 'count', text: `${selCount}/${allScenarios.length}` }),
          el('span', { style: 'font-size:11px;color:#6b7280', text: expanded ? '▲' : '▼' }),
        ),
      ),
    );
    if (expanded) {
      const body = el('div', { class: 'module-body' });
      // 廠商 chip 列(切換 activeVendor)
      const chipRow = el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px' });
      for (const v of m.vendors) {
        const active = (state.activeVendor[m.module] || m.vendors[0]?.id) === v.id;
        chipRow.appendChild(el('div', {
          class: 'vendor-chip' + (active ? ' active' : ''),
          onclick: (e) => { e.stopPropagation(); state.activeVendor[m.module] = v.id; render(); },
          style: active
            ? 'background:rgba(255,138,61,.15);border:1.5px solid #ff8a3d'
            : 'background:transparent;border:1.5px solid rgba(255,255,255,.12)',
        },
          el('span', { style: `font:600 11.5px 'JetBrains Mono';color:${active ? '#fff' : '#9aa0ac'}`, text: v.label }),
          el('span', { style: 'font:10.5px \'JetBrains Mono\';color:#6b7280', text: String(v.scenarios.filter(s => state.checked[s.id]).length) }),
        ));
      }
      body.appendChild(chipRow);
      // 當前選中廠商的案例清單
      const activeV = m.vendors.find(v => v.id === (state.activeVendor[m.module] || m.vendors[0]?.id)) || m.vendors[0];
      if (activeV) for (const s of activeV.scenarios) {
        const ck = !!state.checked[s.id];
        body.appendChild(el('div', { class: 'scenario', onclick: () => { state.checked[s.id] = !state.checked[s.id]; render(); } },
          el('span', { class: 'box' + (ck ? ' checked' : '') }, ck ? el('span', { text: '✓' }) : null),
          el('span', { class: 'name', text: s.name }),
          el('span', { class: 'ep', text: s.endpoint }),
          s.implemented ? null : el('span', { class: 'tag', text: '待開發' }),
        ));
      }
      mod.appendChild(body);
    }
    stack.appendChild(mod);
  }
  matrix.appendChild(stack);
  page.appendChild(matrix);

  // sticky 啟動列
  const canLaunch = totalSelected > 0 && envMeta.ready !== false && state.runStep !== 'running';
  page.appendChild(el('div', { class: 'launch-bar' },
    el('div', { class: 'meta', text: `環境 ${state.env} ・ 已選 ${totalSelected} 案例` }),
    el('button', { class: 'btn-launch', text: state.runStep === 'running' ? '執行中…' : '🚀 啟動測試', onclick: startRun, disabled: !canLaunch }),
  ));
  if (state.launchMsg) page.appendChild(el('div', { class: 'error-banner', text: state.launchMsg }));

  // 預設展開第一個模組
  if (Object.keys(state.expanded).length === 0 && state.modules.length) {
    state.expanded[state.modules[0].module] = true;
    return renderSetup();
  }
  return page;
}

function moduleLabel(id) {
  return { parking: '🚗 停車車辨', amenity: '🦏 房務備品', keycard: '🔑 門禁製卡' }[id] || id;
}

// ---- 啟動測試 + polling ----
async function startRun() {
  const ids = Object.keys(state.checked).filter(k => state.checked[k]);
  if (!ids.length) return;
  state.launchMsg = null;
  let run;
  try {
    run = await api.startRun(state.env, ids);
  } catch (e) {
    state.launchMsg = `啟動失敗：${e}`;
    render(); return;
  }
  if (run.error) {
    // 後端拒絕（如 ENV_NOT_READY 回 409；fetch 不丟例外，需看 body）
    state.launchMsg = `後端拒絕：${run.error}${run.env ? ' (' + run.env + ')' : ''}`;
    render(); return;
  }
  state.runId = run.run_id;
  state.runStep = 'running';
  state.caseResults = [];
  state.activeTab = 'monitor';
  state.resultsView = 'summary';
  render();
  pollRun();
}

async function pollRun() {
  if (!state.runId) return;
  const run = await api.getRun(state.runId);
  const results = await api.getResults(state.runId);
  state.caseResults = results;
  if (run.status && run.status !== 'RUNNING') {
    state.runStep = 'done';
    if (state.pollTimer) { clearTimeout(state.pollTimer); state.pollTimer = null; }
  } else {
    state.pollTimer = setTimeout(pollRun, 600);
  }
  render();
}

// ---- ② 監控頁 ----
function renderMonitor() {
  const page = el('div', { class: 'page' });
  const stepColors = stepColor(state.runStep);
  const statusText = state.runStep === 'idle' ? '尚未啟動' : state.runStep === 'running' ? '執行中…' : '已完成';
  page.appendChild(el('div', { class: 'steps' },
    stepNode('送出參數', stepColors[0]),
    el('div', { class: 'bar' }),
    stepNode('執行中', stepColors[1]),
    el('div', { class: 'bar' }),
    stepNode('完成', stepColors[2]),
    el('div', { class: 'status', text: statusText }),
  ));
  if (!state.caseResults.length) {
    page.appendChild(el('div', { class: 'empty', text: '尚未啟動測試，請回到「① 環境/案例設定」勾選案例並啟動' }));
  } else {
    const list = el('div', { class: 'list-stack' });
    for (const c of state.caseResults) {
      list.appendChild(el('div', { class: 'case-row' },
        el('span', { class: 'st st-' + c.status, text: c.status }),
        el('span', { class: 'name', text: `${moduleLabel(c.module)} / ${c.vendor} / ${c.scenario_name}` }),
        el('span', { class: 'dur', text: c.duration_ms ? c.duration_ms + 'ms' : '—' }),
      ));
    }
    page.appendChild(list);
  }
  return page;
}
function stepNode(label, color) {
  return el('div', { class: 'step' },
    el('span', { class: 'dot', style: `background:${color}` }),
    el('span', { text: label, style: `color:${color}` }),
  );
}
function stepColor(step) {
  if (step === 'idle') return ['#4b5160', '#4b5160', '#4b5160'];
  if (step === 'running') return ['#35d399', '#4da3ff', '#4b5160'];
  return ['#35d399', '#35d399', '#35d399']; // done
}

// ---- ③ 結果分析頁（5 子檢視） ----
function renderResults() {
  const page = el('div', { class: 'page' });
  // 頂層分頁:摘要 | 案例檢視(主從明細) | 時序圖 | 失敗歸類
  const tabs = [['summary', '摘要'], ['cases', '案例��視'], ['timeline', '時序圖'], ['category', '失敗歸類']];
  const tabRow = el('div', { class: 'result-tabs' });
  for (const [id, label] of tabs) {
    tabRow.appendChild(el('div', {
      class: 'result-tab ' + (state.resultsView === id ? 'active' : ''),
      onclick: () => { state.resultsView = id; render(); },
      text: label,
    }));
  }
  page.appendChild(tabRow);

  if (!state.caseResults.length) {
    page.appendChild(el('div', { class: 'empty', text: '尚無測試結果，請先啟動一次測試' }));
    return page;
  }
  if (state.resultsView === 'summary') page.appendChild(renderSummary());
  else if (state.resultsView === 'cases') page.appendChild(renderCaseBrowser());
  else if (state.resultsView === 'timeline') page.appendChild(renderTimeline());
  else page.appendChild(renderCategory());
  return page;
}

// ---- ���要:統計卡 + 整批快照下載 ----
function renderSummary() {
  const passed = state.caseResults.filter(c => c.status === 'PASS').length;
  const failed = state.caseResults.filter(c => c.status === 'FAIL').length;
  const totalDur = state.caseResults.reduce((a, c) => a + (c.duration_ms || 0), 0);
  return el('div', {},
    el('div', { class: 'summary-cards' },
      statCard('總案例數', state.caseResults.length, ''),
      statCard('Passed', passed, 'pass'),
      statCard('Failed', failed, 'fail'),
      statCard('總耗時', (totalDur / 1000).toFixed(1) + 's', ''),
    ),
    el('div', { style: 'margin-top:14px' },
      el('button', { class: 'btn-secondary', text: '📥 下載整批快照 (JSON)', onclick: () =>
        downloadJson(`run-${state.runId || 'snapshot'}.json`, {
          run_id: state.runId, environment: state.env, triggered_at: null, cases: state.caseResults,
        }) }),
    ),
  );
}

// ---- 時序圖 ----
function renderTimeline() {
  const max = Math.max(1, ...state.caseResults.map(c => c.duration_ms || 0));
  const list = el('div', { class: 'list-stack' });
  for (const c of state.caseResults) {
    const pct = Math.round(((c.duration_ms || 0) / max) * 100);
    const color = c.status === 'FAIL' ? '#ff5f56' : '#35d399';
    list.appendChild(el('div', { class: 'timeline-row' },
      el('span', { class: 'tname', text: c.scenario_name }),
      el('div', { class: 'timeline-track' }, el('div', { class: 'timeline-fill', style: `width:${pct}%;background:${color}` })),
      el('span', { class: 'tdur', text: c.duration_ms ? c.duration_ms + 'ms' : '—' }),
    ));
  }
  return list;
}

// ---- 失敗歸類 ----
function renderCategory() {
  const fails = state.caseResults.filter(x => x.status === 'FAIL');
  if (!fails.length) return el('div', { class: 'empty', text: '本次執行沒有失敗案例' });
  const cats = {};
  for (const c of fails) { const k = c.error_category || 'UNKNOWN'; (cats[k] = cats[k] || []).push(c); }
  const wrap = el('div', { class: 'list-stack' });
  for (const [cat, cases] of Object.entries(cats)) {
    wrap.appendChild(el('div', { class: 'cat-box' },
      el('div', { class: 'diff-title', text: `${categoryLabel(cat)}（${cases.length} 案例）` }),
      el('div', { class: 'nt-body', text: cases.map(c => c.scenario_name).join('、') }),
    ));
  }
  return wrap;
}

// ---- 案例檢視:左案例清單 + 右明細(HTTP/JSON/錯誤/快照) ----
function renderCaseBrowser() {
  const selected = state.caseResults.find(c => c.case_id === state.selectedCase) || state.caseResults[0];
  state.selectedCase = selected.case_id;
  const innerTabs = [['http', 'HTTP 稽核'], ['json', 'JSON 稽核'], ['error', '錯誤分析'], ['snapshot', '📥 快照']];
  const tabRow = el('div', { class: 'result-tabs sub' });
  for (const [id, label] of innerTabs) {
    tabRow.appendChild(el('div', {
      class: 'result-tab ' + (state.caseDetailTab === id ? 'active' : ''),
      onclick: () => { state.caseDetailTab = id; render(); },
      text: label,
    }));
  }
  const list = el('div', { class: 'case-list' });
  for (const c of state.caseResults) {
    list.appendChild(el('div', {
      class: 'case-row' + (c.case_id === state.selectedCase ? ' selected' : ''),
      onclick: () => { state.selectedCase = c.case_id; render(); },
    },
      el('span', { class: 'st st-' + c.status, text: c.status }),
      el('span', { class: 'name', text: `${moduleLabel(c.module)}/${c.vendor} ${c.scenario_name}` }),
    ));
  }
  const detail = el('div', { class: 'case-detail' },
    el('div', { class: 'detail-head' },
      el('span', { class: 'st st-' + selected.status, text: selected.status }),
      el('span', { class: 'detail-title', text: `${moduleLabel(selected.module)} / ${selected.vendor} / ${selected.scenario_name}` }),
      el('span', { class: 'ep', text: selected.endpoint }),
    ),
    tabRow,
  );
  if (state.caseDetailTab === 'http') detail.appendChild(renderHttpAudit(selected));
  else if (state.caseDetailTab === 'json') detail.appendChild(renderJsonAudit(selected));
  else if (state.caseDetailTab === 'error') detail.appendChild(renderErrorAnalysis(selected));
  else detail.appendChild(renderSnapshot(selected));
  return el('div', { class: 'browser' }, list, detail);
}

// HTTP 稽核:逐步 HTTP 交易(可折疊)
function renderHttpAudit(c) {
  const steps = c.steps || [];
  if (!steps.length) return el('div', { class: 'empty', text: '本案例無逐步 HTTP 紀錄' });
  const wrap = el('div', { class: 'list-stack' });
  steps.forEach((st, i) => {
    const ok = !st.error && typeof st.status_code === 'number' && st.status_code >= 200 && st.status_code < 300;
    wrap.appendChild(el('div', { class: 'http-step' },
      el('div', { class: 'http-head', onclick: toggleStep },
        el('span', { class: 'http-seq', text: '#' + (i + 1) }),
        el('span', { class: 'http-method', text: st.method }),
        el('span', { class: 'http-url', text: st.url }),
        st.error
          ? el('span', { class: 'http-status fail', text: 'ERROR' })
          : el('span', { class: 'http-status ' + (ok ? 'pass' : 'fail'), text: String(st.status_code) }),
        el('span', { class: 'http-dur', text: st.duration_ms != null ? st.duration_ms + 'ms' : '' }),
        el('span', { class: 'http-twisty', text: '▼' }),
      ),
      el('div', { class: 'http-body' },
        el('div', { class: 'http-col' },
          el('div', { class: 'http-lbl', text: 'Request' }),
          kv('params', st.request_params),
          kv('headers', st.request_headers),
          kv('body', st.request_body),
        ),
        el('div', { class: 'http-col' },
          el('div', { class: 'http-lbl', text: 'Response' }),
          st.error ? el('pre', { class: 'json error', text: st.error }) : null,
          !st.error ? kv('status', st.status_code) : null,
          !st.error ? kv('headers', st.response_headers) : null,
          !st.error ? kv('body', st.response_body) : null,
        ),
      ),
    ));
  });
  return wrap;
}

// JSON 稽核:請求/回應並排 + 期望值 + 欄位 Diff
function renderJsonAudit(c) {
  const wrap = el('div', { class: 'json-audit' });
  wrap.appendChild(el('div', { class: 'json-pair' },
    el('div', { class: 'json-col' },
      el('div', { class: 'http-lbl', text: 'Request payload' }),
      renderJson(c.request_payload),
    ),
    el('div', { class: 'json-col' },
      el('div', { class: 'http-lbl', text: 'Response payload' }),
      renderJson(c.response_payload),
    ),
  ));
  if (c.expected_payload) {
    wrap.appendChild(el('div', { class: 'json-col', style: 'margin-top:12px' },
      el('div', { class: 'http-lbl', text: 'Expected payload（通關種子）' }),
      renderJson(c.expected_payload),
    ));
  }
  const rows = (c.diff && c.diff.length) ? c.diff : [];
  if (rows.length) {
    const box = el('div', { class: 'diff-box', style: 'margin-top:12px' },
      el('div', { class: 'diff-title', text: `欄位 Diff 比對（${rows.length} 項）` }),
      el('div', { class: 'diff-row' },
        el('span', { class: 'f', text: '欄位' }), el('span', { class: 'e', text: '期望' }), el('span', { class: 'a', text: '實際' }),
      ),
    );
    for (const d of rows) {
      box.appendChild(el('div', { class: 'diff-row' },
        el('span', { class: 'f', text: d.field }),
        el('span', { class: 'e', text: fmtVal(d.expected) }),
        el('span', { class: 'a', text: fmtVal(d.actual) }),
      ));
    }
    wrap.appendChild(box);
  } else if (c.status === 'FAIL') {
    wrap.appendChild(el('div', { class: 'empty', style: 'margin-top:12px', text: '無欄位級 Diff（失敗可能源於狀態碼或連線，見「錯誤分析」）' }));
  }
  return wrap;
}

// 錯誤分析:分類 + 除錯建議 + 失敗步回應 + 例外訊息
function renderErrorAnalysis(c) {
  if (c.status !== 'FAIL') return el('div', { class: 'empty', text: '本案例通過，無錯誤可分析' });
  const wrap = el('div', { class: 'list-stack' });
  wrap.appendChild(el('div', { class: 'cat-box' },
    el('div', { class: 'diff-title', text: '錯誤分類:' + categoryLabel(c.error_category) }),
    el('div', { class: 'nt-body', text: '💡 ' + (c.remediation || '—') }),
  ));
  if (c.failing_step) {
    const fs = c.failing_step;
    wrap.appendChild(el('div', { class: 'http-step open' },
      el('div', { class: 'http-head' },
        el('span', { class: 'http-method', text: fs.method }),
        el('span', { class: 'http-url', text: fs.url }),
        fs.error
          ? el('span', { class: 'http-status fail', text: 'ERROR' })
          : el('span', { class: 'http-status fail', text: String(fs.status_code) }),
      ),
      el('div', { class: 'http-body' },
        el('div', { class: 'http-col' },
          el('div', { class: 'http-lbl', text: '回應內容(常含雲端錯誤訊息)' }),
          renderJson(fs.error ? { error: fs.error } : fs.response_body),
        ),
      ),
    ));
  }
  const errPayload = (c.response_payload && typeof c.response_payload === 'object' && c.response_payload.__error__) ? c.response_payload.__error__ : null;
  if (errPayload) {
    wrap.appendChild(el('div', { class: 'json-col' },
      el('div', { class: 'http-lbl', text: '例外訊息' }),
      el('pre', { class: 'json error', text: String(errPayload) }),
    ));
  }
  return wrap;
}

// 快照:下載本案例完整 JSON + 預覽
function renderSnapshot(c) {
  const detail = {
    case_id: c.case_id, module: c.module, vendor: c.vendor, scenario_name: c.scenario_name,
    endpoint: c.endpoint, status: c.status, duration_ms: c.duration_ms,
    error_category: c.error_category, remediation: c.remediation,
    request_payload: c.request_payload, response_payload: c.response_payload,
    expected_payload: c.expected_payload, diff: c.diff, steps: c.steps || [],
  };
  return el('div', { class: 'list-stack' },
    el('div', { class: 'cat-box' },
      el('div', { class: 'nt-body', text: `案例 ${c.case_id} 的完整 HTTP 交易與結果快照（${(c.steps || []).length} 步交易）。` }),
      el('button', { class: 'btn-secondary', text: '📥 下載本案例快照 (JSON)', style: 'margin-top:10px',
        onclick: () => downloadJson(`snapshot-${c.case_id}.json`, detail) }),
    ),
    el('div', { class: 'json-col' }, el('div', { class: 'http-lbl', text: '快照預覽' }), renderJson(detail)),
  );
}

// ---- 共用工具 ----
function toggleStep(e) {
  const head = e.currentTarget, step = head.parentNode;
  if (step) step.classList.toggle('open');
}

function kv(label, val) {
  if (val == null || (typeof val === 'object' && Object.keys(val).length === 0)) return null;
  return el('div', { class: 'kv' },
    el('span', { class: 'kv-k', text: label }),
    el('div', { class: 'kv-v' }, renderJson(val)),
  );
}

function renderJson(val) {
  const txt = val == null ? 'null'
    : (typeof val === 'string' ? JSON.stringify(val) : JSON.stringify(val, null, 2));
  // 先 HTML 跳避再做語法高亮(安全):只注入 <span class>
  const esc = txt.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const html = esc.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)/g,
    (m) => {
      let cls = 'json-num';
      if (/^"/.test(m)) cls = /:\s*$/.test(m) ? 'json-key' : 'json-str';
      else if (/true|false/.test(m)) cls = 'json-bool';
      else if (/null/.test(m)) cls = 'json-null';
      return `<span class="${cls}">${m}</span>`;
    });
  const pre = el('pre', { class: 'json' });
  pre.innerHTML = html;
  return pre;
}

function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

function statCard(label, val, cls) {
  return el('div', { class: 'stat-card ' + cls },
    el('div', { class: 'lbl', text: label }),
    el('div', { class: 'val', text: String(val) }),
  );
}
function autoDiff(c) {
  // 無後端 diff 時，至少顯示 status 一列
  return [{ field: 'status', expected: 'PASS', actual: c.status }];
}
function fmtVal(v) {
  if (v === null) return 'null';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
function categoryLabel(cat) {
  return {
    FIELD_MISMATCH: '欄位缺失／型別錯誤', STATUS_CODE: '狀態碼非預期',
    TIMEOUT: '連線逾時／錯誤', UNIMPLEMENTED: '案例尚無執行器', UNKNOWN_SCENARIO: '未知案例',
    UNKNOWN: '未分類',
  }[cat] || cat;
}

// ---- 🌐 對外隧道卡(真實環境串接) ----
function renderTunnelCard() {
  const t = state.tunnel;
  const busy = state.tunnelBusy;
  const url = t && t.public_url;
  const running = !!(t && t.running && url);
  const card = el('div', { class: 'tunnel-card' });

  card.appendChild(el('div', { class: 'tunnel-head' },
    el('span', { class: 'section-label', text: '🌐 對外隧道（真實環境串接）', style: 'margin:0' }),
    el('span', { class: 'tunnel-state' },
      el('span', { class: 'dot', style: `background:${running ? '#35d399' : '#6b7280'}` }),
      el('span', { text: busy ? '處理中…' : (running ? '已連線' : '未啟動'),
                   style: `font:11.5px 'JetBrains Mono';color:${running ? '#35d399' : '#9aa0ac'}` }),
    ),
  ));

  // 目前公網 URL + 複製
  card.appendChild(el('div', { class: 'tunnel-url' + (url ? '' : ' none') },
    el('span', { text: url || '（未建立隧道）', style: 'flex:1' }),
    url ? el('button', { class: 'copy-btn', text: '複製', onclick: (e) => copyText(url, e) }) : null,
  ));

  // 啟動 / 停止 / 重新檢查
  card.appendChild(el('div', { class: 'tunnel-actions' },
    el('button', { class: 'btn-secondary', text: '▶ 啟動隧道', disabled: busy || running,
                   onclick: () => tunnelAction('start') }),
    el('button', { class: 'btn-secondary', text: '■ 停止隧道', disabled: busy || !(t && t.spawned_by_sandbox),
                   onclick: () => tunnelAction('stop') }),
    el('button', { class: 'btn-secondary', text: '重新檢查', disabled: busy,
                   onclick: () => tunnelAction('refresh') }),
  ));

  // 固定網域提示
  if (t && t.static_domain) {
    card.appendChild(el('div', { class: 'tunnel-hint', text: `固定網域：${t.static_domain}` }));
  } else {
    card.appendChild(el('div', { class: 'tunnel-warn',
      text: '⚠ 未設定固定網域：隨機 URL 每次重啟都會變，且免費隨機 URL 的瀏覽器警告頁會擋掉 PMS 的機器請求。請申請免費固定網域並設定 NGROK_STATIC_DOMAIN（步驟見 README「真實環境串接」）。' }));
  }

  // 各廠商登錄進 PMS 第三方廠商設定的 URL
  if (running && t.register_urls) {
    const rows = [
      ['新詠 SHIN_YEONG（公版單一端點）', t.register_urls.SHIN_YEONG],
      ['博辰 PAYTRONEX（base，PMS 拼 /roomer/*）', t.register_urls.PAYTRONEX],
      ['華豫寧 LIVEAM（base，PMS 拼 /api/*）', t.register_urls.LIVEAM],
    ];
    const box = el('div', { class: 'list-stack' });
    for (const [who, u] of rows) {
      box.appendChild(el('div', { class: 'reg-row' },
        el('span', { class: 'who', text: who }),
        el('span', { class: 'u', text: u }),
        el('button', { class: 'copy-btn', text: '複製', onclick: (e) => copyText(u, e) }),
      ));
    }
    box.appendChild(el('div', { class: 'reg-row' },
      el('span', { class: 'who', text: '小美犀 BR' }),
      el('span', { class: 'u', text: '不需登錄 inbound URL（我方主動呼叫 PMS）', style: 'color:#6b7280' }),
    ));
    card.appendChild(el('div', {},
      el('div', { class: 'tunnel-hint', text: '登錄進各環境 PMS「第三方廠商設定」的 URL：' }),
      box,
    ));
  }
  if (t && t.error) card.appendChild(el('div', { class: 'tunnel-warn', text: `⚠ ${t.error}` }));
  return card;
}

async function tunnelAction(action) {
  state.tunnelBusy = true; render();
  try {
    if (action === 'start') {
      const r = await api.startTunnel();   // 後端最多等 20 秒,期間 UI 顯示「處理中…」
      if (r && r.ok === false) state.tunnel = { running: false, error: r.error };
      else state.tunnel = await api.getTunnelStatus();
    } else {
      if (action === 'stop') await api.stopTunnel();
      state.tunnel = await api.getTunnelStatus();
    }
  } catch (e) {
    state.tunnel = { running: false, error: String(e) };
  }
  state.tunnelBusy = false; render();
}

function copyText(text, ev) {
  const done = () => {
    const b = ev && ev.currentTarget;
    if (b) { const old = b.textContent; b.textContent = '已複製 ✓'; setTimeout(() => { b.textContent = old; }, 1200); }
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else fallbackCopy(text, done);
}

function fallbackCopy(text, done) {
  const ta = document.createElement('textarea');
  ta.value = text; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); done(); } catch (e) { /* 忽略 */ }
  document.body.removeChild(ta);
}

// 啟動
init();
