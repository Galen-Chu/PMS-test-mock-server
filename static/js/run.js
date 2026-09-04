/* 啟動測試 + polling:POST /runs → 600ms 輪詢至非 RUNNING。 */
import { state } from './state.js';
import { api } from './api.js';
import { collectOverrides } from './util.js';
import { render } from './render.js';

export async function startRun() {
  const ids = Object.keys(state.checked).filter(k => state.checked[k]);
  if (!ids.length) return;
  const overrides = collectOverrides(ids);
  state.launchMsg = null;
  let run;
  try {
    run = await api.startRun(state.env, ids, overrides);
  } catch (e) {
    state.launchMsg = `啟動失敗：${e}`;
    render(); return;
  }
  if (run.error) {
    // 後端拒絕（如 ENV_NOT_READY 回 409、overrides 驗證 400;fetch 不丟例外,需看 body）
    let detail = run.error;
    if (run.param) detail += `（參數 ${run.param}）`;
    else if (run.case) detail += `（案例 ${run.case}）`;
    if (run.valid) detail += `・可用：${Array.isArray(run.valid) ? run.valid.join(', ') : run.valid}`;
    state.launchMsg = `後端拒絕：${detail}`;
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
