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
    if (k === 'class') e.className = v;
    else if (k === 'onclick') e.onclick = v;
    else if (k === 'text') e.textContent = v;
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
  modules: [],             // [{module, scenarios:[{id,vendor,name,endpoint,implemented}]}]
  expanded: {},            // module → bool
  checked: {},             // case_id → bool
  runStep: 'idle',         // idle / running / done
  caseResults: [],         // CaseResult[]
  runId: null,
  resultsView: 'summary',
  pollTimer: null,
  launchMsg: null,
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
};

// ---- 初始化 ----
async function init() {
  const [envs, mods] = await Promise.all([api.getEnvironments(), api.getScenarios()]);
  state.environments = envs;
  state.modules = mods;
  state.env = envs[0]?.id || 'LOCAL_OFFLINE';
  // 預設勾選所有已實作案例
  for (const m of mods) for (const s of m.scenarios) if (s.implemented) state.checked[s.id] = true;
  render();
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
    const impl = m.scenarios.filter(s => s.implemented);
    const selCount = m.scenarios.filter(s => state.checked[s.id]).length;
    const expanded = state.expanded[m.module];
    const mod = el('div', { class: 'module' },
      el('div', { class: 'module-head', onclick: () => { state.expanded[m.module] = !expanded; render(); } },
        el('div', { class: 'left' },
          el('span', { class: 'label', text: moduleLabel(m.module) }),
          el('span', { class: 'vendor', text: m.scenarios[0]?.vendor || '' }),
        ),
        el('div', { style: 'display:flex;align-items:center;gap:12px' },
          el('span', { class: 'count', text: `${selCount}/${m.scenarios.length}` }),
          el('span', { style: 'font-size:11px;color:#6b7280', text: expanded ? '▲' : '▼' }),
        ),
      ),
    );
    if (expanded) {
      const body = el('div', { class: 'module-body' });
      for (const s of m.scenarios) {
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
    el('button', { class: 'btn-launch', text: state.runStep === 'running' ? '執行中…' : '🚀 啟動測試', onclick: startRun, disabled: !canLaunch ? '' : null }),
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
    page.appendChild(el('div', { class: 'empty', text: '尚未啟動測試，請回到「① 環境/案例設定���勾選案例並啟動' }));
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
  const tabs = [['summary', '摘要'], ['steps', '逐步紀錄'], ['diff', 'Diff 比對'], ['timeline', '時序圖'], ['category', '失敗歸類']];
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

  const passed = state.caseResults.filter(c => c.status === 'PASS').length;
  const failed = state.caseResults.filter(c => c.status === 'FAIL').length;
  const totalDur = state.caseResults.reduce((a, c) => a + (c.duration_ms || 0), 0);
  const failCase = state.caseResults.find(c => c.status === 'FAIL');

  if (state.resultsView === 'summary') {
    page.appendChild(el('div', { class: 'summary-cards' },
      statCard('總案例數', state.caseResults.length, ''),
      statCard('Passed', passed, 'pass'),
      statCard('Failed', failed, 'fail'),
      statCard('總耗時', (totalDur / 1000).toFixed(1) + 's', ''),
    ));
  } else if (state.resultsView === 'steps') {
    const list = el('div', { class: 'list-stack' });
    for (const c of state.caseResults) {
      list.appendChild(el('div', { class: 'case-row' },
        el('span', { class: 'st st-' + c.status, text: c.status }),
        el('span', { class: 'name', text: `${moduleLabel(c.module)} / ${c.vendor} / ${c.scenario_name}` }),
        el('span', { class: 'ep', text: c.endpoint }),
        el('span', { class: 'dur', text: c.duration_ms ? c.duration_ms + 'ms' : '—' }),
      ));
    }
    page.appendChild(list);
  } else if (state.resultsView === 'diff') {
    if (!failCase) {
      page.appendChild(el('div', { class: 'empty', text: '本次執行沒有失敗案例，無 Diff 可比對' }));
    } else {
      const box = el('div', { class: 'diff-box' },
        el('div', { class: 'diff-title', text: `🛑 ${failCase.scenario_name}（${failCase.endpoint}）` }),
      );
      const rows = (failCase.diff && failCase.diff.length) ? failCase.diff : autoDiff(failCase);
      for (const d of rows) {
        box.appendChild(el('div', { class: 'diff-row' },
          el('span', { class: 'f', text: d.field }),
          el('span', { class: 'e', text: `期望 ${fmtVal(d.expected)}` }),
          el('span', { class: 'a', text: `實際 ${fmtVal(d.actual)}` }),
        ));
      }
      page.appendChild(box);
    }
  } else if (state.resultsView === 'timeline') {
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
    page.appendChild(list);
  } else if (state.resultsView === 'category') {
    if (!failCase) {
      page.appendChild(el('div', { class: 'empty', text: '本次執行沒有失敗案例' }));
    } else {
      const cats = {};
      for (const c of state.caseResults.filter(x => x.status === 'FAIL')) {
        const k = c.error_category || 'UNKNOWN';
        (cats[k] = cats[k] || []).push(c);
      }
      for (const [cat, cases] of Object.entries(cats)) {
        page.appendChild(el('div', { class: 'cat-box' },
          el('div', { class: 'diff-title', text: `${categoryLabel(cat)}（${cases.length} 案例）` }),
          el('div', { class: 'nt-body', text: cases.map(c => c.scenario_name).join('、') }),
        ));
      }
    }
  }
  return page;
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

// 啟動
init();
