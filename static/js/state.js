/* 全域狀態(PMS 測試主控台 — vanilla SPA:state → render;使用者操作改 state 後重渲染)。 */
export const state = {
  activeTab: 'setup',
  environments: [],        // [{id,desc,color,ready,pms_url}]
  env: null,               // 當前選環境 id
  modules: [],             // [{module,label,vendors:[{id,label,scenarios:[{id,name,endpoint,implemented,params}]}]}]
  activeVendor: {},        // module → 當前選廠商 id
  expanded: {},            // module → bool
  checked: {},             // case_id → bool
  paramEdits: {},          // case_id → {param_key: 使用者輸入字串}(參數化表單)
  paramTouched: {},        // case_id → {param_key: bool}——動過的欄位才會進 overrides payload
  paramOpen: {},           // case_id → bool(參數表單展開)
  runStep: 'idle',         // idle / running / done
  caseResults: [],         // CaseResult[]
  runId: null,
  resultsView: 'summary',
  selectedCase: null,      // 結果頁「案例檢視」選中的 case_id
  caseDetailTab: 'http',   // 案例明細內部分頁:http / json / error / snapshot
  pollTimer: null,
  launchMsg: null,
  summaryExpand: {},     // 摘要頁統計卡展開狀態(total/pass/fail/dur)
  snapshotPreview: false, // 摘要頁整批快照預覽開合
  tunnel: null,         // /tunnel/status 結果(對外隧道卡)
  tunnelBusy: false,
};
