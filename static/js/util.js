/* 共用工具:模組標籤/JSON 渲染與下載/統計卡/格式化/分類標籤/參數收集/剪貼簿。 */
import { el } from './el.js';
import { state } from './state.js';

export function moduleLabel(id) {
  return { parking: '🚗 停車車辨', amenity: '🦏 房務備品', keycard: '🔑 門禁製卡', roomcontrol: '🌡️ 房控' }[id] || id;
}

// 收集「已勾選案例」的 overrides(只有動過的欄位會進 payload)
export function collectOverrides(checkedIds) {
  const out = {};
  for (const cid of checkedIds) {
    const t = state.paramTouched[cid];
    if (!t) continue;
    const edits = state.paramEdits[cid] || {};
    const kv = {};
    for (const [k, on] of Object.entries(t)) if (on && edits[k] !== undefined) kv[k] = edits[k];
    if (Object.keys(kv).length) out[cid] = kv;
  }
  return out;
}

export function toggleStep(e) {
  const head = e.currentTarget, step = head.parentNode;
  if (step) step.classList.toggle('open');
}

export function kv(label, val) {
  if (val == null || (typeof val === 'object' && Object.keys(val).length === 0)) return null;
  return el('div', { class: 'kv' },
    el('span', { class: 'kv-k', text: label }),
    el('div', { class: 'kv-v' }, renderJson(val)),
  );
}

export function renderJson(val) {
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

export function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

export function statCard(label, val, cls) {
  return el('div', { class: 'stat-card ' + cls },
    el('div', { class: 'lbl', text: label }),
    el('div', { class: 'val', text: String(val) }),
  );
}

export function autoDiff(c) {
  // 無後端 diff 時，至少顯示 status 一列
  return [{ field: 'status', expected: 'PASS', actual: c.status }];
}

export function fmtVal(v) {
  if (v === null) return 'null';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function categoryLabel(cat) {
  return {
    FIELD_MISMATCH: '欄位缺失／型別錯誤', STATUS_CODE: '狀態碼非預期',
    TIMEOUT: '連線逾時／錯誤', UNIMPLEMENTED: '案例尚無執行器', UNKNOWN_SCENARIO: '未知案例',
    UNKNOWN: '未分類',
  }[cat] || cat;
}

export function copyText(text, ev) {
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
