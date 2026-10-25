import type { AssistantResult, AuditEvent, Dashboard, Draft, Finding, IntelligenceStatus, Rule, RuleInput, RuleRevision } from './types'

const API_BASE = import.meta.env.VITE_API_URL
  ?? (import.meta.env.PROD ? '/api' : 'http://127.0.0.1:8000/api')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new Error(`Cannot reach the API at ${API_BASE}. Start the backend and retry.`)
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? String(body.detail)
      : `Request failed (${response.status})`
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const getDashboard = () => request<Dashboard>('/dashboard')
export const getDrafts = () => request<Draft[]>('/drafts')
export const getDraft = (id: string | number) => request<Draft>(`/drafts/${id}`)
export const getRules = () => request<Rule[]>('/brand-rules')
export const getFindings = () => request<Finding[]>('/findings')
export const getAudit = () => request<AuditEvent[]>('/audit')
export const getIntelligenceStatus = () => request<IntelligenceStatus>('/intelligence/status')
export const createDraft = (input: { title: string; author: string; channel: string; content: string; evidence_reference: string }) =>
  request<Draft>('/submissions', { method: 'POST', body: JSON.stringify(input) })
export const analyzeDraft = (id: string | number) =>
  request<Draft>(`/drafts/${id}/analyze`, { method: 'POST' })
export const reviewDraft = (id: string | number, input: { action: 'approve' | 'reject' | 'request_changes'; comment: string }) =>
  request<Draft>(`/drafts/${id}/review`, { method: 'POST', body: JSON.stringify(input) })
export const addEvidence = (id: string | number, input: { label: string; source_url: string; excerpt: string }) =>
  request<Draft>(`/drafts/${id}/evidence`, { method: 'POST', body: JSON.stringify(input) })
export const askAssistant = (id: string | number, question: string) =>
  request<AssistantResult>(`/drafts/${id}/assistant`, { method: 'POST', body: JSON.stringify({ question }) })
export const decideProposedEdit = (draftId: number, editId: number, action: 'accept' | 'reject') =>
  request<Draft>(`/drafts/${draftId}/proposed-edits/${editId}/decision`, { method: 'POST', body: JSON.stringify({ action }) })
export const reviseDraft = (id: number, input: { content: string; evidence_reference: string; change_note: string }) =>
  request<Draft>(`/drafts/${id}/content`, { method: 'PUT', body: JSON.stringify(input) })
export const createRule = (input: RuleInput) =>
  request<Rule>('/brand-rules', { method: 'POST', body: JSON.stringify(input) })
export const updateRule = (id: number, input: RuleInput) =>
  request<Rule>(`/brand-rules/${id}`, { method: 'PUT', body: JSON.stringify(input) })
export const getRuleRevisions = (id: number) => request<RuleRevision[]>(`/brand-rules/${id}/versions`)
