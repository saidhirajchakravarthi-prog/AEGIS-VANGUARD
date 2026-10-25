export type DraftStatus = 'Draft' | 'In review' | 'Approved' | 'Rejected' | 'Changes requested'

export interface Finding {
  id: number
  draft_id: number
  category: string
  policy_id: number | string | null
  severity: 'low' | 'medium' | 'high'
  title: string
  description: string
  matched_text: string | null
  status: 'potential_issue'
  created_at: string
}

export interface Draft {
  id: number
  title: string
  author: string
  channel: string
  content: string
  evidence_reference: string | null
  status: DraftStatus
  created_at: string
  updated_at: string
  analyzed_at: string | null
  finding_count: number
  findings: Finding[]
  analysis: AnalysisRun | null
  evidence: EvidenceReference[]
  versions: DraftVersion[]
  proposed_edits: ProposedEdit[]
}

export type EvidenceStatus =
  | 'supported_by_reviewed_evidence'
  | 'contradicted_by_reviewed_evidence'
  | 'insufficient_evidence'
  | 'evidence_missing'
  | 'not_checked'

export interface ClaimFinding {
  exact_quote: string
  category: string
  severity: 'low' | 'medium' | 'high'
  explanation: string
  rationale: string
  policy_id: string | null
  evidence_status: EvidenceStatus
  evidence_ids: number[]
  recommended_action: string
  suggested_rewrite: string | null
  human_review_required: boolean
}

export interface AnalysisReport {
  summary: string
  findings: ClaimFinding[]
  missing_information: string[]
}

export interface AnalysisRun {
  id: number
  mode: 'ai_assisted' | 'rules_only'
  outcome: string
  failure_code: string | null
  provider: string
  model: string
  policy_version: number
  content_version: number
  evidence_version: number
  is_current: boolean
  created_at: string
  report: AnalysisReport
}

export interface EvidenceReference {
  id: number
  label: string
  source_url: string | null
  excerpt: string | null
  evidence_status: 'user_supplied_unverified'
  actor: string
  created_at: string
}

export interface DraftVersion {
  id: number
  version: number
  content: string
  actor: string
  change_note: string
  created_at: string
}

export interface ProposedEdit {
  id: number
  analysis_run_id: number
  original_text: string
  suggested_text: string
  rationale: string
  status: 'proposed' | 'accepted' | 'rejected'
  actor: string | null
  created_at: string
  decided_at: string | null
}

export interface Rule {
  id: number
  name: string
  category: string
  term: string | null
  replacement: string | null
  description: string
  enabled: boolean
}

export type RuleCategory = 'terminology' | 'required_term' | 'numerical_claim' | 'evidence_reference'

export interface RuleInput {
  name: string
  category: RuleCategory
  term: string
  replacement: string
  description: string
  enabled: boolean
}

export interface RuleRevision {
  version: number
  rule: Rule
  actor: string
  created_at: string
}

export interface AuditEvent {
  id: number
  action: string
  actor: string
  target_type: string
  target_id: number
  target_title: string
  details: string
  created_at: string
}

export interface GovernanceLearning {
  run_id: number | null
  recorded_at: string | null
  window: { starts_at: string; ends_at: string; days: number }
  basis: {
    method: string
    completed_decisions: number
    decision_ids: number[]
    unverified_actor_labels: boolean
  }
  recommendations: Array<{
    key: string
    recommendation: string
    basis: {
      policy_id: number | null
      category: string
      finding_title: string
      draft_ids: number[]
      finding_ids: number[]
      decision_ids: number[]
    }
    requires_human_policy_review: boolean
    automatically_applied: false
  }>
  notice: string
}

export interface Dashboard {
  total_submissions: number
  in_review: number
  approved: number
  potential_issues: number
  approval_rate: number
  enabled_rules: number
  findings_by_severity: Record<string, number>
  findings_by_category: Record<string, number>
  review_decisions: Record<string, number>
  unresolved_evidence_requirements: number
  latest_analysis_mode: 'ai_assisted' | 'rules_only' | 'not_run'
}

export interface IntelligenceStatus {
  provider: string
  model: string | null
  configured: boolean
  last_request_succeeded: boolean | null
  last_request_status: string
  last_failure_code: string | null
  last_successful_request_at: string | null
  live_ai_claim: boolean
}

export interface AssistantResult {
  mode: 'ai_assisted' | 'rules_only'
  outcome: string
  failure_code?: string | null
  answer: {
    answer: string
    supporting_evidence_ids: number[]
    human_review_required: boolean
  }
}
