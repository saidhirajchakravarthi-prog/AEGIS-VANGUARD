import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  Activity, AlertCircle, AlertTriangle, ArrowRight,
  Bell, BookOpenCheck, Check, CheckCircle2, ChevronDown, ChevronRight,
  CircleHelp, Clock3, FileCheck2, FilePlus2, FileText, Filter, LayoutDashboard,
  ListChecks, LoaderCircle, Menu, MoreHorizontal, PanelLeftClose, Plus, Search,
  Network, Shield, ShieldAlert, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  analyzeDraft, createDraft, getAudit, getDashboard, getDraft, getDrafts,
  getFindings, getIntelligenceStatus, getRules, reviewDraft, addEvidence,
  askAssistant, decideProposedEdit, reviseDraft, createRule, updateRule, getRuleRevisions,
} from './api'
import type { AuditEvent, Dashboard, Draft, Finding, IntelligenceStatus, Rule, RuleCategory, RuleRevision } from './types'
import './App.css'

const navigation = [
  { label: 'Overview', path: '/', icon: LayoutDashboard },
  { label: 'Submissions', path: '/submissions', icon: FileText },
  { label: 'Review queue', path: '/reviews', icon: ListChecks, badge: true },
  { label: 'Content findings', path: '/findings', icon: ShieldAlert },
]
const management = [
  { label: 'Brand rules', path: '/rules', icon: BookOpenCheck },
  { label: 'Audit history', path: '/audit', icon: Activity },
]

const dateLabel = (value: string) => new Date(value).toLocaleDateString(undefined, {
  month: 'short', day: 'numeric', year: 'numeric',
})
const timeLabel = (value: string) => new Date(value).toLocaleString(undefined, {
  month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
})
const statusClass = (status: string) => status.toLowerCase().replaceAll(' ', '-')

function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [rules, setRules] = useState<Rule[]>([])
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [intelligence, setIntelligence] = useState<IntelligenceStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false)

  const refresh = useCallback(async () => {
    setError('')
    const [metrics, allDrafts, allRules, allAudit, allFindings, aiStatus] = await Promise.all([
      getDashboard(), getDrafts(), getRules(), getAudit(), getFindings(), getIntelligenceStatus(),
    ])
    setDashboard(metrics)
    setDrafts(allDrafts)
    setRules(allRules)
    setAudit(allAudit)
    setFindings(allFindings)
    setIntelligence(aiStatus)
  }, [])

  useEffect(() => {
    let alive = true
    Promise.all([getDashboard(), getDrafts(), getRules(), getAudit(), getFindings(), getIntelligenceStatus()])
      .then(([metrics, allDrafts, allRules, allAudit, allFindings, aiStatus]) => {
        if (!alive) return
        setDashboard(metrics)
        setDrafts(allDrafts)
        setRules(allRules)
        setAudit(allAudit)
        setFindings(allFindings)
        setIntelligence(aiStatus)
      })
      .catch((cause: unknown) => {
        if (alive) setError(cause instanceof Error ? cause.message : 'Unable to connect to the Aegis API.')
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const title = useMemo(() => {
    if (location.pathname === '/') return 'Overview'
    if (location.pathname.startsWith('/submissions/new')) return 'New submission'
    if (location.pathname.startsWith('/drafts/')) return 'Submission review'
    if (location.pathname === '/submissions') return 'Submissions'
    if (location.pathname === '/reviews') return 'Review queue'
    if (location.pathname === '/findings') return 'Content findings'
    if (location.pathname === '/rules') return 'Brand rules'
    if (location.pathname === '/audit') return 'Audit history'
    return 'Overview'
  }, [location.pathname])

  const refreshAfterMutation = async () => {
    await refresh()
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <Link to="/" className="brand-lockup" aria-label="Aegis Vanguard overview" onClick={() => setMobileOpen(false)}>
          <span className="brand-mark"><Shield size={23} strokeWidth={2.2} /></span>
          <span className="brand-name">AEGIS<span>VANGUARD</span></span>
        </Link>
        <div className="workspace-switch">
          <span className="workspace-logo">L</span>
          <span className="workspace-copy"><strong>Local workspace</strong><small>Single-user mode · no login</small></span>
          <ChevronDown size={15} />
        </div>
        <p className="nav-caption">WORKSPACE</p>
        <nav className="side-nav" aria-label="Workspace navigation">
          {navigation.map(({ label, path, icon: Icon, badge }) => (
            <NavLink key={path} to={path} end={path === '/'} onClick={() => setMobileOpen(false)} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
              {badge && (dashboard?.in_review ?? 0) > 0 && <span className="nav-badge">{dashboard?.in_review}</span>}
            </NavLink>
          ))}
        </nav>
        <p className="nav-caption management-label">GOVERNANCE</p>
        <nav className="side-nav" aria-label="Governance navigation">
          {management.map(({ label, path, icon: Icon }) => (
            <NavLink key={path} to={path} onClick={() => setMobileOpen(false)} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="compliance-card">
            <div className="compliance-icon"><ShieldCheck size={16} /></div>
            <div><strong>Governance active</strong><span>{rules.filter((rule) => rule.enabled).length} rules are protecting your brand</span></div>
          </div>
          <button className="profile-button" type="button" onClick={() => window.alert('Local single-user mode. Authentication and role-based access are not enabled.')}>
            <span className="avatar avatar-blue">LR</span>
            <span className="profile-copy"><strong>Local reviewer</strong><small>Authentication not enabled</small></span>
            <MoreHorizontal size={18} />
          </button>
        </div>
      </aside>

      {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <main className="main-column" onClickCapture={(event) => {
        if (event.target instanceof Element && event.target.closest('a')) setMobileOpen(false)
      }}>
        <header className="topbar">
          <button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={19} /></button>
          <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div>
          <div className="topbar-actions">
            <span className={`environment ${intelligence?.live_ai_claim ? 'environment-ai' : ''}`}><span className="live-dot" />{intelligence?.live_ai_claim ? `AI analysis active · ${intelligence.model}` : intelligence?.configured ? intelligence.last_failure_code ? `AI unavailable · ${intelligence.last_failure_code}` : 'AI configured · not yet verified' : 'Rules-only mode'}</span>
            <button className="icon-button notification-button" aria-label="Notifications" onClick={() => navigate('/reviews')}><Bell size={18} /><i /></button>
            <button className="avatar avatar-blue top-avatar" aria-label="Local reviewer profile" onClick={() => window.alert('Local single-user mode. Authentication and role-based access are not enabled.')}>LR</button>
          </div>
        </header>
        <div className="page-content">
          {error && <div className="api-error" role="alert"><AlertCircle size={17} /><span><strong>Couldn’t load workspace data.</strong> {error} Check that the FastAPI server is running.</span><button className="text-action" onClick={() => { setLoading(true); refresh().catch((e: unknown) => setError(e instanceof Error ? e.message : 'Unable to connect.')).finally(() => setLoading(false)) }}>Retry</button></div>}
          {loading && !dashboard ? <LoadingState /> : (
            <Routes>
              <Route path="/" element={<Overview dashboard={dashboard} drafts={drafts} findings={findings} audit={audit} intelligence={intelligence} />} />
              <Route path="/intelligence" element={<IntelligenceGraph drafts={drafts} rules={rules} audit={audit} />} />
              <Route path="/submissions" element={<Submissions drafts={drafts} />} />
              <Route path="/submissions/new" element={<NewSubmission onCreate={async (input) => { const draft = await createDraft(input); await refreshAfterMutation(); navigate(`/drafts/${draft.id}`) }} />} />
              <Route path="/drafts/:draftId" element={<DraftDetail onMutation={refreshAfterMutation} intelligence={intelligence} />} />
              <Route path="/reviews" element={<ReviewQueue drafts={drafts} onReview={async (id, action, comment) => { await reviewDraft(id, { action, comment }); await refreshAfterMutation() }} />} />
              <Route path="/findings" element={<FindingsPage findings={findings} drafts={drafts} />} />
              <Route path="/rules" element={<RulesPage rules={rules} onMutation={refreshAfterMutation} />} />
              <Route path="/audit" element={<AuditPage events={audit} />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          )}
        </div>
      </main>
    </div>
  )
}

function LoadingState() {
  return <div className="loading-state"><LoaderCircle className="spin" size={25} /><span>Loading your governance workspace…</span></div>
}

function PageHeader({ eyebrow, title, description, children }: { eyebrow?: string; title: string; description: string; children?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1><p className="page-description">{description}</p></div>{children && <div className="heading-actions">{children}</div>}</div>
}

function Overview({ dashboard, drafts, findings, audit, intelligence }: { dashboard: Dashboard | null; drafts: Draft[]; findings: Finding[]; audit: AuditEvent[]; intelligence: IntelligenceStatus | null }) {
  const navigate = useNavigate()
  const recent = drafts.slice(0, 4)
  const recentActivity = audit.slice(0, 5)
  const severityTotal = Object.values(dashboard?.findings_by_severity ?? {}).reduce((sum, value) => sum + value, 0)
  const categoryEntries = Object.entries(dashboard?.findings_by_category ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 5)
  const maxCategory = Math.max(1, ...categoryEntries.map(([, value]) => value))
  const waiting = drafts.filter((draft) => draft.status === 'In review').sort((a, b) => a.updated_at.localeCompare(b.updated_at))
  return <>
    <PageHeader eyebrow="AEGIS / GOVERNANCE INTELLIGENCE" title="Command center" description="A live operating picture of claims, policy alignment and human decisions.">
      <span className="workspace-date">{new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' }).format(new Date())}</span>
      <button className="button button-primary" onClick={() => navigate('/submissions/new')}><Plus size={16} /> Submit content</button>
    </PageHeader>
    <section className="command-hero">
      <div className="command-hero-main"><div className="command-kicker"><span className="signal-mark" /> OPERATIONS / LIVE SNAPSHOT</div><h2>Integrity is a<br /><em>connected chain.</em></h2><p>Move from flagged language to its governing policy, available evidence and the human decision that closes the loop.</p><Link to="/intelligence" className="hero-link">Explore intelligence graph <ArrowRight size={15} /></Link></div>
      <div className="command-telemetry"><div className="telemetry-top"><span>WORKSPACE SIGNAL</span><span className="live-indicator"><i /> LIVE RECORDS</span></div><div className="telemetry-count">{(dashboard?.in_review ?? 0).toString().padStart(2, '0')}<small> / {dashboard?.total_submissions ?? 0}</small></div><div className="telemetry-caption">submissions awaiting a human decision</div><div className="telemetry-track"><span style={{ width: `${dashboard?.total_submissions ? Math.min((dashboard.in_review / dashboard.total_submissions) * 100, 100) : 0}%` }} /></div><div className="telemetry-foot"><span>{dashboard?.potential_issues ?? 0} potential signals</span><span>{dashboard?.unresolved_evidence_requirements ?? 0} evidence gaps</span></div><div className="telemetry-mode"><span className={`analysis-mode-dot ${intelligence?.live_ai_claim ? 'mode-ai' : ''}`} />{intelligence?.live_ai_claim ? `AI assisted · ${intelligence.model}` : intelligence?.configured ? 'AI configured · no live claim yet' : 'Rules-only · no model invoked'}</div></div>
      <div className="hero-index">AV / 01</div>
    </section>
    <div className="command-grid">
      <section className="command-section priority-section"><div className="section-rail"><span>01</span><i /></div><div className="section-body"><div className="section-title-row"><div><p className="eyebrow">HUMAN REVIEW</p><h2>Decision queue</h2></div><Link to="/reviews" className="text-link">Open queue <ArrowRight size={14} /></Link></div>
        {waiting.length ? <div className="priority-list">{waiting.slice(0, 3).map((draft, index) => <Link to={`/drafts/${draft.id}`} className="priority-item" key={draft.id}><span className="priority-number">0{index + 1}</span><span className="priority-copy"><strong>{draft.title}</strong><small>{draft.channel} · {draft.finding_count + (draft.analysis?.report.findings.length ?? 0)} potential signals · updated {dateLabel(draft.updated_at)}</small></span><StatusBadge status={draft.status} /><ChevronRight size={15} /></Link>)}</div> : <div className="intentional-empty"><span className="empty-axis">∅</span><div><strong>No decision is waiting</strong><p>New submissions analyzed and sent to review will surface here.</p></div><Link to="/submissions/new">Create a draft <ArrowRight size={13} /></Link></div>}
        {findings.length > 0 && <Link to="/findings" className="attention-strip"><AlertTriangle size={15} /><span><strong>{findings.length} unresolved potential findings</strong><small>Signals for human review — not verified false claims</small></span><ArrowRight size={14} /></Link>}
      </div></section>
      <section className="command-section profile-section"><div className="section-rail"><span>02</span><i /></div><div className="section-body"><div className="section-title-row"><div><p className="eyebrow">SIGNAL DISTRIBUTION</p><h2>Finding profile</h2></div><span className="source-note">PERSISTED / {findings.length}</span></div>
        {severityTotal ? <><div className="severity-stack" aria-label="Finding severity distribution">{['high', 'medium', 'low'].map((level) => <span key={level} className={`severity-segment ${level}`} style={{ width: `${((dashboard?.findings_by_severity?.[level] ?? 0) / severityTotal) * 100}%` }} title={`${level}: ${dashboard?.findings_by_severity?.[level] ?? 0}`} />)}</div><div className="severity-legend">{['high', 'medium', 'low'].map((level) => <Link key={level} to={`/findings?severity=${level}`}><i className={level} /><span>{level}</span><strong>{dashboard?.findings_by_severity?.[level] ?? 0}</strong></Link>)}</div></> : <div className="chart-empty">No analyzed signals yet.<br /><span>Category and severity distribution appears after analysis.</span></div>}
        <div className="category-bars">{categoryEntries.map(([category, value]) => <Link to={`/findings?category=${encodeURIComponent(category)}`} className="category-row" key={category}><span>{category.replaceAll('_', ' ')}</span><i><b style={{ width: `${(value / maxCategory) * 100}%` }} /></i><strong>{value}</strong></Link>)}</div>
      </div></section>
      <section className="command-section recent-section"><div className="section-rail"><span>03</span><i /></div><div className="section-body"><div className="section-title-row"><div><p className="eyebrow">DOCUMENT FLOW</p><h2>Recently touched</h2></div><Link to="/submissions" className="text-link">All drafts <ArrowRight size={14} /></Link></div>
        {recent.length ? <div className="recent-documents">{recent.map((draft) => <Link to={`/drafts/${draft.id}`} className="recent-document" key={draft.id}><span className="doc-glyph"><FileText size={17} /></span><span><strong>{draft.title}</strong><small>{draft.channel} · v{draft.versions.at(-1)?.version ?? 1} · {draft.analysis?.mode === 'ai_assisted' ? 'AI assisted' : draft.analysis ? 'Rules-only' : 'Not analyzed'}</small></span><StatusBadge status={draft.status} /><time>{dateLabel(draft.updated_at)}</time></Link>)}</div> : <div className="intentional-empty"><span className="empty-axis">01</span><div><strong>Start with a real document</strong><p>Submit copy to create the first connected claim and policy review.</p></div><Link to="/submissions/new">Submit content <ArrowRight size={13} /></Link></div>}
      </div></section>
      <section className="command-section activity-section"><div className="section-rail"><span>04</span><i /></div><div className="section-body"><div className="section-title-row"><div><p className="eyebrow">AUDIT TRAIL</p><h2>Recent activity</h2></div><Link to="/audit" className="text-link">Decision ledger <ArrowRight size={14} /></Link></div>
        {recentActivity.length ? <div className="activity-timeline">{recentActivity.slice(0, 4).map((event) => <Link to={event.target_type === 'brand_rule' ? `/rules#policy-${event.target_id}` : event.target_type === 'draft' ? `/drafts/${event.target_id}` : '/audit'} className="activity-event" key={event.id}><span className="timeline-pin" /><span><strong>{event.action}</strong><small>{event.target_title} · {event.actor}</small></span><time>{timeLabel(event.created_at)}</time></Link>)}</div> : <div className="chart-empty">No saved activity yet. Analysis, policy changes and decisions appear here.</div>}
        <div className="operating-facts"><span><b>{dashboard?.enabled_rules ?? 0}</b> active policies</span><span><b>{dashboard?.review_decisions?.approve ?? 0}</b> approvals recorded</span><span><b>{dashboard?.review_decisions?.request_changes ?? 0}</b> revisions requested</span></div>
      </div></section>
    </div>
    <div className="trust-note"><CircleHelp size={15} /><span>Signals indicate potential policy or evidence issues only. Missing evidence is not proof of a false claim; all decisions remain human.</span></div>
  </>
}

function IntelligenceGraph({ drafts, rules, audit }: { drafts: Draft[]; rules: Rule[]; audit: AuditEvent[] }) {
  const [selected, setSelected] = useState<{ title: string; kind: string; detail: string; draftId: number; policyId?: number; evidenceId?: number } | null>(null)
  const chains = drafts.flatMap((draft) => {
    const analysisFindings = draft.analysis?.report.findings.map((finding, index) => ({
      key: `analysis-${draft.analysis?.id}-${index}`,
      quote: finding.exact_quote,
      category: finding.category,
      severity: finding.severity,
      explanation: finding.explanation,
      policyId: finding.policy_id ? Number(finding.policy_id) : undefined,
      evidenceIds: finding.evidence_ids,
      evidenceStatus: finding.evidence_status,
      source: 'Structured analysis record',
      current: draft.analysis?.is_current ?? false,
    })) ?? []
    const deterministic = draft.findings.map((finding) => ({
      key: `finding-${finding.id}`,
      quote: finding.matched_text ?? finding.title,
      category: finding.category,
      severity: finding.severity,
      explanation: finding.description,
      policyId: finding.policy_id ? Number(finding.policy_id) : undefined,
      evidenceIds: [] as number[],
      evidenceStatus: 'not_checked',
      source: `Persisted finding #${finding.id}`,
      current: true,
    }))
    return [...analysisFindings, ...deterministic].map((finding) => ({ draft, finding }))
  })
  return <section className="graph-page">
    <PageHeader eyebrow="RELATIONSHIP EXPLORER" title="Evidence intelligence graph" description="Follow stored claim, policy, evidence and decision relationships. Unlinked and missing relationships are shown explicitly." />
    <div className="graph-legend" aria-label="Graph legend"><span><i className="node-claim" /> Claim signal</span><span><i className="node-policy" /> Policy record</span><span><i className="node-evidence" /> Evidence record</span><span><i className="node-missing" /> Missing relationship</span><span><i className="node-decision" /> Decision event</span></div>
    <div className="graph-workspace">
      <div className="graph-lanes">
        {!chains.length && !drafts.length && <div className="graph-empty"><Network size={25} /><strong>The graph begins with a real record</strong><span>Submit and analyze content to create claim, policy and evidence relationships.</span><Link to="/submissions/new" className="button button-primary">Submit content <ArrowRight size={14} /></Link></div>}
        {!chains.length && drafts.length > 0 && <div className="graph-empty"><FileText size={24} /><strong>Submissions are saved; analysis is not</strong><span>Open a draft and run analysis to reveal stored relationships. No nodes are inferred from unanalysed text.</span><Link to={`/drafts/${drafts[0].id}`} className="text-link">Open {drafts[0].title} <ArrowRight size={14} /></Link></div>}
        {chains.map(({ draft, finding }) => {
          const linkedEvidence = draft.evidence.filter((item) => finding.evidenceIds.includes(item.id))
          const policy = rules.find((item) => item.id === finding.policyId)
          const missingEvidence = finding.evidenceStatus === 'evidence_missing' || finding.evidenceStatus === 'insufficient_evidence'
          return <article className="graph-lane" key={finding.key}>
            <div className="graph-lane-head"><Link to={`/drafts/${draft.id}`}><FileText size={14} />{draft.title}</Link><span>v{draft.analysis?.content_version ?? draft.versions.at(-1)?.version ?? 1}</span>{!finding.current && <span className="stale-label">STALE SNAPSHOT</span>}</div>
            <div className="graph-chain">
              <button className="graph-node claim-node" onClick={() => setSelected({ title: 'Claim signal', kind: finding.category.replaceAll('_', ' '), detail: `“${finding.quote}” — ${finding.explanation} · ${finding.source}${!finding.current ? ' · This analysis is stale.' : ''}`, draftId: draft.id })}><span>CLAIM</span><strong>{finding.quote}</strong><small>{finding.severity} · {finding.category.replaceAll('_', ' ')}</small></button>
              <span className="graph-edge" aria-label="claim links to policy"><i /></span>
              {policy ? <button className="graph-node policy-node" onClick={() => setSelected({ title: policy.name, kind: `Policy #${policy.id}`, detail: `${policy.description}${policy.term ? ` · Term: “${policy.term}”` : ''} · ${policy.enabled ? 'Active' : 'Disabled'}`, draftId: draft.id, policyId: policy.id })}><span>POLICY #{policy.id}</span><strong>{policy.name}</strong><small>{policy.enabled ? 'Active rule' : 'Disabled rule'}</small></button> : <button className="graph-node missing-node" onClick={() => setSelected({ title: 'No linked policy', kind: 'Missing relationship', detail: 'The saved finding has no policy ID. No governing policy relationship can be confirmed.', draftId: draft.id })}><span>POLICY LINK</span><strong>Not linked</strong><small>Relationship absent in record</small></button>}
              <span className="graph-edge"><i /></span>
              {linkedEvidence.length ? linkedEvidence.map((item) => <button key={item.id} className="graph-node evidence-node" onClick={() => setSelected({ title: item.label, kind: `Evidence #${item.id}`, detail: `${item.evidence_status.replaceAll('_', ' ')} · supplied by ${item.actor}${item.excerpt ? ` · Excerpt: ${item.excerpt}` : ''}${item.source_url ? ` · URL: ${item.source_url}` : ''}`, draftId: draft.id, evidenceId: item.id })}><span>EVIDENCE #{item.id}</span><strong>{item.label}</strong><small>Supplied · unverified</small></button>) : <button className={`graph-node ${missingEvidence ? 'missing-node' : 'evidence-node'}`} onClick={() => setSelected({ title: missingEvidence ? 'Evidence relationship missing' : 'No evidence linked to this finding', kind: missingEvidence ? 'Recorded evidence gap' : 'No linked source', detail: missingEvidence ? `Analysis recorded “${finding.evidenceStatus.replaceAll('_', ' ')}”. This is a source gap, not proof the claim is false.` : 'No evidence ID is linked to this claim in the saved analysis. Other draft-level evidence is not assumed to support it.', draftId: draft.id })}><span>{missingEvidence ? 'MISSING EVIDENCE' : 'EVIDENCE LINK'}</span><strong>{missingEvidence ? 'Source required' : 'No link recorded'}</strong><small>{finding.evidenceStatus.replaceAll('_', ' ')}</small></button>}
              <span className="graph-edge"><i /></span>
              <button className="graph-node finding-node" onClick={() => setSelected({ title: 'Persisted analysis finding', kind: finding.source, detail: `${finding.severity} severity · ${finding.category.replaceAll('_', ' ')} · ${finding.explanation}${draft.analysis ? ` · ${draft.analysis.mode.replaceAll('_', ' ')} · ${draft.analysis.provider}/${draft.analysis.model}` : ''}`, draftId: draft.id })}><span>FINDING</span><strong>{finding.category.replaceAll('_', ' ')}</strong><small>{finding.current ? 'Current snapshot' : 'Historical snapshot'}</small></button>
            </div>
            <div className="draft-decision-row"><span className="draft-anchor">Draft-level record</span><i /><span className="decision-records">{audit.filter((event) => event.target_type === 'draft' && event.target_id === draft.id && /approved|rejected|changes requested/i.test(event.action)).length ? audit.filter((event) => event.target_type === 'draft' && event.target_id === draft.id && /approved|rejected|changes requested/i.test(event.action)).map((event) => <button key={event.id} onClick={() => setSelected({ title: event.action, kind: 'Draft-level decision event', detail: `${event.actor} · ${timeLabel(event.created_at)}${event.details ? ` · ${event.details}` : ''}`, draftId: draft.id })}>{event.action} · {timeLabel(event.created_at)}</button>) : <span>No review decision recorded</span>}</span></div>
          </article>
        })}
      </div>
      <aside className="graph-inspector"><p className="eyebrow">NODE INSPECTOR</p>{selected ? <><span className="inspector-kind">{selected.kind}</span><h2>{selected.title}</h2><p>{selected.detail}</p><div className="inspector-actions"><Link to={`/drafts/${selected.draftId}`} className="button button-primary">Open submission <ArrowRight size={14} /></Link>{selected.policyId && <Link to={`/rules#policy-${selected.policyId}`} className="text-link">Open policy lab</Link>}{selected.evidenceId && <Link to={`/drafts/${selected.draftId}`} className="text-link">Inspect evidence record</Link>}</div></> : <div className="inspector-placeholder"><Network size={20} /><strong>Select a node</strong><span>Inspect provenance, missing relationships and the related persisted record.</span></div>}<div className="graph-boundary"><strong>Relationship boundary</strong><span>Draft-level decisions are not attributed to individual claims. Evidence is linked only when the saved analysis names its evidence ID.</span></div></aside>
    </div>
    <div className="graph-accessible"><strong>Text navigation</strong>{drafts.length ? drafts.map((draft) => <Link key={draft.id} to={`/drafts/${draft.id}`}>{draft.title} · {draft.analysis?.report.findings.length ?? draft.findings.length} stored finding records</Link>) : <span>No stored submissions.</span>}</div>
  </section>
}

function StatusBadge({ status }: { status: string }) {
  const icon = status === 'Approved' ? <Check size={12} /> : status === 'In review' ? <Clock3 size={12} /> : status === 'Rejected' ? <X size={12} /> : status === 'Changes requested' ? <AlertCircle size={12} /> : <FileText size={12} />
  return <span className={`status-badge ${statusClass(status)}`}>{icon}{status}</span>
}

function Submissions({ drafts }: { drafts: Draft[] }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All statuses')
  const filtered = drafts.filter((draft) => `${draft.title} ${draft.author} ${draft.channel}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'All statuses' || draft.status === filter))
  return <>
    <PageHeader title="Submissions" description="Track every piece of content moving through governance."><Link className="button button-primary" to="/submissions/new"><Plus size={16} /> New submission</Link></PageHeader>
    <section className="panel full-panel">
      <div className="list-toolbar"><div className="search-box"><Search size={16} /><input aria-label="Search submissions" placeholder="Search submissions…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><label className="select-filter"><Filter size={15} /><select aria-label="Filter submissions by status" value={filter} onChange={(event) => setFilter(event.target.value)}>{['All statuses', 'Draft', 'In review', 'Approved', 'Changes requested', 'Rejected'].map((status) => <option key={status}>{status}</option>)}</select><ChevronDown size={14} /></label><span className="result-count">{filtered.length} submissions</span></div>
      <div className="table-wrap"><table><thead><tr><th>SUBMISSION</th><th>CHANNEL</th><th>STATUS</th><th>FINDINGS</th><th>LAST UPDATED</th><th /></tr></thead><tbody>
        {filtered.map((draft) => <tr key={draft.id} className="clickable-row" onClick={() => navigate(`/drafts/${draft.id}`)}><td><div className="submission-cell"><span className="file-icon"><FileText size={15} /></span><span><strong>{draft.title}</strong><small>by {draft.author}</small></span></div></td><td><span className="channel-tag">{draft.channel}</span></td><td><StatusBadge status={draft.status} /></td><td><span className={draft.finding_count ? 'finding-count' : 'muted-cell'}>{draft.finding_count ? `${draft.finding_count} potential issue${draft.finding_count === 1 ? '' : 's'}` : '—'}</span></td><td className="muted-cell">{dateLabel(draft.updated_at)}</td><td><ChevronRight size={15} className="row-chevron" /></td></tr>)}
        {!filtered.length && <tr><td colSpan={6}><EmptyState icon={Search} title={drafts.length ? 'No matching submissions' : 'Your submissions start here'} description={drafts.length ? 'Try another search or status filter.' : 'Create a draft and send it through the governance workflow.'} action={!drafts.length ? <Link className="subtle-link" to="/submissions/new">Create submission <ArrowRight size={14} /></Link> : undefined} /></td></tr>}
      </tbody></table></div>
    </section>
  </>
}

function NewSubmission({ onCreate }: { onCreate: (input: { title: string; author: string; channel: string; content: string; evidence_reference: string }) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('Local reviewer')
  const [channel, setChannel] = useState('Website')
  const [content, setContent] = useState('')
  const [evidence, setEvidence] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try { await onCreate({ title, author, channel, content, evidence_reference: evidence }) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save your draft.') }
    finally { setSubmitting(false) }
  }
  return <>
    <PageHeader eyebrow="CONTENT GOVERNANCE" title="New submission" description="Submit a draft for deterministic brand checks and human review." />
    <form className="panel form-panel" onSubmit={submit}>
      <div className="form-section-heading"><span className="section-number">01</span><div><h2>Submission details</h2><p>Tell us where this content will appear.</p></div></div>
      <div className="form-grid"><label className="field-label field-wide">Content title<input required maxLength={160} placeholder="e.g. Spring product launch announcement" value={title} onChange={(event) => setTitle(event.target.value)} /></label><label className="field-label">Submitted by<input required maxLength={100} value={author} onChange={(event) => setAuthor(event.target.value)} /></label><label className="field-label">Publishing channel<select value={channel} onChange={(event) => setChannel(event.target.value)}>{['Website', 'Social media', 'Email', 'Paid advertising', 'Press release', 'Internal', 'Other'].map((option) => <option key={option}>{option}</option>)}</select></label></div>
      <div className="form-section-heading form-section-spaced"><span className="section-number">02</span><div><h2>Draft content</h2><p>Paste the content you’d like to review. Checks are transparent and rule-based.</p></div></div>
      <label className="field-label">Content<textarea required minLength={5} maxLength={12000} rows={8} placeholder="Paste your content here…" value={content} onChange={(event) => setContent(event.target.value)} /><span className="field-helper">{content.length.toLocaleString()} / 12,000 characters</span></label>
      <label className="field-label evidence-field">Evidence reference <span className="optional-label">OPTIONAL</span><input maxLength={500} placeholder="e.g. Report Q2-2026, page 8 (reference only; not verified)" value={evidence} onChange={(event) => setEvidence(event.target.value)} /><span className="field-helper">Provide an existing source reference for numerical claims. We never create or verify citations.</span></label>
      {error && <div className="form-error"><AlertCircle size={15} />{error}</div>}
      <div className="form-footer"><Link className="button button-quiet" to="/submissions">Cancel</Link><button className="button button-primary" type="submit" disabled={submitting}>{submitting ? <LoaderCircle size={16} className="spin" /> : <FilePlus2 size={16} />}{submitting ? 'Saving draft…' : 'Save draft'}</button></div>
    </form>
  </>
}

function DraftDetail({ onMutation, intelligence }: { onMutation: () => Promise<void>; intelligence: IntelligenceStatus | null }) {
  const { draftId = '' } = useParams()
  return <DraftDetailContent key={draftId} draftId={draftId} onMutation={onMutation} intelligence={intelligence} />
}

function DraftDetailContent({ draftId, onMutation, intelligence }: { draftId: string; onMutation: () => Promise<void>; intelligence: IntelligenceStatus | null }) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [evidenceLabel, setEvidenceLabel] = useState('')
  const [evidenceUrl, setEvidenceUrl] = useState('')
  const [evidenceExcerpt, setEvidenceExcerpt] = useState('')
  const [savingEvidence, setSavingEvidence] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [answerEvidenceIds, setAnswerEvidenceIds] = useState<number[]>([])
  const [assistantMode, setAssistantMode] = useState<'ai_assisted' | 'rules_only' | null>(null)
  const [asking, setAsking] = useState(false)
  const [revisionText, setRevisionText] = useState('')
  const [revisionNote, setRevisionNote] = useState('')
  const [savingRevision, setSavingRevision] = useState(false)
  const [editBusy, setEditBusy] = useState<number | null>(null)
  useEffect(() => {
    let alive = true
    getDraft(draftId).then((value) => { if (alive) { setDraft(value); setRevisionText(value.content) } }).catch((cause: unknown) => { if (alive) setError(cause instanceof Error ? cause.message : 'Could not load submission.') }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [draftId])
  const reloadDraft = async () => {
    const updated = await getDraft(draftId)
    setDraft(updated)
    setRevisionText(updated.content)
    await onMutation()
  }
  const analyze = async () => {
    setAnalyzing(true)
    setError('')
    try { const result = await analyzeDraft(draftId); setDraft(result); setRevisionText(result.content); await onMutation() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Analysis failed.') }
    finally { setAnalyzing(false) }
  }
  const submitEvidence = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSavingEvidence(true)
    setError('')
    try {
      await addEvidence(draftId, { label: evidenceLabel, source_url: evidenceUrl, excerpt: evidenceExcerpt })
      setEvidenceLabel('')
      setEvidenceUrl('')
      setEvidenceExcerpt('')
      await reloadDraft()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save evidence reference.') }
    finally { setSavingEvidence(false) }
  }
  const ask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAsking(true)
    setAnswer('')
    setAnswerEvidenceIds([])
    setError('')
    try {
      const result = await askAssistant(draftId, question)
      setAnswer(result.answer.answer)
      setAnswerEvidenceIds(result.answer.supporting_evidence_ids)
      setAssistantMode(result.mode)
      await onMutation()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Assistant request failed.') }
    finally { setAsking(false) }
  }
  const decideEdit = async (editId: number, action: 'accept' | 'reject') => {
    setEditBusy(editId)
    setError('')
    try { const updated = await decideProposedEdit(Number(draftId), editId, action); setDraft(updated); setRevisionText(updated.content); await onMutation() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not record this edit decision.') }
    finally { setEditBusy(null) }
  }
  const submitRevision = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSavingRevision(true)
    setError('')
    try {
      const updated = await reviseDraft(Number(draftId), {
        content: revisionText,
        evidence_reference: draft?.evidence_reference ?? '',
        change_note: revisionNote,
      })
      setDraft(updated)
      setRevisionNote('')
      await onMutation()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save the requested changes.') }
    finally { setSavingRevision(false) }
  }
  if (loading) return <LoadingState />
  if (!draft) return <div className="panel empty-page"><EmptyState icon={FileText} title="Submission not found" description={error || 'This draft may have been removed.'} action={<Link className="subtle-link" to="/submissions">Back to submissions</Link>} /></div>
  return <>
    <Link to="/submissions" className="back-link"><ArrowRight size={14} /> All submissions</Link>
    <PageHeader eyebrow={draft.channel.toUpperCase()} title={draft.title} description={`Submitted by ${draft.author} · Updated ${timeLabel(draft.updated_at)}`}>
      <StatusBadge status={draft.status} />
      <button className="button button-primary" onClick={() => void analyze()} disabled={analyzing || ['Approved', 'Rejected'].includes(draft.status)}>{analyzing ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}{analyzing ? 'Analyzing…' : 'Run analysis'}</button>
    </PageHeader>
    {error && <div className="form-error inline-error"><AlertCircle size={15} />{error}</div>}
    {draft.status === 'In review' && draft.analysis && !draft.analysis.is_current && <div className="form-error inline-error"><AlertCircle size={15} />The draft or brand rules changed after this analysis. Re-analyze before a reviewer can record a decision.</div>}
    <div className="analysis-banner">
      <span className={`analysis-mode-dot ${draft.analysis?.mode === 'ai_assisted' ? 'mode-ai' : ''}`} />
      <div><strong>{draft.analysis?.mode === 'ai_assisted' ? 'AI-assisted analysis' : 'Rules-only analysis'}</strong><span>{draft.analysis ? `${draft.analysis.provider} · ${draft.analysis.model} · policy v${draft.analysis.policy_version} · content v${draft.analysis.content_version} · ${timeLabel(draft.analysis.created_at)}${draft.analysis.failure_code ? ` · provider issue: ${draft.analysis.failure_code}` : ''}` : intelligence?.configured ? 'AI provider configured; analysis has not run yet.' : 'Deterministic rules are active. No AI analysis has run.'}</span></div>
      <span className={`mode-label ${draft.analysis?.mode === 'ai_assisted' ? 'mode-label-ai' : ''}`}>{draft.analysis?.mode === 'ai_assisted' ? draft.analysis.is_current ? 'MODEL SUCCEEDED' : 'STALE · RE-ANALYZE' : draft.analysis?.outcome === 'provider_error' ? 'AI FAILED · FALLBACK' : 'NO MODEL CLAIM'}</span>
    </div>
    {draft.analysis && <section className="panel ai-analysis-panel">
      <div className="panel-heading"><div><h2>Claim &amp; policy analysis</h2><p>{draft.analysis.report.summary}</p></div><span className="result-count">{draft.analysis.report.findings.length} structured finding{draft.analysis.report.findings.length === 1 ? '' : 's'}</span></div>
      {draft.analysis.report.findings.length ? <div className="claim-list">{draft.analysis.report.findings.map((finding, index) => <ClaimCard finding={finding} index={index} evidence={draft.evidence} key={`${draft.analysis?.id}-${index}`} />)}</div> : <div className="quiet-state"><CircleHelp size={16} />{draft.analysis.mode === 'ai_assisted' ? 'The model returned no structured findings. Human review is still required.' : 'Rules-only fallback is active. It does not perform interpretive claim analysis.'}</div>}
      {draft.analysis.report.missing_information.length > 0 && <div className="missing-info"><strong>Information to resolve</strong><ul>{draft.analysis.report.missing_information.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      {!!draft.proposed_edits.length && <div className="rewrite-studio"><div className="rewrite-heading"><Sparkles size={16} /><div><strong>Rewrite studio</strong><span>Suggestions are proposals. Accepting one creates a new draft version; nothing is silently changed.</span></div></div>{draft.proposed_edits.map((edit) => { const currentProposal = edit.analysis_run_id === draft.analysis?.id && draft.analysis.is_current; return <article className="proposed-edit" key={edit.id}><div className="edit-diff"><div><small>ORIGINAL</small><p>{edit.original_text}</p></div><ArrowRight size={16} /><div><small>PROPOSED REVISION</small><p>{edit.suggested_text}</p></div></div><p className="edit-rationale">{edit.rationale}</p><div className="edit-actions"><span className={`edit-state ${edit.status}`}>{edit.status !== 'proposed' ? `${edit.status} by ${edit.actor ?? 'reviewer'}` : currentProposal ? 'Awaiting your decision' : 'Stale proposal · re-analyze'}</span>{edit.status === 'proposed' && currentProposal && <span><button className="button button-quiet" disabled={editBusy === edit.id} onClick={() => void decideEdit(edit.id, 'reject')}>Reject suggestion</button><button className="button button-primary" disabled={editBusy === edit.id || ['Approved', 'Rejected'].includes(draft.status)} onClick={() => void decideEdit(edit.id, 'accept')}>{editBusy === edit.id ? 'Saving…' : 'Accept & create version'}</button></span>}</div></article>})}</div>}
    </section>}
    <div className="detail-grid"><section className="panel content-panel"><div className="panel-heading"><div><h2>Draft content</h2><p>Version {draft.versions.at(-1)?.version ?? 1} · {draft.content.length.toLocaleString()} characters</p></div><FileText size={17} className="muted-icon" /></div><div className="draft-copy">{draft.content}</div>{draft.evidence_reference && <div className="evidence-reference"><span className="evidence-ref-icon"><FileCheck2 size={15} /></span><span><strong>Submission evidence reference</strong><small>{draft.evidence_reference} · supplied, not verified</small></span></div>}{draft.versions.length > 1 && <div className="version-history"><strong>Version history</strong>{draft.versions.slice().reverse().map((version) => <div key={version.id}><span>v{version.version} · {version.change_note}</span><small>{version.actor} · {timeLabel(version.created_at)}</small></div>)}</div>}</section><section className="panel finding-panel"><div className="panel-heading"><div><h2>Deterministic policy checks</h2><p>{draft.findings.length ? `${draft.findings.length} configured rule signal${draft.findings.length === 1 ? '' : 's'}` : draft.analyzed_at ? 'No configured rule signals' : 'Run analysis to check this draft'}</p></div><ShieldCheck size={18} className="muted-icon" /></div>{draft.findings.length ? <div className="finding-list">{draft.findings.map((finding) => <FindingCard finding={finding} key={finding.id} />)}</div> : draft.analyzed_at ? <div className="clean-state"><span><CheckCircle2 size={22} /></span><strong>No configured rules were triggered</strong><small>This is not a factual verification or guarantee of compliance.</small></div> : <div className="not-analyzed"><Sparkles size={19} /><strong>Ready for analysis</strong><span>Rules are deterministic. AI is used only when configured.</span></div>}</section></div>
    {draft.status === 'Changes requested' && <section className="panel revision-panel"><div className="panel-heading"><div><h2>Revise requested changes</h2><p>Saving creates a new version; the original remains in version history.</p></div></div><form className="revision-form" onSubmit={(event) => void submitRevision(event)}><label className="field-label">Updated draft<textarea required minLength={5} maxLength={12000} rows={7} value={revisionText} onChange={(event) => setRevisionText(event.target.value)} /></label><label className="field-label">Revision note<input required minLength={2} maxLength={500} value={revisionNote} onChange={(event) => setRevisionNote(event.target.value)} placeholder="Describe the changes made" /></label><button className="button button-primary" disabled={savingRevision}>{savingRevision ? 'Saving…' : 'Save revision'}</button></form></section>}
    <section className="panel evidence-workspace"><div className="panel-heading"><div><h2>Evidence workspace</h2><p>Associate source URLs or excerpts with this draft. References are never fetched or verified by this MVP.</p></div><FileCheck2 size={17} className="muted-icon" /></div>{draft.evidence.length > 0 && <div className="evidence-list">{draft.evidence.map((item) => <article className="evidence-item" key={item.id}><span className="evidence-ref-icon"><FileCheck2 size={15} /></span><span><strong>{item.label}</strong>{item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_url}</a>}{item.excerpt && <small>“{item.excerpt}”</small>}<em>User-supplied · unverified</em></span></article>)}</div>}<form className="evidence-form" onSubmit={(event) => void submitEvidence(event)}><label className="field-label">Reference label<input required maxLength={160} value={evidenceLabel} onChange={(event) => setEvidenceLabel(event.target.value)} placeholder="Report Q2, page 8" /></label><label className="field-label">Source URL<input type="url" maxLength={2000} value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} placeholder="https://…" /></label><label className="field-label field-wide">Source excerpt<textarea maxLength={5000} rows={3} value={evidenceExcerpt} onChange={(event) => setEvidenceExcerpt(event.target.value)} placeholder="Paste a short passage from the source (optional)" /></label><button className="button button-outline" disabled={savingEvidence}>{savingEvidence ? 'Saving…' : 'Add evidence reference'}</button></form></section>
    <section className="panel assistant-panel"><div className="panel-heading"><div><h2>AEGIS contextual assistant</h2><p>Ask about this draft, active policies, findings and supplied evidence. It cannot change or approve content.</p></div><CircleHelp size={17} className="muted-icon" /></div><form className="assistant-form" onSubmit={(event) => void ask(event)}><label className="field-label">Question<input required minLength={3} maxLength={500} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What evidence is missing for this claim?" /></label><button className="button button-primary" disabled={asking}>{asking ? 'Thinking…' : 'Ask Aegis'}</button></form>{!intelligence?.configured && <p className="assistant-fallback-note">Rules-only mode returns workspace status only; configuring a provider enables contextual answers.</p>}{answer && <div className="assistant-answer"><span className={`mode-label ${assistantMode === 'ai_assisted' ? 'mode-label-ai' : ''}`}>{assistantMode === 'ai_assisted' ? 'AI-ASSISTED' : 'RULES-ONLY'}</span><p>{answer}</p>{answerEvidenceIds.length > 0 && <small>Context cited: {draft.evidence.filter((item) => answerEvidenceIds.includes(item.id)).map((item) => `${item.label} (user-supplied, unverified)`).join(', ')}</small>}<small>Suggestions only · no changes or verification have been performed.</small></div>}</section>
    <div className="trust-note"><CircleHelp size={15} /><span>Model output is untrusted and schema-validated; exact quotes, policy IDs and evidence IDs are checked against supplied records. Human review remains required.</span></div>
  </>
}

function ClaimCard({ finding, index, evidence }: { finding: import('./types').ClaimFinding; index: number; evidence: Draft['evidence'] }) {
  const linkedEvidence = evidence.filter((item) => finding.evidence_ids.includes(item.id))
  return <article className="claim-card"><div className="claim-head"><span className={`finding-type-icon ${finding.severity}`}><AlertTriangle size={15} /></span><span className="finding-heading"><strong>Claim {index + 1} · {finding.category.replaceAll('_', ' ')}</strong><small>{finding.severity} severity · {finding.evidence_status.replaceAll('_', ' ')}</small></span><span className="human-review-tag">HUMAN REVIEW</span></div><blockquote>“{finding.exact_quote}”</blockquote><p>{finding.explanation}</p><p className="claim-rationale">{finding.rationale}</p><div className="claim-meta"><span>Policy: {finding.policy_id ? `#${finding.policy_id}` : 'No specific rule linked'}</span><span>Evidence: {linkedEvidence.length ? linkedEvidence.map((item) => item.label).join(', ') : 'No source independently verified'}</span></div><div className="claim-action"><strong>Recommended action</strong><span>{finding.recommended_action}</span></div>{finding.suggested_rewrite && <div className="claim-rewrite"><strong>Suggested wording · not applied</strong><span>{finding.suggested_rewrite}</span></div>}</article>
}

function FindingCard({ finding }: { finding: Finding }) {
  return <article className="finding-card"><div className="finding-title-row"><span className={`finding-type-icon ${finding.severity}`}><AlertTriangle size={15} /></span><span className="finding-heading"><strong>{finding.title}</strong><small>{finding.category.replaceAll('_', ' ')}{finding.policy_id !== null ? ` · policy #${finding.policy_id}` : ''}</small></span><span className={`severity-pill ${finding.severity}`}>{finding.severity}</span></div><p>{finding.description}</p>{finding.matched_text && <blockquote>“{finding.matched_text}”</blockquote>}<span className="potential-label">Potential issue · not a verified false claim</span></article>
}

function ReviewQueue({ drafts, onReview }: { drafts: Draft[]; onReview: (id: number, action: 'approve' | 'reject' | 'request_changes', comment: string) => Promise<void> }) {
  const [processing, setProcessing] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [comments, setComments] = useState<Record<number, string>>({})
  const [query, setQuery] = useState('')
  const [severity, setSeverity] = useState('all')
  const [category, setCategory] = useState('all')
  const queued = drafts.filter((draft) => draft.status === 'In review')
  const visibleQueue = queued.filter((draft) => {
    const textMatches = `${draft.title} ${draft.author} ${draft.channel} ${draft.content}`.toLowerCase().includes(query.toLowerCase())
    const allFindings = [
      ...draft.findings.map((finding) => ({ severity: finding.severity, category: finding.category })),
      ...(draft.analysis?.report.findings ?? []).map((finding) => ({ severity: finding.severity, category: finding.category })),
    ]
    return textMatches
      && (severity === 'all' || allFindings.some((finding) => finding.severity === severity))
      && (category === 'all' || allFindings.some((finding) => finding.category === category))
  })
  const queueCategories = [...new Set(queued.flatMap((draft) => [
    ...draft.findings.map((finding) => finding.category),
    ...(draft.analysis?.report.findings ?? []).map((finding) => finding.category),
  ]))]
  const act = async (id: number, action: 'approve' | 'reject' | 'request_changes') => {
    setProcessing(id)
    setError('')
    try {
      await onReview(id, action, (comments[id] ?? '').trim())
      setComments((current) => ({ ...current, [id]: '' }))
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Review action failed.') }
    finally { setProcessing(null) }
  }
  return <>
    <PageHeader title="Review queue" description="Review analyzed content and record a clear governance decision."><span className="queue-count">{queued.length} awaiting review</span></PageHeader>
    {error && <div className="form-error inline-error"><AlertCircle size={15} />{error}</div>}
    {queued.length > 0 && <div className="panel review-filterbar"><div className="search-box"><Search size={15} /><input aria-label="Search review queue" placeholder="Search submissions…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><label className="select-filter"><Filter size={14} /><select aria-label="Filter review queue by severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">All severities</option>{['high', 'medium', 'low'].map((item) => <option key={item} value={item}>{item} severity</option>)}</select><ChevronDown size={14} /></label><label className="select-filter"><select aria-label="Filter review queue by category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">All categories</option>{queueCategories.map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select><ChevronDown size={14} /></label></div>}
    {queued.length ? visibleQueue.length ? <div className="review-list">{visibleQueue.map((draft) => { const findingCount = draft.finding_count + (draft.analysis?.report.findings.length ?? 0); return <article className="panel review-card" key={draft.id}><div className="review-card-top"><div className="submission-cell"><span className="file-icon"><FileText size={15} /></span><span><strong>{draft.title}</strong><small>{draft.channel} · submitted by {draft.author} · {dateLabel(draft.updated_at)}</small></span></div><StatusBadge status={draft.status} /></div>{draft.analysis && !draft.analysis.is_current && <div className="form-error"><AlertCircle size={14} />Draft or policy changed after analysis. Re-analyze before review.</div>}<div className="review-preview">{draft.content}</div><div className="review-meta"><span><ShieldAlert size={14} /> {findingCount} potential finding{findingCount === 1 ? '' : 's'}</span><Link to={`/drafts/${draft.id}`} className="subtle-link">Open full review <ArrowRight size={14} /></Link></div><textarea className="review-comment" rows={2} aria-label={`Review note for ${draft.title}`} placeholder="Optional review note…" value={comments[draft.id] ?? ''} onChange={(event) => setComments((current) => ({ ...current, [draft.id]: event.target.value }))} /><div className="review-actions"><Link className="button button-quiet" to={`/drafts/${draft.id}`}>View findings</Link><div className="review-action-group"><button className="button button-danger-quiet" disabled={processing === draft.id || !draft.analysis?.is_current} onClick={() => void act(draft.id, 'reject')}><X size={15} /> Reject</button><button className="button button-outline" disabled={processing === draft.id || !draft.analysis?.is_current} onClick={() => void act(draft.id, 'request_changes')}><AlertCircle size={15} /> Request changes</button><button className="button button-primary" disabled={processing === draft.id || !draft.analysis?.is_current} onClick={() => void act(draft.id, 'approve')}>{processing === draft.id ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />} Approve</button></div></div></article>})}</div> : <section className="panel"><EmptyState icon={Search} title="No queue items match" description="Change or clear the search and finding filters." /></section> : <section className="panel"><EmptyState icon={CheckCircle2} title="The review queue is clear" description="Analyzed drafts submitted for review will appear here. You can submit a new draft to get started." action={<Link className="button button-primary" to="/submissions/new"><Plus size={15} /> New submission</Link>} /></section>}
  </>
}

function FindingsPage({ findings, drafts }: { findings: Finding[]; drafts: Draft[] }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const severity = searchParams.get('severity') ?? 'all'
  const category = searchParams.get('category') ?? 'all'
  const categories = [...new Set(findings.map((finding) => finding.category))]
  const filtered = findings.filter((finding) =>
    (severity === 'all' || finding.severity.toLowerCase() === severity.toLowerCase())
    && (category === 'all' || finding.category === category),
  )
  return <>
    <PageHeader title="Content findings" description="Rule-based signals that may need human attention. None are factual verdicts." />
    <section className="panel full-panel"><div className="list-toolbar"><label className="select-filter"><Filter size={15} /><select aria-label="Filter findings by severity" value={severity} onChange={(event) => { const next = new URLSearchParams(searchParams); if (event.target.value === 'all') next.delete('severity'); else next.set('severity', event.target.value); setSearchParams(next) }}>{[['all', 'All severities'], ['high', 'High'], ['medium', 'Medium'], ['low', 'Low']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><ChevronDown size={14} /></label><label className="select-filter"><select aria-label="Filter findings by category" value={category} onChange={(event) => { const next = new URLSearchParams(searchParams); if (event.target.value === 'all') next.delete('category'); else next.set('category', event.target.value); setSearchParams(next) }}><option value="all">All categories</option>{categories.map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select><ChevronDown size={14} /></label><span className="result-count">{filtered.length} potential findings</span></div>{filtered.length ? <div className="findings-table-list">{filtered.map((finding) => { const draft = drafts.find((item) => item.id === finding.draft_id); return <Link to={`/drafts/${finding.draft_id}`} className="finding-row" key={finding.id}><span className={`finding-type-icon ${finding.severity}`}><AlertTriangle size={15} /></span><span className="finding-row-copy"><strong>{finding.title}</strong><small>{finding.description}</small></span><span className="finding-draft">{draft?.title ?? 'Submission'}</span><span className={`severity-pill ${finding.severity}`}>{finding.severity}</span><ChevronRight size={15} /></Link>})}</div> : <EmptyState icon={ShieldCheck} title="No findings to show" description={findings.length ? 'No findings match the selected severity and category.' : 'Analyze a submission to see potential issues identified by your brand rules.'} action={!findings.length ? <Link to="/submissions" className="subtle-link">View submissions <ArrowRight size={14} /></Link> : undefined} />}</section>
    <div className="trust-note"><CircleHelp size={15} /><span>Numerical claims are flagged for evidence review only. No statement is labeled false or externally verified.</span></div>
  </>
}

function RulesPage({ rules, onMutation }: { rules: Rule[]; onMutation: () => Promise<void> }) {
  const [editing, setEditing] = useState<Rule | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [category, setCategory] = useState<RuleCategory>('terminology')
  const [term, setTerm] = useState('')
  const [replacement, setReplacement] = useState('')
  const [description, setDescription] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [historyId, setHistoryId] = useState<number | null>(null)
  const [history, setHistory] = useState<RuleRevision[]>([])
  const [historyError, setHistoryError] = useState('')
  const startEdit = (rule: Rule) => {
    setEditing(rule)
    setCreating(false)
    setName(rule.name)
    setCategory(rule.category as RuleCategory)
    setTerm(rule.term ?? '')
    setReplacement(rule.replacement ?? '')
    setDescription(rule.description)
    setEnabled(rule.enabled)
    setError('')
  }
  const startCreate = () => {
    setEditing(null)
    setCreating(true)
    setName('')
    setCategory('terminology')
    setTerm('')
    setReplacement('')
    setDescription('')
    setEnabled(true)
    setError('')
  }
  const submitRule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    const input = { name, category, term, replacement, description, enabled }
    try {
      if (editing) await updateRule(editing.id, input)
      else await createRule(input)
      setEditing(null)
      setCreating(false)
      await onMutation()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save brand rule.') }
    finally { setSaving(false) }
  }
  const showHistory = async (id: number) => {
    setHistoryId(id)
    setHistoryError('')
    try { setHistory(await getRuleRevisions(id)) }
    catch (cause) { setHistoryError(cause instanceof Error ? cause.message : 'Could not load rule versions.') }
  }
  const groups = [
    { title: 'Restricted terminology', description: 'Terms that should be avoided in published brand content.', rules: rules.filter((rule) => rule.category === 'terminology') },
    { title: 'Required language', description: 'Phrases that must appear in applicable content.', rules: rules.filter((rule) => rule.category === 'required_term') },
    { title: 'Evidence checks', description: 'Claims and references that should be reviewed by a human.', rules: rules.filter((rule) => ['numerical_claim', 'evidence_reference'].includes(rule.category)) },
  ]
  return <>
    <PageHeader title="Brand rules" description="Transparent, deterministic checks configured for this local workspace."><span className="enabled-indicator"><span className="live-dot" /> {rules.filter((rule) => rule.enabled).length} active rules</span><button className="button button-primary" onClick={startCreate}><Plus size={15} /> Add rule</button></PageHeader>
    <div className="rules-intro"><span className="rules-intro-icon"><ShieldCheck size={19} /></span><div><strong>Your brand guardrails</strong><p>Rules are stored locally and run without external AI services. Findings are review prompts, not proof of an incorrect claim.</p></div></div>
    {(creating || editing) && <form className="panel rule-editor" onSubmit={(event) => void submitRule(event)}><div className="panel-heading"><div><h2>{editing ? `Edit rule · ${editing.name}` : 'Create brand rule'}</h2><p>Saving creates a new immutable policy version. Existing analyses keep their original policy version.</p></div><button className="button button-quiet" type="button" onClick={() => { setEditing(null); setCreating(false) }}>Cancel</button></div><div className="rule-form-grid"><label className="field-label">Rule name<input required minLength={2} maxLength={140} value={name} onChange={(event) => setName(event.target.value)} /></label><label className="field-label">Rule type<select value={category} onChange={(event) => setCategory(event.target.value as RuleCategory)}>{[['terminology', 'Restricted terminology'], ['required_term', 'Required language'], ['numerical_claim', 'Numerical claim review'], ['evidence_reference', 'Evidence reference']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>{['terminology', 'required_term'].includes(category) && <label className="field-label">Term<input required maxLength={200} value={term} onChange={(event) => setTerm(event.target.value)} /></label>}{category === 'terminology' && <label className="field-label">Suggested alternative<input maxLength={200} value={replacement} onChange={(event) => setReplacement(event.target.value)} /></label>}<label className="field-label field-wide">Description<textarea required minLength={3} maxLength={1000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label><label className="rule-enabled-toggle"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Active rule</label><button className="button button-primary" disabled={saving}>{saving ? 'Saving…' : editing ? 'Save new version' : 'Create rule'}</button></div>{error && <div className="form-error"><AlertCircle size={14} />{error}</div>}</form>}
    {historyId !== null && <section className="panel rule-history"><div className="panel-heading"><div><h2>Rule version history</h2><p>Rule #{historyId} · snapshots used by prior analyses are preserved.</p></div><button className="button button-quiet" onClick={() => setHistoryId(null)}>Close</button></div>{historyError ? <div className="form-error">{historyError}</div> : history.map((item) => <article className="rule-version" key={item.version}><strong>Version {item.version} · {item.rule.name}</strong><span>{item.rule.description}</span><small>{item.actor} · {timeLabel(item.created_at)}</small></article>)}</section>}
    <div className="rule-groups">{groups.map((group) => <section className="panel rule-group" key={group.title}><div className="panel-heading"><div><h2>{group.title}</h2><p>{group.description}</p></div><span className="rule-count">{group.rules.length}</span></div>{group.rules.length ? group.rules.map((rule) => <article className="rule-item" key={rule.id}><span className={`rule-symbol ${rule.enabled ? '' : 'rule-disabled'}`}>{rule.category === 'terminology' ? <AlertTriangle size={15} /> : rule.category === 'required_term' ? <CheckCircle2 size={15} /> : <FileCheck2 size={15} />}</span><span className="rule-copy"><strong>Policy #{rule.id} · {rule.name}</strong><small>{rule.description}</small>{rule.term && <span className="rule-term">{rule.category === 'terminology' ? `Flag: “${rule.term}”` : `Check: “${rule.term}”`}{rule.replacement ? `  ·  Suggested alternative: “${rule.replacement}”` : ''}</span>}<span className="rule-actions"><button className="text-action" onClick={() => startEdit(rule)}>Edit</button><button className="text-action" onClick={() => void showHistory(rule.id)}>Versions</button></span></span><span className={`rule-state ${rule.enabled ? 'rule-on' : ''}`}>{rule.enabled ? 'Active' : 'Off'}</span></article>) : <div className="rule-empty">No rules configured in this category.</div>}</section>)}</div>
  </>
}

function AuditPage({ events }: { events: AuditEvent[] }) {
  const [query, setQuery] = useState('')
  const filtered = events.filter((event) => `${event.action} ${event.actor} ${event.target_title} ${event.details}`.toLowerCase().includes(query.toLowerCase()))
  const auditIcon = (action: string) => action.includes('approved') ? <Check size={15} /> : action.includes('rejected') ? <X size={15} /> : action.includes('change') ? <AlertCircle size={15} /> : action.includes('analyzed') ? <Sparkles size={15} /> : <FileText size={15} />
  return <>
    <PageHeader title="Audit history" description="A durable, chronological record of governance activity." />
    <section className="panel full-panel"><div className="list-toolbar"><div className="search-box"><Search size={16} /><input aria-label="Search audit history" placeholder="Search activity…" value={query} onChange={(event) => setQuery(event.target.value)} /></div><span className="result-count">{filtered.length} events</span></div>{filtered.length ? <div className="audit-list">{filtered.map((event) => <article className="audit-event" key={event.id}><span className={`audit-event-icon ${event.action.includes('approved') ? 'audit-green' : event.action.includes('rejected') ? 'audit-red' : ''}`}>{auditIcon(event.action)}</span><div className="audit-copy"><strong>{event.action}</strong><span>{event.target_title}{event.details ? ` · ${event.details}` : ''}</span><small>{event.actor}</small></div><time>{timeLabel(event.created_at)}</time></article>)}</div> : <EmptyState icon={Activity} title="No audit events found" description={events.length ? 'Try adjusting your search.' : 'Draft submissions, analyses and review decisions will be recorded here.'} />}</section>
  </>
}

function EmptyState({ icon: Icon, title, description, action }: { icon: typeof FileText; title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-icon"><Icon size={20} /></span><strong>{title}</strong><p>{description}</p>{action && <div className="empty-action">{action}</div>}</div>
}

function NotFound() {
  return <section className="panel"><EmptyState icon={PanelLeftClose} title="Page not found" description="The page you’re looking for doesn’t exist." action={<Link className="subtle-link" to="/">Return to overview <ArrowRight size={14} /></Link>} /></section>
}

export default App
