/** 受控分发（按授权地区领用金记录）接口封装。 */
import { request } from './client'

export type Brief = Record<string, unknown>

export async function controlPost<T = any>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  return (await response.json()) as T
}

export async function controlGet<T = any>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  return (await response.json()) as T
}

export function downloadUrl(code: string): string {
  return `/api/controlled-distribution/claims/${encodeURIComponent(code)}/download`
}

export const controlApi = {
  meta: () => controlGet('/api/controlled-distribution/meta'),
  grants: (subscriber?: string | number) =>
    controlGet(`/api/controlled-distribution/grants${subscriber ? `?subscriber=${encodeURIComponent(String(subscriber))}` : ''}`),
  changeGrant: (body: Record<string, unknown>) => controlPost('/api/controlled-distribution/grants', body),
  revokeGrant: (id: number | string, body: Record<string, unknown> = {}) =>
    controlPost(`/api/controlled-distribution/grants/${id}/revoke`, body),
  preview: (body: Record<string, unknown>) => controlPost('/api/controlled-distribution/preview', body),
  createClaim: (body: Record<string, unknown>) => controlPost('/api/controlled-distribution/claims', body),
  claims: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
    return controlGet(`/api/controlled-distribution/claims?${qs.toString()}`)
  },
  claim: (code: string) => controlGet(`/api/controlled-distribution/claims/${encodeURIComponent(code)}`),
  continueClaim: (code: string) =>
    controlPost(`/api/controlled-distribution/claims/${encodeURIComponent(code)}/continue`),
  history: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
    return controlGet(`/api/controlled-distribution/history?${qs.toString()}`)
  },
  publishHistory: (goldenPublishId: number | string) =>
    controlGet(`/api/golden_publish/${goldenPublishId}/claim-history`),
  publishedRows: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
    return controlGet(`/api/controlled-distribution/published-rows?${qs.toString()}`)
  },
  adjustAttribution: (rowId: number | string, body: Record<string, unknown>) =>
    controlPost(`/api/controlled-distribution/published-rows/${rowId}/attribution`, body),
}
