/* ① 設定頁:環境卡 + 對外隧道卡 + 真實環境提示 + 案例矩陣 + 參數化表單 + sticky 啟動列。 */
import { el } from '../el.js';
import { state } from '../state.js';
import { moduleLabel, collectOverrides } from '../util.js';
import { render } from '../render.js';
import { renderTunnelCard } from '../tunnel.js';
import { startRun } from '../run.js';

export function renderSetup() {
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
  const allScenarios = state.modules.flatMap(m => m.vendors.flatMap(v => v.scenarios)).filter(s => s.implemented);
  const allOn = totalSelected === allScenarios.length && allScenarios.length > 0;
  matrix.appendChild(el('div', { class: 'matrix-head' },
    el('div', { class: 'section-label', text: '模組 × 廠商 × 測試案例', style: 'margin:0' }),
    el('div', { style: 'display:flex;align-items:center;gap:10px' },
      el('div', { class: 'sel', text: `已選 ${totalSelected} 案例` }),
      el('button', { class: 'btn-secondary matrix-bulk', text: allOn ? '✕ 清除全選' : '☑ 全選',
        onclick: () => {
          for (const s of allScenarios) state.checked[s.id] = !allOn;
          render();
        } }),
    ),
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
      // 廠商 chip 列(切換 activeVendor)+ 本廠商全選/清除
      const activeV = m.vendors.find(v => v.id === (state.activeVendor[m.module] || m.vendors[0]?.id)) || m.vendors[0];
      const chipRow = el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:6px' });
      for (const v of m.vendors) {
        const active = v.id === activeV.id;
        chipRow.appendChild(el('div', {
          class: 'vendor-chip' + (active ? ' active' : ''),
          onclick: (e) => { e.stopPropagation(); state.activeVendor[m.module] = v.id; render(); },
          style: (active
            ? 'background:rgba(255,138,61,.18);border:1.5px solid #ff8a3d'
            : 'background:rgba(255,255,255,.04);border:1.5px solid rgba(255,255,255,.16)')
            + ';padding:4px 12px;gap:10px;align-items:center;display:inline-flex',
        },
          el('span', { style: `font:600 12px 'JetBrains Mono';color:${active ? '#fff' : '#d7dae0'}`, text: v.label }),
          // 勾選數:徽章式呈現,與 label 明確分離
          el('span', {
            style: `font:600 10.5px 'JetBrains Mono';padding:1px 8px;border-radius:9px;`
                 + (active ? 'background:rgba(255,138,61,.28);color:#ffd9b8' : 'background:rgba(255,255,255,.09);color:#b9bfca'),
            title: '已勾選案例數 / 該廠商案例數',
            text: `${v.scenarios.filter(s => state.checked[s.id])}/${v.scenarios.length}`,
          }),
        ));
      }
      // 本廠商(作用中)全選/清除
      if (activeV && activeV.scenarios.length) {
        const vAll = activeV.scenarios.every(s => state.checked[s.id]);
        chipRow.appendChild(el('button', {
          class: 'btn-secondary matrix-bulk', text: vAll ? '✕ 清除本商' : '☑ 全選本商',
          title: `全選/清除「${activeV.label}」的案例`,
          onclick: (e) => { e.stopPropagation(); for (const s of activeV.scenarios) state.checked[s.id] = !vAll; render(); },
        }));
      }
      body.appendChild(chipRow);
      // 當前選中廠商的案例清單(activeV 已於上方求得)
      if (activeV) for (const s of activeV.scenarios) {
        const ck = !!state.checked[s.id];
        const hasParams = !!(s.params && s.params.length);
        body.appendChild(el('div', { class: 'scenario', onclick: () => { state.checked[s.id] = !state.checked[s.id]; render(); } },
          el('span', { class: 'box' + (ck ? ' checked' : '') }, ck ? el('span', { text: '✓' }) : null),
          el('span', { class: 'name', text: s.name }),
          hasParams ? el('span', {
            class: 'gear' + (state.paramOpen[s.id] ? ' on' : '') + (paramTouchedCount(s.id) ? ' dirty' : ''),
            text: '⚙', title: '案例參數',
            onclick: (e) => { e.stopPropagation(); state.paramOpen[s.id] = !state.paramOpen[s.id]; render(); },
          }) : null,
          el('span', { class: 'ep', text: s.endpoint }),
          s.implemented ? null : el('span', { class: 'tag', text: '待開發' }),
        ));
        // 參數化(設計 §8):有宣告參數的案例,⚙ 展開由 /scenarios 詮釋資料驅動的表單
        if (hasParams && state.paramOpen[s.id]) body.appendChild(renderParamForm(s));
      }
      mod.appendChild(body);
    }
    stack.appendChild(mod);
  }
  matrix.appendChild(stack);
  page.appendChild(matrix);

  // sticky 啟動列
  const canLaunch = totalSelected > 0 && envMeta.ready !== false && state.runStep !== 'running';
  const overridden = Object.keys(collectOverrides(Object.keys(state.checked).filter(k => state.checked[k]))).length;
  page.appendChild(el('div', { class: 'launch-bar' },
    el('div', { class: 'meta', text: `環境 ${state.env} ・ 已選 ${totalSelected} 案例${overridden ? ` ・ 參數覆寫 ${overridden} 案例` : ''}` }),
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

// ---- 案例參數化表單(設計 §8:全程由 /scenarios 詮釋資料驅動,廠商視角零改動) ----
function paramTouchedCount(caseId) {
  const t = state.paramTouched[caseId] || {};
  return Object.values(t).filter(Boolean).length;
}

function renderParamForm(s) {
  const box = el('div', { class: 'param-form' });
  const touched = state.paramTouched[s.id] || {};
  const edits = state.paramEdits[s.id] || {};
  for (const sp of s.params) {
    const isTouched = !!touched[sp.key];
    const input = el('input', {
      class: 'param-input' + (isTouched ? ' touched' : ''),
      type: 'text',
      value: isTouched ? String(edits[sp.key] ?? '') : '',
      placeholder: sp.dynamic ? '自動(每次執行產生)' : (sp.default != null ? String(sp.default) : ''),
      title: sp.hint || sp.label,
    });
    input.oninput = () => {
      state.paramEdits[s.id] = state.paramEdits[s.id] || {};
      state.paramTouched[s.id] = state.paramTouched[s.id] || {};
      state.paramEdits[s.id][sp.key] = input.value;
      state.paramTouched[s.id][sp.key] = true;   // 動過才進 overrides——保持請求乾淨
    };
    box.appendChild(el('div', { class: 'param-row' },
      el('span', { class: 'param-label', text: sp.label + (sp.dynamic ? ' ⚡' : ''), title: sp.hint || '' }),
      input,
      el('span', { class: 'param-type', text: sp.type }),
    ));
  }
  const n = paramTouchedCount(s.id);
  box.appendChild(el('div', { class: 'param-foot' },
    el('span', { class: 'param-note', text: n ? `已覆寫 ${n} 欄(其餘用預設)` : '未調整 = 全用預設值;清空欄位送空值可測缺欄負面路徑' }),
    el('button', { class: 'btn-secondary param-reset', text: '↺ 還原預設',
      onclick: (e) => { e.stopPropagation(); delete state.paramEdits[s.id]; delete state.paramTouched[s.id]; render(); } }),
  ));
  return box;
}
