/* ③ 結果分析頁(5 子檢視):摘要 | 案例檢視(主從明細) | 時序圖 | 失敗歸類 + 繼續測試。 */
import { el } from '../el.js';
import { state } from '../state.js';
import { moduleLabel, renderJson, downloadJson, statCard, fmtVal, categoryLabel, kv, toggleStep } from '../util.js';
import { render } from '../render.js';

export function renderResults() {
  const page = el('div', { class: 'page' });
  // 頂層分頁:摘要 | 案例檢視(主從明細) | 時序圖 | 失敗歸類 + 繼續測試返回設定頁
  const tabs = [['summary', '摘要'], ['cases', '案例檢視'], ['timeline', '時序圖'], ['category', '失敗歸類']];
  const tabRow = el('div', { class: 'result-tabs results-head' });
  for (const [id, label] of tabs) {
    tabRow.appendChild(el('div', {
      class: 'result-tab ' + (state.resultsView === id ? 'active' : ''),
      onclick: () => { state.resultsView = id; render(); },
      text: label,
    }));
  }
  // 繼續測試:保留勾選與參數,返回 ① 環境/案例設定
  tabRow.appendChild(el('button', {
    class: 'btn-secondary continue-btn', text: '↩ 繼續測試(返回設定)',
    onclick: () => { state.activeTab = 'setup'; render(); },
  }));
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

// ---- 摘要:統計卡(可點擊展開條列) + 整批快照(先預覽再下載) ----
// 案例路由條列格式:模組 / 廠商 / 路由路徑(+案例名)
function caseRouteText(c) {
  return `${moduleLabel(c.module)} / ${c.vendor} / ${c.endpoint}`;
}

function renderSummary() {
  const passed = state.caseResults.filter(c => c.status === 'PASS');
  const failed = state.caseResults.filter(c => c.status === 'FAIL');
  const totalDur = state.caseResults.reduce((a, c) => a + (c.duration_ms || 0), 0);
  state.summaryExpand = state.summaryExpand || {};
  const exp = state.summaryExpand;

  // 可點擊統計卡:單選式展開——點別張卡即覆蓋目前的展開(同一時間只展開一個清單)
  const mkStat = (key, label, val, cls, list) => {
    const card = statCard(label + (list && list.length ? (exp[key] ? ' ▴' : ' ▾') : ''), val, cls);
    if (list && list.length) {
      card.classList.add('clickable');
      card.onclick = () => {
        const on = !exp[key];
        for (const k of Object.keys(exp)) exp[k] = false;   // 互斥:其他卡收合
        exp[key] = on;
        state.snapshotPreview = false;
        render();
      };
    }
    return card;
  };
  const wrap = el('div', {});
  wrap.appendChild(el('div', { class: 'summary-cards' },
    mkStat('total', '總案例數', state.caseResults.length, '', state.caseResults),
    mkStat('pass', 'Passed', passed.length, 'pass', passed),
    mkStat('fail', 'Failed', failed.length, 'fail', failed),
    mkStat('dur', '總耗時', (totalDur / 1000).toFixed(1) + 's', '', state.caseResults),
  ));

  // 展開條列:總案例/Passed/Failed → 模組、廠商、路由路徑;總耗時 → 逐案耗時(降冪)
  const expandKey = Object.keys(exp).find(k => exp[k]);
  if (expandKey) {
    let list = expandKey === 'pass' ? passed : expandKey === 'fail' ? failed : state.caseResults;
    if (expandKey === 'dur') list = [...state.caseResults].sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0));
    const box = el('div', { class: 'cat-box stat-detail' },
      el('div', { class: 'detail-title', text: expandKey === 'dur' ? '逐案耗時(降冪)' : '案例清單(模組 / 廠商 / 路由路徑)' }));
    for (const c of list) {
      box.appendChild(el('div', { class: 'stat-detail-row' },
        el('span', { class: 'st st-' + c.status, text: c.status }),
        el('span', { class: 'route', text: caseRouteText(c), title: c.scenario_name }),
        el('span', { class: 'nm', text: c.scenario_name }),
        expandKey === 'dur' ? el('span', { class: 'dur', text: c.duration_ms != null ? c.duration_ms + 'ms' : '—' }) : null,
      ));
    }
    wrap.appendChild(box);
  }

  // 整批快照:先預覽 → 再下載(預覽即將下載的完整 JSON)
  const snapObj = { run_id: state.runId, environment: state.env, triggered_at: null, cases: state.caseResults };
  const snapArea = el('div', { style: 'margin-top:14px' },
    el('button', { class: 'btn-secondary', text: state.snapshotPreview ? '▲ 收起快照預覽' : '👁 預覽整批快照 (JSON)',
      onclick: () => { state.snapshotPreview = !state.snapshotPreview; render(); } }));
  if (state.snapshotPreview) {
    snapArea.appendChild(el('div', { class: 'json-col', style: 'margin-top:10px' },
      el('div', { class: 'http-lbl', text: `快照預覽(${state.caseResults.length} 案例・下載即此內容)` }),
      renderJson(snapObj),
      el('button', { class: 'btn-secondary', text: '📥 下載整批快照 (JSON)', style: 'margin-top:10px',
        onclick: () => downloadJson(`run-${state.runId || 'snapshot'}.json`, snapObj) }),
    ));
  }
  wrap.appendChild(snapArea);
  return wrap;
}

// ---- 時序圖(標籤:案例名 + 模組/廠商 + 路由路徑 條列) ----
function renderTimeline() {
  const max = Math.max(1, ...state.caseResults.map(c => c.duration_ms || 0));
  const list = el('div', { class: 'list-stack' });
  for (const c of state.caseResults) {
    const pct = Math.round(((c.duration_ms || 0) / max) * 100);
    const color = c.status === 'FAIL' ? '#ff5f56' : '#35d399';
    list.appendChild(el('div', { class: 'timeline-row' },
      el('div', { class: 'tname' },
        el('div', { class: 'nm', text: c.scenario_name }),
        el('div', { class: 'rt', text: `${moduleLabel(c.module)} / ${c.vendor}` }),
        el('div', { class: 'ep', text: c.endpoint, title: c.endpoint }),
      ),
      el('div', { class: 'timeline-track' }, el('div', { class: 'timeline-fill', style: `width:${pct}%;background:${color}` })),
      el('span', { class: 'tdur', text: c.duration_ms ? c.duration_ms + 'ms' : '—' }),
    ));
  }
  return list;
}

// ---- 失敗歸類(Given-When-Then 三段式描述:情境前提 / 操作觸發 / 預期 vs 實際) ----
function gwtBlocks(c) {
  const fs = c.failing_step || (c.steps || [])[0] || null;
  const rp = c.resolved_params && Object.keys(c.resolved_params).length
    ? ',參數 ' + Object.entries(c.resolved_params).map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`).join('、')
    : '';
  const given = `Given:於 ${state.env} 環境執行「${moduleLabel(c.module)} / ${c.vendor} / ${c.scenario_name}」${rp}`;
  const when = fs
    ? `When:發送 ${fs.method} ${fs.url}${fs.error ? '(連線失敗)' : ''}`
    : 'When:案例執行器完成但未留下 HTTP 交易紀錄';
  const actual = [];
  if (fs && fs.status_code != null) actual.push(`HTTP ${fs.status_code}`);
  actual.push(`分類 ${categoryLabel(c.error_category)}`);
  let hint = '';
  if (fs) {
    const rb = fs.error ? { message: fs.error } : fs.response_body;
    if (rb && typeof rb === 'object') {
      const bits = [];
      if (rb.code != null) bits.push(`code=${rb.code}`);
      if (rb.message != null) bits.push(`message=${String(rb.message).slice(0, 80)}`);
      if (bits.length) hint = `,回應 ${bits.join(' / ')}`;
    } else if (typeof rb === 'string' && rb) hint = `,回應 ${rb.slice(0, 80)}`;
  }
  const then = `Then:預期 2xx 且合約代碼 0000;實際 ${actual.join(' / ')}${hint}。💡 ${c.remediation || ''}`;
  return el('div', { class: 'gwt' },
    el('div', { class: 'g-line g-given', text: given }),
    el('div', { class: 'g-line g-when', text: when, title: when }),
    el('div', { class: 'g-line g-then', text: then }),
  );
}

function renderCategory() {
  const fails = state.caseResults.filter(x => x.status === 'FAIL');
  if (!fails.length) return el('div', { class: 'empty', text: '本次執行沒有失敗案例' });
  const cats = {};
  for (const c of fails) { const k = c.error_category || 'UNKNOWN'; (cats[k] = cats[k] || []).push(c); }
  const wrap = el('div', { class: 'list-stack' });
  for (const [cat, cases] of Object.entries(cats)) {
    const box = el('div', { class: 'cat-box' },
      el('div', { class: 'diff-title', text: `${categoryLabel(cat)}（${cases.length} 案例）` }),
    );
    for (const c of cases) {
      box.appendChild(el('div', { class: 'gwt-case' },
        el('div', { class: 'gwt-head' },
          el('span', { class: 'st st-' + c.status, text: c.status }),
          el('span', { class: 'gwt-name', text: `${c.scenario_name}（${moduleLabel(c.module)} / ${c.vendor}）` }),
          el('span', { class: 'dur', text: c.duration_ms ? c.duration_ms + 'ms' : '' }),
        ),
        gwtBlocks(c),
      ));
    }
    wrap.appendChild(box);
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
    // 參數化(設計 §8):標題列參數摘要 chip——本次實際用了什麼參數,報告可追溯
    renderParamChips(selected),
    tabRow,
  );
  if (state.caseDetailTab === 'http') detail.appendChild(renderHttpAudit(selected));
  else if (state.caseDetailTab === 'json') detail.appendChild(renderJsonAudit(selected));
  else if (state.caseDetailTab === 'error') detail.appendChild(renderErrorAnalysis(selected));
  else detail.appendChild(renderSnapshot(selected));
  return el('div', { class: 'browser' }, list, detail);
}

// 參數摘要 chip:label=value(resolved_params 為內部鍵,對照 /scenarios 詮釋資料顯示 label)
function paramLabelOf(caseId, key) {
  for (const m of state.modules) for (const v of m.vendors) {
    const s = (v.scenarios || []).find(x => x.id === caseId);
    if (s && s.params) { const sp = s.params.find(x => x.key === key); if (sp) return sp.label; }
  }
  return null;
}

function renderParamChips(c) {
  const rp = c.resolved_params;
  if (!rp || !Object.keys(rp).length) return null;
  const chips = Object.entries(rp).map(([k, v]) =>
    el('span', { class: 'param-chip', title: `${k} = ${fmtVal(v)}`, text: `${paramLabelOf(c.case_id, k) || k}=${fmtVal(v)}` }));
  return el('div', { class: 'param-chips' }, ...chips);
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

// JSON 稽核:請求/回應並排 + 期望值 + 欄位 Diff(§7 分級:參數覆寫=灰/真差異=紅/缺欄=琥珀)
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
  if (c.resolved_params && Object.keys(c.resolved_params).length) {
    wrap.appendChild(el('div', { class: 'json-col', style: 'margin-top:12px' },
      el('div', { class: 'http-lbl', text: '本次使用參數（resolved）' }),
      renderJson(c.resolved_params),
    ));
  }
  if (c.expected_payload) {
    wrap.appendChild(el('div', { class: 'json-col', style: 'margin-top:12px' },
      el('div', { class: 'http-lbl', text: 'Expected payload（通關種子・echo 欄位已按本次參數回填）' }),
      renderJson(c.expected_payload),
    ));
  }
  const rows = (c.diff && c.diff.length) ? c.diff : [];
  if (rows.length) {
    const nEcho = rows.filter(r => r.kind === 'param_echo').length;
    const box = el('div', { class: 'diff-box', style: 'margin-top:12px' },
      el('div', { class: 'diff-title', text: `欄位 Diff 比對（${rows.length} 項${nEcho ? `・${nEcho} 參數覆寫` : ''}）` }),
      el('div', { class: 'diff-row diff-head' },
        el('span', { class: 'f', text: '欄位' }), el('span', { class: 'e', text: '期望' }),
        el('span', { class: 'a', text: '實際' }), el('span', { class: 'k', text: '分級' }),
      ),
    );
    for (const d of rows) {
      const kind = d.kind || (d.actual == null ? 'missing' : 'mismatch');
      box.appendChild(el('div', { class: 'diff-row k-' + kind },
        el('span', { class: 'f', text: d.field }),
        el('span', { class: 'e', text: fmtVal(d.expected) }),
        el('span', { class: 'a', text: fmtVal(d.actual) }),
        el('span', { class: 'k k-badge-' + kind,
                     text: kind === 'param_echo' ? '參數覆寫' : kind === 'missing' ? '缺欄' : '真差異' }),
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
    resolved_params: c.resolved_params,
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
