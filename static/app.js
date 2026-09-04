/* PMS 測試主控台 — 進入點(vanilla SPA,原生 ES modules,無建置工具)
 * 結構:state → render;使用者操作改 state 後重渲染。
 * 三頁:①設定(環境卡+案例矩陣+啟動) ②監控(步驟條+逐案例) ③結果(5 子檢視)
 * 2026-09-04 由單檔拆分為 js/ 模組群(純搬家零行為變更);本檔僅保留 init 與啟動。
 */
import { state } from './js/state.js';
import { api } from './js/api.js';
import { render } from './js/render.js';

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

// 啟動
init();
