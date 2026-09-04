/* API client:GET /environments /scenarios;POST /runs(202 立即回)→polling GET /runs/<id>;隧道三端點。 */
const API = '';
export const api = {
  getEnvironments: () => fetch(API + '/environments').then(r => r.json()),
  getScenarios: () => fetch(API + '/scenarios').then(r => r.json()),
  startRun: (env, ids, overrides) => fetch(API + '/runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign(
      { environment: env, scenario_ids: ids },
      overrides && Object.keys(overrides).length ? { overrides } : {})),
  }).then(r => r.json()),
  getRun: (id) => fetch(API + `/runs/${id}`).then(r => r.json()),
  getResults: (id) => fetch(API + `/runs/${id}/results`).then(r => r.json()),
  getTunnelStatus: () => fetch(API + '/tunnel/status').then(r => r.json()),
  startTunnel: () => fetch(API + '/tunnel/start', { method: 'POST' }).then(r => r.json()),
  stopTunnel: () => fetch(API + '/tunnel/stop', { method: 'POST' }).then(r => r.json()),
};
