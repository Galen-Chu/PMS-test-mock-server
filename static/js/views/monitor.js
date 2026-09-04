/* ② 監控頁:三步驟條 + 逐案例列(狀態/名稱/耗時)。 */
import { el } from '../el.js';
import { state } from '../state.js';
import { moduleLabel } from '../util.js';

export function renderMonitor() {
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
