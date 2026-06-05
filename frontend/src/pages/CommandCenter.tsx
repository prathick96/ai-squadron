/**
 * CommandCenter.tsx — AI Squadron operations hub
 *
 * Layout:
 *   TopBar   → key metrics + Launch button
 *   Hero     → active pipeline with stage tracker + decision card when paused
 *   History  → recent runs (compact)
 *   Bottom   → Portfolio (left)  +  Agent health (right)
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  type AgentRow,
  type ConfidenceReport,
  type PipelineRun,
  type PortfolioSlot,
  type RevenueSummary,
  type Venture,
} from '../api'

// ─── Colour tokens ────────────────────────────────────────────────────────────
const C = {
  bg:         '#080810',
  panel:      '#0d0d1a',
  panelAlt:   '#111128',
  border:     '#1e1e3a',
  borderHover:'#2e2e5a',
  accent:     '#3ecf8e',
  purple:     '#7c3aed',
  purpleGlow: 'rgba(124,58,237,0.25)',
  red:        '#ef4444',
  orange:     '#f59e0b',
  blue:       '#3b82f6',
  fg:         '#e2e8f0',
  fgMuted:    '#64748b',
  fgDim:      '#334155',
}

// ─── Pipeline stages (correct order after RCA fix) ────────────────────────────
const STAGES = [
  { id: 'RESEARCH_NODE',          label: 'Research',    icon: '🔍' },
  { id: 'CEO_NODE',               label: 'CEO',         icon: '👔' },
  { id: 'PRODUCT_VP_NODE',        label: 'Product VP',  icon: '📋' },
  { id: 'PRODUCT_MANAGER_NODE',   label: 'PM',          icon: '📝' },
  { id: 'ENGINEERING_NODE',       label: 'Engineering', icon: '⚙️' },
  { id: 'QA_TECHNICAL_NODE',      label: 'QA',          icon: '🧪' },
  { id: 'SECURITY_NODE',          label: 'Security',    icon: '🛡️' },
  { id: 'LEGAL_NODE',             label: 'Legal',       icon: '⚖️' },
  { id: 'DEPLOYMENT_NODE',        label: 'Deploy',      icon: '🚀' },
  { id: 'MARKETING_SEO_NODE',     label: 'Marketing',   icon: '📢' },
  { id: 'PRODUCT_GROWTH_NODE',    label: 'Growth',      icon: '📈' },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────
function usd(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

function elapsed(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

function stageIdx(current: string): number {
  return Math.max(0, STAGES.findIndex(s => s.id === current))
}

// ─── Stage tracker component ──────────────────────────────────────────────────
function PipelineStageTracker({ run }: { run: PipelineRun }) {
  const idx = stageIdx(run.current_stage)
  const done = run.status === 'COMPLETED'
  const failed = run.status === 'FAILED'
  const paused = run.status === 'MANUAL_REVIEW'

  return (
    <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, minWidth: 720 }}>
        {STAGES.map((stage, i) => {
          const isActive  = i === idx && !done && !failed
          const isRunning = isActive && (run.status === 'RUNNING' || run.status === 'STARTED')
          const isPaused  = isActive && paused
          const isDone    = done || i < idx
          const isFailed  = failed && i === idx

          let bg    = C.panelAlt
          let color = C.fgDim
          let border = C.border

          if (isDone)    { bg = 'rgba(62,207,142,0.12)';  color = C.accent;  border = 'rgba(62,207,142,0.4)' }
          if (isRunning) { bg = 'rgba(59,130,246,0.12)';  color = C.blue;    border = 'rgba(59,130,246,0.5)' }
          if (isPaused)  { bg = 'rgba(245,158,11,0.12)';  color = C.orange;  border = 'rgba(245,158,11,0.5)' }
          if (isFailed)  { bg = 'rgba(239,68,68,0.12)';   color = C.red;     border = 'rgba(239,68,68,0.5)'  }

          return (
            <div key={stage.id} style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
              <div style={{
                flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
                padding: '8px 4px',
                background: bg, border: `1px solid ${border}`, borderRadius: 8,
                position: 'relative', transition: 'all 0.3s',
                boxShadow: isRunning ? `0 0 12px rgba(59,130,246,0.3)` : isPaused ? `0 0 12px rgba(245,158,11,0.3)` : 'none',
              }}>
                <span style={{ fontSize: 16 }}>{stage.icon}</span>
                <span style={{ fontSize: 9, fontWeight: 600, color, marginTop: 2, textAlign: 'center', lineHeight: 1.2 }}>
                  {stage.label}
                </span>
                {isRunning && (
                  <span style={{
                    position: 'absolute', bottom: -6,
                    width: 6, height: 6, borderRadius: '50%', background: C.blue,
                    animation: 'pulse 1.2s infinite',
                  }} />
                )}
                {isPaused && (
                  <span style={{
                    position: 'absolute', bottom: -6,
                    fontSize: 8, color: C.orange, fontWeight: 800,
                  }}>⏸</span>
                )}
              </div>
              {i < STAGES.length - 1 && (
                <div style={{
                  width: 16, height: 2, flexShrink: 0,
                  background: i < idx || done ? C.accent : C.border,
                  transition: 'background 0.3s',
                }} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Decision card for MANUAL_REVIEW ─────────────────────────────────────────
function DecisionCard({ run, onProceed, onKill }: {
  run: PipelineRun
  onProceed: () => void
  onKill: () => void
}) {
  const [proceeding, setProceeding] = useState(false)
  const [killing,    setKilling]    = useState(false)
  const [err,        setErr]        = useState('')

  const stageLabel = STAGES.find(s => s.id === run.current_stage)?.label ?? run.current_stage

  async function handleProceed() {
    if (!confirm('Override this review and deploy the build as-is? The issue will be noted but NOT fixed.')) return
    setProceeding(true); setErr('')
    try {
      await api.proceedPipeline(run.run_id)
      onProceed()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Proceed failed')
    } finally { setProceeding(false) }
  }

  async function handleKill() {
    if (!confirm(`Kill venture ${run.venture_id}? This cannot be undone.`)) return
    setKilling(true); setErr('')
    try {
      await api.killVenture(run.venture_id)
      onKill()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Kill failed')
    } finally { setKilling(false) }
  }

  return (
    <div style={{
      marginTop: 16,
      background: 'rgba(245,158,11,0.06)',
      border: `1px solid rgba(245,158,11,0.4)`,
      borderRadius: 10, padding: '16px 20px',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span style={{ fontSize: 24, flexShrink: 0, marginTop: 2 }}>⏸</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: C.orange, marginBottom: 4 }}>
            Pipeline paused — {stageLabel} requires your decision
          </div>
          {run.last_error && (
            <div style={{
              fontSize: 12, color: '#fcd34d', fontFamily: 'monospace',
              background: 'rgba(0,0,0,0.3)', borderRadius: 6,
              padding: '8px 12px', marginBottom: 12, lineHeight: 1.6,
              maxHeight: 80, overflowY: 'auto',
            }}>
              {run.last_error}
            </div>
          )}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <button
              onClick={handleProceed}
              disabled={proceeding || killing}
              style={{
                padding: '9px 20px', borderRadius: 8, border: 'none',
                background: proceeding ? '#1a2a1a' : 'linear-gradient(135deg,#166534,#14532d)',
                color: proceeding ? C.fgMuted : C.accent,
                fontWeight: 700, fontSize: 13, cursor: proceeding ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
                boxShadow: proceeding ? 'none' : '0 0 16px rgba(62,207,142,0.2)',
                transition: 'all 0.2s',
              }}
            >
              {proceeding ? '⏳ Deploying…' : '→ Proceed Anyway'}
            </button>
            <button
              onClick={handleKill}
              disabled={proceeding || killing}
              style={{
                padding: '9px 20px', borderRadius: 8,
                border: `1px solid rgba(239,68,68,0.5)`,
                background: killing ? '#1a0000' : 'rgba(239,68,68,0.08)',
                color: killing ? C.fgMuted : C.red,
                fontWeight: 700, fontSize: 13, cursor: killing ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              {killing ? '⏳ Killing…' : '✕ Kill Pipeline'}
            </button>
            <span style={{ fontSize: 11, color: C.fgDim, maxWidth: 280, lineHeight: 1.5 }}>
              "Proceed Anyway" deploys the build as-is, bypassing this gate.
            </span>
          </div>
          {err && <div style={{ marginTop: 8, fontSize: 11, color: C.red, fontFamily: 'monospace' }}>⚠ {err}</div>}
        </div>
      </div>
    </div>
  )
}

// ─── Active pipeline hero card ─────────────────────────────────────────────────
function ActivePipelineCard({ run, onRefresh, onKill }: {
  run: PipelineRun
  onRefresh: () => void
  onKill: () => void
}) {
  const [deployUrl, setDeployUrl] = useState<string | null>(null)
  const [deploying, setDeploying] = useState(false)
  const [deployErr, setDeployErr] = useState('')

  const isActive   = run.status === 'RUNNING' || run.status === 'STARTED'
  const isPaused   = run.status === 'MANUAL_REVIEW'
  const isComplete = run.status === 'COMPLETED'
  const isFailed   = run.status === 'FAILED'

  const idx  = stageIdx(run.current_stage)
  const pct  = isComplete ? 100 : Math.round(((idx + 1) / STAGES.length) * 100)
  const el   = elapsed(run.started_at)

  const statusColor = isActive ? C.blue : isComplete ? C.accent : isPaused ? C.orange : C.red

  async function deployNow() {
    setDeploying(true); setDeployErr('')
    try {
      const r = await api.deployVenture(run.venture_id)
      setDeployUrl(r.url)
      onRefresh()
    } catch (e) {
      setDeployErr(e instanceof Error ? e.message : 'Deploy failed')
    } finally { setDeploying(false) }
  }

  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.border}`,
      borderRadius: 12, padding: '20px 24px',
      boxShadow: isActive ? `0 0 0 1px rgba(59,130,246,0.2), 0 4px 24px rgba(59,130,246,0.08)` :
                 isPaused ? `0 0 0 1px rgba(245,158,11,0.2)` : 'none',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <span style={{
              display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
              background: statusColor,
              boxShadow: isActive ? `0 0 8px ${statusColor}` : 'none',
              animation: isActive ? 'pulse 1.2s infinite' : 'none',
            }} />
            <span style={{ fontFamily: 'monospace', fontSize: 13, color: C.fgMuted }}>
              {run.venture_id}
            </span>
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
              background: `${statusColor}22`, color: statusColor, fontFamily: 'monospace',
            }}>
              {run.status}
            </span>
          </div>
          <div style={{ fontSize: 11, color: C.fgDim, fontFamily: 'monospace' }}>
            {el} · {pct}% complete
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {isComplete && !deployUrl && (
            <button
              onClick={deployNow}
              disabled={deploying}
              style={{
                padding: '7px 18px', borderRadius: 8, border: 'none',
                background: deploying ? '#1a1a2e' : 'linear-gradient(135deg,#7c3aed,#6d28d9)',
                color: deploying ? C.fgMuted : '#fff',
                fontWeight: 700, fontSize: 12, cursor: deploying ? 'not-allowed' : 'pointer',
                boxShadow: deploying ? 'none' : '0 0 16px rgba(124,58,237,0.3)',
              }}
            >
              {deploying ? '⏳ Deploying…' : '🚀 Launch Product'}
            </button>
          )}
          {!isComplete && !isPaused && (
            <button
              onClick={onKill}
              style={{
                padding: '5px 12px', borderRadius: 6,
                border: `1px solid rgba(239,68,68,0.4)`,
                background: 'rgba(239,68,68,0.06)', color: C.red,
                fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'monospace',
              }}
            >
              Kill
            </button>
          )}
        </div>
      </div>

      {/* Stage tracker */}
      <PipelineStageTracker run={run} />

      {/* Progress bar */}
      <div style={{ marginTop: 12, background: '#1a1a2e', borderRadius: 4, height: 4, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: isFailed ? C.red : isPaused ? C.orange : isComplete ? C.accent : C.blue,
          transition: 'width 0.6s ease',
        }} />
      </div>

      {/* Live URL banner */}
      {deployUrl && (
        <a
          href={deployUrl} target="_blank" rel="noreferrer"
          style={{
            display: 'flex', alignItems: 'center', gap: 10, marginTop: 14,
            padding: '10px 16px', borderRadius: 8, textDecoration: 'none',
            background: 'rgba(62,207,142,0.08)', border: `1px solid rgba(62,207,142,0.3)`,
            color: C.accent, fontWeight: 700, fontSize: 13,
          }}
        >
          <span>🟢 Live →</span>
          <span style={{ fontSize: 11, fontWeight: 400, color: '#86efac', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {deployUrl}
          </span>
        </a>
      )}

      {/* Error line */}
      {run.last_error && !isPaused && (
        <div style={{ marginTop: 10, fontSize: 11, color: C.red, fontFamily: 'monospace', lineHeight: 1.5 }}>
          ⚠ {run.last_error.slice(0, 160)}
        </div>
      )}

      {/* Recent events */}
      {run.recent_events.length > 0 && !isPaused && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {run.recent_events.slice(-3).map((ev, i) => (
            <div key={i} style={{ fontSize: 10, color: C.fgDim, fontFamily: 'monospace' }}>
              › {String((ev as Record<string, unknown>).event_type ?? JSON.stringify(ev)).replace(/_/g, ' ').slice(0, 70)}
            </div>
          ))}
        </div>
      )}

      {/* Build actions when complete */}
      {isComplete && (
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <a href={`/api/builds/${run.venture_id}`} target="_blank" rel="noreferrer"
            style={{ fontSize: 11, padding: '4px 10px', borderRadius: 5, border: `1px solid ${C.border}`, background: C.panelAlt, color: C.fgMuted, textDecoration: 'none', fontFamily: 'monospace' }}>
            📁 Build files
          </a>
          <a href={`/api/builds/${run.venture_id}/download`}
            style={{ fontSize: 11, padding: '4px 10px', borderRadius: 5, border: `1px solid ${C.border}`, background: C.panelAlt, color: C.fgMuted, textDecoration: 'none', fontFamily: 'monospace' }}>
            ⬇ Download ZIP
          </a>
        </div>
      )}

      {/* Deploy error */}
      {deployErr && (
        <div style={{ marginTop: 8, fontSize: 11, color: C.red, fontFamily: 'monospace' }}>⚠ {deployErr}</div>
      )}

      {/* Decision card when paused */}
      {isPaused && (
        <DecisionCard
          run={run}
          onProceed={onRefresh}
          onKill={onRefresh}
        />
      )}
    </div>
  )
}

// ─── Compact run history row ──────────────────────────────────────────────────
function HistoryRow({ run }: { run: PipelineRun }) {
  const statusColor = {
    COMPLETED: C.accent, FAILED: C.red, MANUAL_REVIEW: C.orange,
    RUNNING: C.blue, STARTED: C.blue,
  }[run.status] ?? C.fgMuted

  const idx = stageIdx(run.current_stage)
  const pct = run.status === 'COMPLETED' ? 100 : Math.round(((idx + 1) / STAGES.length) * 100)

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '8px 12px', borderRadius: 6,
      border: `1px solid ${C.border}`, background: C.panelAlt,
      fontSize: 11,
    }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, flexShrink: 0, display: 'inline-block' }} />
      <span style={{ fontFamily: 'monospace', color: C.fgMuted, flexShrink: 0 }}>{run.venture_id}</span>
      <div style={{ flex: 1, background: C.border, borderRadius: 2, height: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: statusColor, transition: 'width 0.4s' }} />
      </div>
      <span style={{ color: statusColor, fontWeight: 700, fontFamily: 'monospace', flexShrink: 0, width: 90 }}>
        {run.current_stage.replace(/_NODE$/, '').replace(/_/g, ' ')}
      </span>
      <span style={{ color: C.fgDim, flexShrink: 0 }}>{elapsed(run.started_at)}</span>
    </div>
  )
}

// ─── Portfolio card ───────────────────────────────────────────────────────────
function PortfolioCard({ slot }: { slot: PortfolioSlot & { live_url?: string; niche?: string } }) {
  const isLive = slot.status === 'LIVE' || slot.live_url
  const statusColor = isLive ? C.accent : slot.status === 'DEVELOPMENT' ? C.blue : C.fgDim

  return (
    <div style={{
      padding: '12px 16px', borderRadius: 8,
      border: `1px solid ${isLive ? 'rgba(62,207,142,0.3)' : C.border}`,
      background: isLive ? 'rgba(62,207,142,0.04)' : C.panelAlt,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: 'monospace', fontSize: 10, color: C.fgDim, marginBottom: 3 }}>
            {slot.venture_id}
          </div>
          <div style={{ fontSize: 12, fontWeight: 600, color: C.fg, marginBottom: 4, lineHeight: 1.4 }}>
            {slot.niche || 'Pending niche'}
          </div>
          {slot.live_url && (
            <a href={slot.live_url} target="_blank" rel="noreferrer"
              style={{ fontSize: 10, color: C.accent, textDecoration: 'none', wordBreak: 'break-all' }}>
              {slot.live_url}
            </a>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
          <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 3,
            background: `${statusColor}22`, color: statusColor, fontFamily: 'monospace' }}>
            {slot.status}
          </span>
          {slot.mrr_usd > 0 && (
            <span style={{ fontSize: 11, fontWeight: 700, color: C.accent }}>
              {usd(slot.mrr_usd)}/mo
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Agent health grid ────────────────────────────────────────────────────────
function AgentHealthRow({ agent }: { agent: AgentRow }) {
  const isRunning = agent.status === 'RUNNING'
  const isFailed  = agent.status === 'FAILED'
  const color = isRunning ? C.blue : isFailed ? C.red : agent.success_ratio > 0.8 ? C.accent : C.fgMuted

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: `1px solid ${C.border}` }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0, display: 'inline-block',
        boxShadow: isRunning ? `0 0 6px ${color}` : 'none', animation: isRunning ? 'pulse 1.2s infinite' : 'none' }} />
      <span style={{ flex: 1, fontSize: 11, color: C.fgMuted, fontFamily: 'monospace',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {agent.agent_name.replace(/_/g, ' ')}
      </span>
      <span style={{ fontSize: 10, color: C.fgDim, fontFamily: 'monospace', flexShrink: 0 }}>
        {agent.status === 'RUNNING' ? '▶' : agent.success_ratio > 0 ? `${(agent.success_ratio * 100).toFixed(0)}%` : '●'}
      </span>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function CommandCenter() {
  const [revenue,    setRevenue]    = useState<RevenueSummary | null>(null)
  const [confidence, setConfidence] = useState<ConfidenceReport | null>(null)
  const [agents,     setAgents]     = useState<AgentRow[]>([])
  const [slots,      setSlots]      = useState<(PortfolioSlot & { live_url?: string; niche?: string })[]>([])
  const [ventures,   setVentures]   = useState<Venture[]>([])
  const [runs,       setRuns]       = useState<PipelineRun[]>([])
  const [launching,  setLaunching]  = useState(false)
  const [launchErr,  setLaunchErr]  = useState('')
  const [lastTick,   setLastTick]   = useState('')
  const [apiErr,     setApiErr]     = useState('')

  const pollTimers = useRef(new Map<string, ReturnType<typeof setInterval>>())

  // ── Polling individual run ────────────────────────────────────────────────
  const pollRun = useCallback((run_id: string) => {
    if (pollTimers.current.has(run_id)) return
    const timer = setInterval(async () => {
      try {
        const run = await api.pipelineStatus(run_id)
        setRuns(prev => prev.map(r => r.run_id === run_id ? run : r))
        if (!['STARTED', 'RUNNING'].includes(run.status)) {
          clearInterval(pollTimers.current.get(run_id))
          pollTimers.current.delete(run_id)
        }
      } catch {
        clearInterval(pollTimers.current.get(run_id))
        pollTimers.current.delete(run_id)
      }
    }, 3000)
    pollTimers.current.set(run_id, timer)
  }, [])

  // ── Data refresh ──────────────────────────────────────────────────────────
  const refresh = useCallback(async () => {
    try {
      const [a, r, conf, venRes, runsRes] = await Promise.all([
        api.agents().catch(() => ({ agents: [], source: 'offline' })),
        api.revenue().catch(() => null),
        api.confidence().catch(() => null),
        api.ventures().catch(() => ({ ventures: [], count: 0 })),
        api.pipelineRecent().catch(() => ({ runs: [], count: 0 })),
      ])
      setAgents(a.agents)
      if (r) setRevenue(r)
      if (conf) setConfidence(conf)
      setVentures(venRes.ventures)
      setRuns((prev: PipelineRun[]) => {
        const serverById = new Map<string, PipelineRun>(
          runsRes.runs.map((r: PipelineRun) => [r.run_id, r] as [string, PipelineRun])
        )
        const merged: PipelineRun[] = prev.map(r => serverById.get(r.run_id) ?? r)
        runsRes.runs.forEach((r: PipelineRun) => {
          if (!merged.find(m => m.run_id === r.run_id)) merged.unshift(r)
        })
        return merged.slice(0, 50)
      })

      // Build portfolio from ventures
      const portfolioSlots = venRes.ventures
        .filter(v => v.status !== 'KILLED')
        .map((v, i) => ({
          slot: i + 1, venture_id: v.venture_id,
          status: v.status, niche: v.niche, mrr_usd: 0,
          live_url: (v as Venture & { live_url?: string }).live_url,
        }))
      setSlots(portfolioSlots)

      setApiErr('')
      setLastTick(new Date().toLocaleTimeString())
    } catch {
      setApiErr('API unreachable — check Railway service is running')
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30_000)
    return () => clearInterval(id)
  }, [refresh])

  // Auto-poll active runs
  useEffect(() => {
    runs.forEach(r => { if (r.status === 'STARTED' || r.status === 'RUNNING') pollRun(r.run_id) })
  }, [runs, pollRun])

  // WebSocket live tick
  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/api/ws/live`)
    ws.onmessage = ev => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'tick' && msg.revenue) setRevenue(msg.revenue)
      } catch { /* ignore */ }
    }
    return () => ws.close()
  }, [])

  useEffect(() => () => pollTimers.current.forEach(t => clearInterval(t)), [])

  // ── Actions ───────────────────────────────────────────────────────────────
  async function launchPipeline() {
    setLaunching(true); setLaunchErr('')
    try {
      const result = await api.pipelineRun()
      const stub: PipelineRun = {
        run_id: result.run_id, venture_id: result.venture_id,
        department: 'PRODUCT', status: 'STARTED',
        current_stage: 'RESEARCH_NODE',
        started_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        completed_at: null, event_count: 0, recent_events: [], last_error: null,
      }
      setRuns(prev => [stub, ...prev])
      pollRun(result.run_id)
    } catch (e) {
      setLaunchErr(e instanceof Error ? e.message : 'Launch failed')
    } finally { setLaunching(false) }
  }

  // ── Derived ───────────────────────────────────────────────────────────────
  const mrr  = revenue?.mrr_usd ?? 0
  const burn = revenue?.burn_usd ?? 0
  const net  = revenue?.net_mrr_usd ?? 0
  const conf = confidence?.confidence_score ?? 0

  const killedIds = new Set(ventures.filter(v => v.status === 'KILLED').map(v => v.venture_id))
  const visibleRuns = runs.filter(r => !killedIds.has(r.venture_id))
  const activeRuns  = visibleRuns.filter(r => ['STARTED', 'RUNNING', 'MANUAL_REVIEW'].includes(r.status))
  const historyRuns = visibleRuns.filter(r => ['COMPLETED', 'FAILED'].includes(r.status)).slice(0, 8)
  const liveVentures = slots.filter(s => s.status === 'LIVE' || s.live_url)

  return (
    <div style={{ background: C.bg, minHeight: '100vh', color: C.fg }}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #2e2e4a; border-radius: 4px; }
      `}</style>

      {/* ── Top bar ──────────────────────────────────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: `${C.bg}ee`, backdropFilter: 'blur(12px)',
        borderBottom: `1px solid ${C.border}`,
        padding: '0 24px', height: 56,
        display: 'flex', alignItems: 'center', gap: 24,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <span style={{ fontSize: 18 }}>⚡</span>
          <div>
            <div style={{ fontWeight: 800, fontSize: 13, letterSpacing: '-0.5px' }}>AI Squadron</div>
            <div style={{ fontSize: 9, color: C.fgDim, fontFamily: 'monospace' }}>COMMAND CENTER</div>
          </div>
        </div>

        {/* Metrics strip */}
        <div style={{ display: 'flex', gap: 0, flex: 1 }}>
          {[
            { label: 'MRR', value: usd(mrr), color: mrr > 0 ? C.accent : C.fgMuted },
            { label: 'Burn', value: usd(burn), color: C.red },
            { label: 'Net', value: usd(net), color: net >= 0 ? C.accent : C.red },
            { label: 'Confidence', value: `${conf}/100`, color: conf >= 50 ? C.accent : conf >= 25 ? C.orange : C.fgMuted },
          ].map(m => (
            <div key={m.label} style={{ padding: '0 16px', borderRight: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 9, color: C.fgDim, fontFamily: 'monospace', marginBottom: 1 }}>{m.label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: m.color, fontFamily: 'monospace' }}>{m.value}</div>
            </div>
          ))}
          <div style={{ padding: '0 16px', borderRight: `1px solid ${C.border}` }}>
            <div style={{ fontSize: 9, color: C.fgDim, fontFamily: 'monospace', marginBottom: 1 }}>LIVE</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.accent, fontFamily: 'monospace' }}>{liveVentures.length}</div>
          </div>
          <div style={{ padding: '0 16px' }}>
            <div style={{ fontSize: 9, color: C.fgDim, fontFamily: 'monospace', marginBottom: 1 }}>ACTIVE</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: activeRuns.length > 0 ? C.blue : C.fgMuted, fontFamily: 'monospace' }}>
              {activeRuns.length}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
          {lastTick && (
            <span style={{ fontSize: 10, color: C.fgDim, fontFamily: 'monospace' }}>
              {lastTick}
            </span>
          )}
          <button
            onClick={launchPipeline}
            disabled={launching}
            style={{
              padding: '7px 18px', borderRadius: 8, border: 'none',
              background: launching ? C.panelAlt : `linear-gradient(135deg,${C.purple},#6d28d9)`,
              color: launching ? C.fgMuted : '#fff',
              fontWeight: 700, fontSize: 12, cursor: launching ? 'not-allowed' : 'pointer',
              boxShadow: launching ? 'none' : `0 0 16px ${C.purpleGlow}`,
              transition: 'all 0.2s',
            }}
          >
            {launching ? '⏳ Launching…' : '+ Launch Pipeline'}
          </button>
          <button
            onClick={async () => {
              if (!confirm('Kill all IDEATION + stale DEVELOPMENT ventures? Deployed ones are kept.')) return
              await fetch('/api/ventures/cleanup', { method: 'POST' })
              refresh()
            }}
            style={{
              padding: '7px 12px', borderRadius: 8,
              border: `1px solid rgba(239,68,68,0.3)`,
              background: 'rgba(239,68,68,0.06)', color: C.red,
              fontSize: 11, fontWeight: 700, cursor: 'pointer',
            }}
          >
            🗑 Cleanup
          </button>
        </div>
      </div>

      {/* ── Error banner ─────────────────────────────────────────────────────── */}
      {apiErr && (
        <div style={{
          background: 'rgba(239,68,68,0.1)', borderBottom: `1px solid rgba(239,68,68,0.3)`,
          padding: '10px 24px', fontSize: 12, color: C.red, fontFamily: 'monospace',
        }}>
          ⚠ {apiErr}
        </div>
      )}
      {launchErr && (
        <div style={{
          background: 'rgba(239,68,68,0.1)', borderBottom: `1px solid rgba(239,68,68,0.3)`,
          padding: '10px 24px', fontSize: 12, color: C.red,
        }}>
          Launch failed: {launchErr}
        </div>
      )}

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '24px 24px 48px' }}>

        {/* ── Active pipelines (hero) ─────────────────────────────────────────── */}
        <section style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, letterSpacing: '-0.3px' }}>
              Active Pipelines
              {activeRuns.length > 0 && (
                <span style={{ marginLeft: 8, fontSize: 11, background: `${C.blue}22`, color: C.blue,
                  padding: '2px 8px', borderRadius: 10, fontWeight: 600 }}>
                  {activeRuns.length} running
                </span>
              )}
            </h2>
            <span style={{ fontSize: 11, color: C.fgDim }}>
              Research → CEO → Engineering → QA → Security → Legal → Deploy
            </span>
          </div>

          {activeRuns.length === 0 ? (
            <div style={{
              background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: '40px 24px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>🚀</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: C.fg, marginBottom: 6 }}>No active pipelines</div>
              <div style={{ fontSize: 12, color: C.fgMuted, marginBottom: 20 }}>
                Launch a pipeline to autonomously research a niche, build a SaaS product, and deploy it to Railway.
              </div>
              <button
                onClick={launchPipeline}
                disabled={launching}
                style={{
                  padding: '10px 28px', borderRadius: 8, border: 'none',
                  background: `linear-gradient(135deg,${C.purple},#6d28d9)`,
                  color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer',
                  boxShadow: `0 0 20px ${C.purpleGlow}`,
                }}
              >
                {launching ? '⏳ Launching…' : '+ Launch First Pipeline'}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {activeRuns.map(run => (
                <ActivePipelineCard
                  key={run.run_id}
                  run={run}
                  onRefresh={refresh}
                  onKill={() => api.killVenture(run.venture_id).then(refresh).catch(() => {})}
                />
              ))}
            </div>
          )}
        </section>

        {/* ── Recent history ─────────────────────────────────────────────────── */}
        {historyRuns.length > 0 && (
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 700, color: C.fgMuted }}>
              Recent Runs
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {historyRuns.map(run => <HistoryRow key={run.run_id} run={run} />)}
            </div>
          </section>
        )}

        {/* ── Bottom grid: Portfolio + Agents ──────────────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20 }}>

          {/* Portfolio */}
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>
                Portfolio
                <span style={{ marginLeft: 8, fontSize: 11, color: C.fgMuted, fontWeight: 400 }}>
                  {slots.length} venture{slots.length !== 1 ? 's' : ''}
                  {liveVentures.length > 0 && ` · ${liveVentures.length} live`}
                </span>
              </h2>
            </div>
            {slots.length === 0 ? (
              <div style={{
                background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10,
                padding: '32px 24px', textAlign: 'center',
                color: C.fgMuted, fontSize: 12,
              }}>
                No ventures yet — launch a pipeline to generate your first SaaS product.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
                {slots.map(s => <PortfolioCard key={s.venture_id} slot={s} />)}
              </div>
            )}
          </section>

          {/* Agent health */}
          <section>
            <h2 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>
              Agent Health
            </h2>
            <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, padding: '12px 16px' }}>
              {agents.length === 0 ? (
                <div style={{ fontSize: 11, color: C.fgDim, textAlign: 'center', padding: '20px 0' }}>
                  No agent data yet
                </div>
              ) : (
                agents.map(a => <AgentHealthRow key={a.agent_name} agent={a} />)
              )}
            </div>

            {/* Confidence panel */}
            {confidence && (
              <div style={{
                marginTop: 12, background: C.panel,
                border: `1px solid ${C.border}`, borderRadius: 10, padding: '14px 16px',
              }}>
                <div style={{ fontSize: 11, color: C.fgMuted, marginBottom: 8, fontWeight: 600 }}>CONFIDENCE SCORE</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
                  <span style={{
                    fontSize: 32, fontWeight: 900,
                    color: conf >= 60 ? C.accent : conf >= 30 ? C.orange : C.red,
                  }}>{conf}</span>
                  <span style={{ fontSize: 12, color: C.fgMuted }}>/100 · {confidence.confidence_tier}</span>
                </div>
                <div style={{ background: C.border, borderRadius: 4, height: 6, overflow: 'hidden', marginBottom: 12 }}>
                  <div style={{
                    width: `${conf}%`, height: '100%',
                    background: conf >= 60 ? C.accent : conf >= 30 ? C.orange : C.red,
                    transition: 'width 0.6s ease',
                  }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {[
                    ['12mo p50 MRR', usd(confidence.forecast_p50_mrr_12mo)],
                    ['QA pass rate', `${confidence.leading_indicators?.qa_first_pass_rate_pct ?? 0}%`],
                    ['Completed runs', String(confidence.leading_indicators?.completed_pipeline_runs ?? 0)],
                  ].map(([label, value]) => (
                    <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                      <span style={{ color: C.fgDim }}>{label}</span>
                      <span style={{ color: C.fg, fontFamily: 'monospace', fontWeight: 600 }}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
