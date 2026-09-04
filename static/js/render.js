/* 渲染入口:render() 清空 #app 重掛 layout(三頁分發:①設定 ②監控 ③結果)。 */
import { el } from './el.js';
import { state } from './state.js';
import { renderSetup } from './views/setup.js';
import { renderMonitor } from './views/monitor.js';
import { renderResults } from './views/results.js';

export function render() {
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
    mk('results', '③ 結果分析', state.runStep === 'done' && state.activeTab !== 'results' ? 'yellow' : null),
    el('div', { class: 'foot' }, document.createTextNode('mock-server v.next'), el('br'), document.createTextNode('三分頁常駐・自由切換')),
  );
}
