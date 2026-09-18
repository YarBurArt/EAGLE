import { api } from '../shared/api/axios'

const BASE = '/cmd'

export const chainApi = {
  list: () => api.get(`${BASE}/chains`).then((res) => res.data),

  create: (chainName) =>
    api.post(`${BASE}/new-chain`, { chain_name: chainName }).then((res) => res.data),
  delete: (chainId) => api.delete(`${BASE}/chains/${chainId}`).then((res) => res.data),

  getChainInfo: (chainId) => api.get(`${BASE}/chain-phase/${chainId}`).then((res) => res.data),

  getChainWithSteps: (chainId) => api.get(`${BASE}/chain/${chainId}`).then((res) => res.data),

  nextPhase: (chainId) => api.post(`${BASE}/next-phase/${chainId}`).then((res) => res.data),
  setPhase: (chainId, phaseName) =>
    api
      .post(`${BASE}/set-phase/${chainId}`, null, {
        params: { phase_name: phaseName },
      })
      .then((res) => res.data),
  // can depend on current UCKC phase
  rejectLastStep: (chainName) => api.post(`${BASE}/reject-s/${chainName}`).then((res) => res.data),
  // stop chain execution , works after 30-120 sec cuz all commands via Mythic
  cancelChain: (chainId, chainName) =>
    api
      .post(`${BASE}/cancel-chain/${chainId}`, null, {
        params: { chain_name: chainName },
      })
      .then((res) => res.data),

  runChain: (chainId) =>
    api
      .post(`${BASE}/run-chain/${chainId}`, null, { params: { zero_display_id: 0 } })
      .then((res) => res.data),

  getCurrentUser: () => api.get('/users/me').then((res) => res.data),
}
