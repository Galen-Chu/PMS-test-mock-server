/* 🌐 對外隧道卡(真實環境串接):ngrok 狀態/啟停/各廠商註冊 URL。 */
import { el } from './el.js';
import { state } from './state.js';
import { api } from './api.js';
import { copyText } from './util.js';
import { render } from './render.js';

export function renderTunnelCard() {
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
    el('button', { class: 'btn-secondary', text: '▶ 啟動隧道(模擬前端)', title: '以 ngrok 建立對外隧道,模擬前端/邊緣端供真實環境回呼', disabled: busy || running,
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
