/**
 * CommandCenter.tsx — AI Squadron operations hub
 *
 * Layout:
 *   TopBar    → logo · metrics · green live clock · launch button
 *   3D Hero   → immersive sci-fi agent pipeline (active run or dormant)
 *   Row 2     → Confidence score card (left) + Recent Runs 2-max + See All (right)
 *   Row 3     → Portfolio (left) + Agent Health (right)
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

// ─── Pipeline stages (correct order) ─────────────────────────────────────────
const STAGES = [
  { id: 'RESEARCH_NODE',        label: 'Research',    icon: '🔍' },
  { id: 'CEO_NODE',             label: 'CEO',         icon: '👔' },
  { id: 'PRODUCT_VP_NODE',      label: 'VP',          icon: '📋' },
  { id: 'PRODUCT_MANAGER_NODE', label: 'PM',          icon: '📝' },
  { id: 'ENGINEERING_NODE',     label: 'Engineering', icon: '⚙️' },
  { id: 'QA_TECHNICAL_NODE',    label: 'QA',          icon: '🧪' },
  { id: 'SECURITY_NODE',        label: 'Security',    icon: '🛡️' },
  { id: 'LEGAL_NODE',           label: 'Legal',       icon: '⚖️' },
  { id: 'DEPLOYMENT_NODE',      label: 'Deploy',      icon: '🚀' },
  { id: 'MARKETING_SEO_NODE',   label: 'Marketing',   icon: '📢' },
  { id: 'PRODUCT_GROWTH_NODE',  label: 'Growth',      icon: '📈' },
]

// ─── Per-state visual theme ───────────────────────────────────────────────────
const THEME = {
  done:   { border: 'rgba(62,207,142,0.55)',  bg: 'rgba(62,207,142,0.08)',  glow: 'rgba(62,207,142,0.45)',  label: '#3ecf8e', screen: '#3ecf8e',  text: '✓ DONE'   },
  active: { border: 'rgba(59,130,246,0.80)',  bg: 'rgba(59,130,246,0.12)',  glow: 'rgba(59,130,246,0.55)',  label: '#60a5fa', screen: '#60a5fa',  text: '▶ RUN'    },
  paused: { border: 'rgba(245,158,11,0.80)',  bg: 'rgba(245,158,11,0.10)',  glow: 'rgba(245,158,11,0.50)',  label: '#fcd34d', screen: '#fcd34d',  text: '⏸ HOLD'   },
  failed: { border: 'rgba(239,68,68,0.80)',   bg: 'rgba(239,68,68,0.10)',   glow: 'rgba(239,68,68,0.50)',   label: '#f87171', screen: '#f87171',  text: '✕ FAIL'   },
  idle:   { border: '#252540',                bg: 'rgba(18,18,42,0.5)',     glow: 'none',                   label: '#383860', screen: '#1e1e3a',  text: '· · ·'    },
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function usd(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}
function elapsed(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60)   return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}
function stageIdx(current: string): number {
  return Math.max(0, STAGES.findIndex(s => s.id === current))
}

// ─── 3D Immersive Agent Pipeline ──────────────────────────────────────────────
function AgentPipeline3D({ run }: { run: PipelineRun | null }) {
  const idx    = run ? stageIdx(run.current_stage) : -1
  const isComp = run?.status === 'COMPLETED'
  const isAct  = !!(run && (run.status === 'RUNNING' || run.status === 'STARTED'))
  const isPaused = run?.status === 'MANUAL_REVIEW'
  const isFail   = run?.status === 'FAILED'

  return (
    <div style={{
      background: 'radial-gradient(ellipse at 50% 90%, #0c0c22 0%, #050510 60%)',
      borderRadius: 14, padding: '32px 20px 22px',
      border: '1px solid #1a1a3a', overflow: 'visible', position: 'relative',
    }}>
      {/* Sci-fi grid overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', borderRadius: 14,
        backgroundImage:
          'linear-gradient(rgba(62,207,142,0.022) 1px, transparent 1px),' +
          'linear-gradient(90deg, rgba(62,207,142,0.022) 1px, transparent 1px)',
        backgroundSize: '44px 44px',
      }} />

      {/* Corner decorations */}
      {['topleft','topright','bottomleft','bottomright'].map(pos => (
        <div key={pos} style={{
          position: 'absolute',
          top:    pos.startsWith('top')    ? 8 : undefined,
          bottom: pos.startsWith('bottom') ? 8 : undefined,
          left:   pos.endsWith('left')     ? 8 : undefined,
          right:  pos.endsWith('right')    ? 8 : undefined,
          width: 12, height: 12,
          borderTop:    pos.startsWith('top')    ? '1px solid rgba(62,207,142,0.3)' : 'none',
          borderBottom: pos.startsWith('bottom') ? '1px solid rgba(62,207,142,0.3)' : 'none',
          borderLeft:   pos.endsWith('left')     ? '1px solid rgba(62,207,142,0.3)' : 'none',
          borderRight:  pos.endsWith('right')    ? '1px solid rgba(62,207,142,0.3)' : 'none',
          pointerEvents: 'none',
        }} />
      ))}

      {/* Status badge */}
      <div style={{
        position: 'absolute', top: 10, left: 18,
        fontSize: 8, fontWeight: 700, letterSpacing: '0.18em',
        color: run ? (isAct ? '#3b82f6' : isComp ? '#3ecf8e' : isPaused ? '#f59e0b' : isFail ? '#ef4444' : '#334155') : '#252550',
        fontFamily: 'monospace',
      }}>
        ● {run ? `PIPELINE ${run.status}` : 'PIPELINE IDLE'}
      </div>

      {/* Active glow orb tracking the current node */}
      {isAct && idx >= 0 && (
        <div style={{
          position: 'absolute', top: '55%',
          left: `calc(${((idx + 0.5) / STAGES.length) * 100}%)`,
          transform: 'translate(-50%, -50%)',
          width: 160, height: 100, borderRadius: '50%', pointerEvents: 'none',
          background: 'radial-gradient(circle, rgba(59,130,246,0.10) 0%, transparent 70%)',
          transition: 'left 1s ease',
        }} />
      )}

      {/* 3D perspective wrapper */}
      <div style={{ perspective: '700px', perspectiveOrigin: '50% 120%' }}>
        <div style={{
          display: 'flex', alignItems: 'flex-end', gap: 0,
          transform: 'rotateX(9deg)',
          transformOrigin: 'center bottom',
          overflowX: 'auto',
          paddingBottom: 4, paddingTop: 8,
        }}>
          {STAGES.map((stage, i) => {
            let state: keyof typeof THEME = 'idle'
            if (isComp || i < idx)             state = 'done'
            if (i === idx && isAct)            state = 'active'
            if (i === idx && isPaused)         state = 'paused'
            if (i === idx && isFail)           state = 'failed'

            const th = THEME[state]
            const lineGreen = state === 'done' || (isComp && i < STAGES.length)

            return (
              <div key={stage.id} style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>

                {/* Agent node */}
                <div style={{
                  flex: '0 0 auto', minWidth: 64,
                  display: 'flex', flexDirection: 'column', alignItems: 'center',
                  padding: '10px 4px 8px',
                  background: th.bg,
                  border: `1px solid ${th.border}`,
                  borderRadius: 10,
                  boxShadow: th.glow !== 'none'
                    ? `0 0 20px ${th.glow}, 0 0 44px ${th.glow.replace(/[\d.]+\)$/, '0.12)')}`
                    : 'none',
                  transition: 'all 0.5s ease',
                  position: 'relative', cursor: 'default',
                }}>
                  {/* Pulse ring on active node */}
                  {state === 'active' && (
                    <div style={{
                      position: 'absolute', inset: -4, borderRadius: 14,
                      border: '1px solid rgba(59,130,246,0.4)',
                      animation: 'pulse-ring 1.8s ease-out infinite',
                      pointerEvents: 'none',
                    }} />
                  )}

                  {/* Icon */}
                  <span style={{
                    fontSize: 17, lineHeight: 1, marginBottom: 4,
                    opacity: state === 'idle' ? 0.25 : 1,
                    transition: 'opacity 0.5s',
                    filter: state !== 'idle' && state !== 'done'
                      ? `drop-shadow(0 0 4px ${th.label})`
                      : 'none',
                  }}>
                    {stage.icon}
                  </span>

                  {/* Label */}
                  <span style={{
                    fontSize: 7.5, fontWeight: 700, letterSpacing: '0.07em',
                    color: th.label, textAlign: 'center', lineHeight: 1.2,
                    marginBottom: 6,
                    textShadow: th.glow !== 'none' ? `0 0 8px ${th.glow}` : 'none',
                    transition: 'color 0.5s',
                  }}>
                    {stage.label.toUpperCase()}
                  </span>

                  {/* Mini CRT screen */}
                  <div style={{
                    width: '100%', background: '#010308',
                    border: `1px solid ${th.border}`,
                    borderRadius: 3, padding: '3px 3px',
                    fontFamily: 'monospace', fontSize: 6,
                    color: th.screen, textAlign: 'center',
                    minHeight: 16, letterSpacing: '0.04em',
                    position: 'relative', overflow: 'hidden',
                    transition: 'all 0.5s',
                  }}>
                    {/* CRT scanlines */}
                    <div style={{
                      position: 'absolute', inset: 0, pointerEvents: 'none',
                      backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 1px, rgba(0,0,0,0.22) 1px, rgba(0,0,0,0.22) 2px)',
                    }} />
                    <span style={{ position: 'relative' }}>{th.text}</span>
                  </div>
                </div>

                {/* Neon connector */}
                {i < STAGES.length - 1 && (
                  <div style={{
                    flex: 1, height: 2, minWidth: 2,
                    background: lineGreen
                      ? 'linear-gradient(90deg,#3ecf8e,#2ab87a)'
                      : '#1a1a3a',
                    boxShadow: lineGreen ? '0 0 7px rgba(62,207,142,0.55)' : 'none',
                    transition: 'all 0.5s ease',
                    position: 'relative', overflow: 'hidden',
                  }}>
                    {lineGreen && (
                      <div style={{
                        position: 'absolute', top: 0, width: '50%', height: '100%',
                        background: 'linear-gradient(90deg,transparent,rgba(255,255,255,0.55),transparent)',
                        animation: `data-packet ${2.2 + (i % 3) * 0.4}s linear infinite`,
                      }} />
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ─── Decision card (MANUAL_REVIEW) ───────────────────────────────────────────
function DecisionCard({ run, onProceed, onKill }: {
  run: PipelineRun; onProceed: () => void; onKill: () => void
}) {
  const [proceeding, setProceeding] = useState(false)
  const [killing,    setKilling]    = useState(false)
  const [err,        setErr]        = useState('')
  const stageLabel = STAGES.find(s => s.id === run.current_stage)?.label ?? run.current_stage

  async function handleProceed() {
    if (!confirm('Override this review and deploy the build as-is? The issue will be noted but NOT fixed.')) return
    setProceeding(true); setErr('')
    try { await api.proceedPipeline(run.run_id); onProceed() }
    catch (e) { setErr(e instanceof Error ? e.message : 'Proceed failed') }
    finally { setProceeding(false) }
  }
  async function handleKill() {
    if (!confirm(`Kill venture ${run.venture_id}? This cannot be undone.`)) return
    setKilling(true); setErr('')
    try { await api.killVenture(run.venture_id); onKill() }
    catch (e) { setErr(e instanceof Error ? e.message : 'Kill failed') }
    finally { setKilling(false) }
  }

  return (
    <div style={{ marginTop: 16, background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.35)', borderRadius: 10, padding: '16px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span style={{ fontSize: 22, flexShrink: 0, marginTop: 2 }}>⏸</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: C.orange, marginBottom: 4 }}>
            Pipeline paused — {stageLabel} requires your decision
          </div>
          {run.last_error && (
            <div style={{ fontSize: 11, color: '#fcd34d', fontFamily: 'monospace', background: 'rgba(0,0,0,0.3)', borderRadius: 6, padding: '8px 12px', marginBottom: 12, lineHeight: 1.6, maxHeight: 80, overflowY: 'auto' }}>
              {run.last_error}
            </div>
          )}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <button
              onClick={handleProceed} disabled={proceeding || killing}
              style={{ padding: '9px 20px', borderRadius: 8, border: 'none', background: proceeding ? '#1a2a1a' : 'linear-gradient(135deg,#166534,#14532d)', color: proceeding ? C.fgMuted : C.accent, fontWeight: 700, fontSize: 13, cursor: proceeding ? 'not-allowed' : 'pointer' }}
            >
              {proceeding ? '⏳ Deploying…' : '→ Proceed Anyway'}
            </button>
            <button
              onClick={handleKill} disabled={proceeding || killing}
              style={{ padding: '9px 20px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.5)', background: killing ? '#1a0000' : 'rgba(239,68,68,0.08)', color: killing ? C.fgMuted : C.red, fontWeight: 700, fontSize: 13, cursor: killing ? 'not-allowed' : 'pointer' }}
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

// ─── Active pipeline detail card ──────────────────────────────────────────────
function ActivePipelineCard({ run, onRefresh, onKill }: {
  run: PipelineRun; onRefresh: () => void; onKill: () => void
}) {
  const [deployUrl, setDeployUrl] = useState<string | null>(null)
  const [deploying, setDeploying] = useState(false)
  const [deployErr, setDeployErr] = useState('')

  const isActive   = run.status === 'RUNNING' || run.status === 'STARTED'
  const isPaused   = run.status === 'MANUAL_REVIEW'
  const isComplete = run.status === 'COMPLETED'
  const isFailed   = run.status === 'FAILED'
  const idx        = stageIdx(run.current_stage)
  const pct        = isComplete ? 100 : Math.round(((idx + 1) / STAGES.length) * 100)
  const statusColor = isActive ? C.blue : isComplete ? C.accent : isPaused ? C.orange : C.red

  async function deployNow() {
    setDeploying(true); setDeployErr('')
    try { const r = await api.deployVenture(run.venture_id); setDeployUrl(r.url); onRefresh() }
    catch (e) { setDeployErr(e instanceof Error ? e.message : 'Deploy failed') }
    finally { setDeploying(false) }
  }

  return (
    <div style={{
      background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 22px',
      boxShadow: isActive  ? `0 0 0 1px rgba(59,130,246,0.15), 0 4px 24px rgba(59,130,246,0.06)` :
                 isPaused  ? `0 0 0 1px rgba(245,158,11,0.15)` : 'none',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 3 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%', background: statusColor,
              display: 'inline-block', flexShrink: 0,
              boxShadow: isActive ? `0 0 8px ${statusColor}` : 'none',
              animation: isActive ? 'pulse 1.2s infinite' : 'none',
            }} />
            <span style={{ fontFamily: 'monospace', fontSize: 13, color: C.fgMuted }}>{run.venture_id}</span>
            <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4, background: `${statusColor}22`, color: statusColor, fontFamily: 'monospace' }}>
              {run.status}
            </span>
          </div>
          <div style={{ fontSize: 11, color: C.fgDim, fontFamily: 'monospace' }}>
            {elapsed(run.started_at)} · {pct}% complete
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {isComplete && !deployUrl && (
            <button onClick={deployNow} disabled={deploying} style={{
              padding: '7px 18px', borderRadius: 8, border: 'none',
              background: deploying ? '#1a1a2e' : `linear-gradient(135deg,${C.purple},#6d28d9)`,
              color: deploying ? C.fgMuted : '#fff', fontWeight: 700, fontSize: 12,
              cursor: deploying ? 'not-allowed' : 'pointer',
            }}>
              {deploying ? '⏳ Deploying…' : '🚀 Launch Product'}
            </button>
          )}
          {!isComplete && !isPaused && (
            <button onClick={onKill} style={{
              padding: '5px 12px', borderRadius: 6,
              border: '1px solid rgba(239,68,68,0.4)',
              background: 'rgba(239,68,68,0.06)', color: C.red,
              fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'monospace',
            }}>Kill</button>
          )}
        </div>
      </div>

      {/* Thin progress bar */}
      <div style={{ background: '#1a1a2e', borderRadius: 4, height: 3, overflow: 'hidden', marginBottom: 10 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: isFailed ? C.red : isPaused ? C.orange : isComplete ? C.accent : C.blue, transition: 'width 0.6s ease' }} />
      </div>

      {/* Live URL */}
      {deployUrl && (
        <a href={deployUrl} target="_blank" rel="noreferrer" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, padding: '10px 16px', borderRadius: 8, textDecoration: 'none', background: 'rgba(62,207,142,0.08)', border: '1px solid rgba(62,207,142,0.3)', color: C.accent, fontWeight: 700, fontSize: 13 }}>
          <span>🟢 Live →</span>
          <span style={{ fontSize: 11, fontWeight: 400, color: '#86efac', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{deployUrl}</span>
        </a>
      )}

      {/* Error (non-paused) */}
      {run.last_error && !isPaused && (
        <div style={{ fontSize: 11, color: C.red, fontFamily: 'monospace', lineHeight: 1.5, marginBottom: 6 }}>
          ⚠ {run.last_error.slice(0, 220)}
        </div>
      )}

      {/* Recent events */}
      {run.recent_events.length > 0 && !isPaused && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {run.recent_events.slice(-3).map((ev, i) => (
            <div key={i} style={{ fontSize: 10, color: C.fgDim, fontFamily: 'monospace' }}>
              › {String((ev as Record<string, unknown>).event_type ?? JSON.stringify(ev)).replace(/_/g, ' ').slice(0, 80)}
            </div>
          ))}
        </div>
      )}

      {/* Build actions when complete */}
      {isComplete && (
        <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
          <a href={`/api/builds/${run.venture_id}`} target="_blank" rel="noreferrer" style={{ fontSize: 11, padding: '4px 10px', borderRadius: 5, border: `1px solid ${C.border}`, background: C.panelAlt, color: C.fgMuted, textDecoration: 'none', fontFamily: 'monospace' }}>📁 Build files</a>
          <a href={`/api/builds/${run.venture_id}/download`} style={{ fontSize: 11, padding: '4px 10px', borderRadius: 5, border: `1px solid ${C.border}`, background: C.panelAlt, color: C.fgMuted, textDecoration: 'none', fontFamily: 'monospace' }}>⬇ Download ZIP</a>
        </div>
      )}

      {deployErr && <div style={{ marginTop: 8, fontSize: 11, color: C.red, fontFamily: 'monospace' }}>⚠ {deployErr}</div>}
      {isPaused && <DecisionCard run={run} onProceed={onRefresh} onKill={onRefresh} />}
    </div>
  )
}

// ─── History row (shows failed agent + error reason) ─────────────────────────
function HistoryRow({ run }: { run: PipelineRun }) {
  const statusColor = {
    COMPLETED:     C.accent,
    FAILED:        C.red,
    MANUAL_REVIEW: C.orange,
    RUNNING:       C.blue,
    STARTED:       C.blue,
  }[run.status] ?? C.fgMuted

  const idx        = stageIdx(run.current_stage)
  const pct        = run.status === 'COMPLETED' ? 100 : Math.round(((idx + 1) / STAGES.length) * 100)
  const failStage  = run.status === 'FAILED' ? STAGES.find(s => s.id === run.current_stage) : null

  return (
    <div style={{
      background: C.panelAlt,
      border: `1px solid ${run.status === 'FAILED' ? 'rgba(239,68,68,0.22)' : C.border}`,
      borderRadius: 8, padding: '10px 14px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, flexShrink: 0, display: 'inline-block' }} />
        <span style={{ fontFamily: 'monospace', color: C.fgMuted, flexShrink: 0, fontSize: 11 }}>{run.venture_id}</span>

        {failStage && (
          <span style={{
            fontSize: 10, color: C.red, fontFamily: 'monospace', flexShrink: 0,
            background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
            padding: '1px 6px', borderRadius: 4,
          }}>
            ✕ {failStage.icon} {failStage.label}
          </span>
        )}
        {run.status === 'COMPLETED' && (
          <span style={{ fontSize: 10, color: C.accent, fontFamily: 'monospace', flexShrink: 0 }}>✓ Done</span>
        )}

        <div style={{ flex: 1, background: C.border, borderRadius: 2, height: 3, overflow: 'hidden' }}>
          <div style={{ width: `${pct}%`, height: '100%', background: statusColor, transition: 'width 0.4s' }} />
        </div>
        <span style={{ color: C.fgDim, flexShrink: 0, fontSize: 10 }}>{elapsed(run.started_at)}</span>
      </div>

      {/* Error detail box — only for failed runs */}
      {run.status === 'FAILED' && run.last_error && (
        <div style={{
          marginTop: 8, padding: '7px 10px',
          background: 'rgba(239,68,68,0.05)',
          border: '1px solid rgba(239,68,68,0.15)',
          borderRadius: 5, fontFamily: 'monospace',
          fontSize: 10, color: '#fca5a5', lineHeight: 1.65,
          wordBreak: 'break-word',
        }}>
          {run.last_error.slice(0, 280)}{run.last_error.length > 280 ? '…' : ''}
        </div>
      )}
    </div>
  )
}

// ─── See All history popup ────────────────────────────────────────────────────
function HistoryPopup({ runs, onClose }: { runs: PipelineRun[]; onClose: () => void }) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(5,5,16,0.78)',
        backdropFilter: 'blur(10px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: C.panel, border: `1px solid ${C.border}`,
          borderRadius: 16, padding: '24px',
          maxWidth: 760, width: '100%', maxHeight: '80vh',
          overflow: 'hidden', display: 'flex', flexDirection: 'column',
          boxShadow: '0 24px 80px rgba(0,0,0,0.6)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>
            All Pipeline Runs
            <span style={{ marginLeft: 8, fontSize: 11, color: C.fgMuted, fontWeight: 400 }}>{runs.length} total</span>
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: `1px solid rgba(239,68,68,0.3)`,
              color: C.red, width: 28, height: 28, borderRadius: 6,
              cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >✕</button>
        </div>
        <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {runs.map(run => <HistoryRow key={run.run_id} run={run} />)}
          {runs.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px 0', color: C.fgDim, fontSize: 13 }}>
              No runs yet
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Portfolio card ───────────────────────────────────────────────────────────
function PortfolioCard({ slot }: { slot: PortfolioSlot & { live_url?: string; niche?: string } }) {
  const isLive = slot.status === 'LIVE' || !!slot.live_url
  const statusColor = isLive ? C.accent : slot.status === 'DEVELOPMENT' ? C.blue : C.fgDim
  return (
    <div style={{ padding: '12px 16px', borderRadius: 8, border: `1px solid ${isLive ? 'rgba(62,207,142,0.28)' : C.border}`, background: isLive ? 'rgba(62,207,142,0.04)' : C.panelAlt }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: 'monospace', fontSize: 10, color: C.fgDim, marginBottom: 3 }}>{slot.venture_id}</div>
          <div style={{ fontSize: 12, fontWeight: 600, color: C.fg, marginBottom: 4, lineHeight: 1.4 }}>{slot.niche || 'Pending niche'}</div>
          {slot.live_url && (
            <a href={slot.live_url} target="_blank" rel="noreferrer" style={{ fontSize: 10, color: C.accent, textDecoration: 'none', wordBreak: 'break-all' }}>{slot.live_url}</a>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
          <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 3, background: `${statusColor}22`, color: statusColor, fontFamily: 'monospace' }}>{slot.status}</span>
          {slot.mrr_usd > 0 && <span style={{ fontSize: 11, fontWeight: 700, color: C.accent }}>{usd(slot.mrr_usd)}/mo</span>}
        </div>
      </div>
    </div>
  )
}

// ─── Agent health row ─────────────────────────────────────────────────────────
function AgentHealthRow({ agent }: { agent: AgentRow }) {
  const isRunning = agent.status === 'RUNNING'
  const isFailed  = agent.status === 'FAILED'
  const color = isRunning ? C.blue : isFailed ? C.red : agent.success_ratio > 0.8 ? C.accent : C.fgMuted
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: `1px solid ${C.border}` }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%', background: color,
        flexShrink: 0, display: 'inline-block',
        boxShadow: isRunning ? `0 0 6px ${color}` : 'none',
        animation: isRunning ? 'pulse 1.2s infinite' : 'none',
      }} />
      <span style={{ flex: 1, fontSize: 11, color: C.fgMuted, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
  const [revenue,     setRevenue]     = useState<RevenueSummary | null>(null)
  const [confidence,  setConfidence]  = useState<ConfidenceReport | null>(null)
  const [agents,      setAgents]      = useState<AgentRow[]>([])
  const [slots,       setSlots]       = useState<(PortfolioSlot & { live_url?: string; niche?: string })[]>([])
  const [ventures,    setVentures]    = useState<Venture[]>([])
  const [runs,        setRuns]        = useState<PipelineRun[]>([])
  const [launching,   setLaunching]   = useState(false)
  const [launchErr,   setLaunchErr]   = useState('')
  const [apiErr,      setApiErr]      = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const [clock,       setClock]       = useState(new Date().toLocaleTimeString())

  const pollTimers = useRef(new Map<string, ReturnType<typeof setInterval>>())

  // ── Live clock — updates every second ────────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000)
    return () => clearInterval(id)
  }, [])

  // ── Poll individual run ───────────────────────────────────────────────────
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
      if (r)    setRevenue(r)
      if (conf) setConfidence(conf)
      setVentures(venRes.ventures)
      setRuns((prev: PipelineRun[]) => {
        const serverById = new Map<string, PipelineRun>(runsRes.runs.map((r: PipelineRun) => [r.run_id, r] as [string, PipelineRun]))
        const merged: PipelineRun[] = prev.map(r => serverById.get(r.run_id) ?? r)
        runsRes.runs.forEach((r: PipelineRun) => { if (!merged.find(m => m.run_id === r.run_id)) merged.unshift(r) })
        return merged.slice(0, 50)
      })
      setSlots(venRes.ventures
        .filter((v: Venture) => v.status !== 'KILLED')
        .map((v: Venture, i: number) => ({
          slot: i + 1, venture_id: v.venture_id,
          status: v.status, niche: v.niche, mrr_usd: 0,
          live_url: (v as Venture & { live_url?: string }).live_url,
        }))
      )
      setApiErr('')
    } catch {
      setApiErr('API unreachable — check Railway service is running')
    }
  }, [])

  useEffect(() => { refresh(); const id = setInterval(refresh, 30_000); return () => clearInterval(id) }, [refresh])
  useEffect(() => { runs.forEach(r => { if (r.status === 'STARTED' || r.status === 'RUNNING') pollRun(r.run_id) }) }, [runs, pollRun])

  // WebSocket live tick
  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/api/ws/live`)
    ws.onmessage = ev => {
      try { const msg = JSON.parse(ev.data); if (msg.type === 'tick' && msg.revenue) setRevenue(msg.revenue) }
      catch { /* ignore */ }
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
        department: 'PRODUCT', status: 'STARTED', current_stage: 'RESEARCH_NODE',
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
  const mrr  = revenue?.mrr_usd  ?? 0
  const burn = revenue?.burn_usd ?? 0
  const net  = revenue?.net_mrr_usd ?? 0
  const conf = confidence?.confidence_score ?? 0

  const killedIds    = new Set(ventures.filter(v => v.status === 'KILLED').map(v => v.venture_id))
  const visibleRuns  = runs.filter(r => !killedIds.has(r.venture_id))
  const activeRuns   = visibleRuns.filter(r => ['STARTED', 'RUNNING', 'MANUAL_REVIEW'].includes(r.status))
  const historyRuns  = visibleRuns.filter(r => ['COMPLETED', 'FAILED'].includes(r.status))
  const recentTwo    = historyRuns.slice(0, 2)
  const liveVentures = slots.filter(s => s.status === 'LIVE' || s.live_url)

  const confColor = conf >= 60 ? C.accent : conf >= 30 ? C.orange : C.red

  return (
    <div style={{ background: C.bg, minHeight: '100vh', color: C.fg }}>
      <style>{`
        @keyframes pulse        { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes pulse-ring   { 0%{transform:scale(1);opacity:0.6} 70%{transform:scale(1.18);opacity:0} 100%{transform:scale(1.18);opacity:0} }
        @keyframes data-packet  { 0%{left:-55%} 100%{left:155%} }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar       { width: 4px; height: 4px; }
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
        {/* Logo */}
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
            { label: 'MRR',    value: usd(mrr),              color: mrr > 0 ? C.accent : C.fgMuted },
            { label: 'BURN',   value: usd(burn),             color: C.red },
            { label: 'NET',    value: usd(net),              color: net >= 0 ? C.accent : C.red },
            { label: 'LIVE',   value: String(liveVentures.length), color: C.accent },
            { label: 'ACTIVE', value: String(activeRuns.length),   color: activeRuns.length > 0 ? C.blue : C.fgMuted },
          ].map(m => (
            <div key={m.label} style={{ padding: '0 14px', borderRight: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 9, color: C.fgDim, fontFamily: 'monospace', marginBottom: 1 }}>{m.label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: m.color, fontFamily: 'monospace' }}>{m.value}</div>
            </div>
          ))}
        </div>

        {/* Actions + live clock */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexShrink: 0 }}>
          {/* Green live clock */}
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, color: C.accent, fontFamily: 'monospace' }}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%', background: C.accent,
              display: 'inline-block', flexShrink: 0,
              boxShadow: `0 0 5px ${C.accent}`,
              animation: 'pulse 2s infinite',
            }} />
            {clock}
          </span>

          <button
            onClick={launchPipeline} disabled={launching}
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
              border: '1px solid rgba(239,68,68,0.3)',
              background: 'rgba(239,68,68,0.06)', color: C.red,
              fontSize: 11, fontWeight: 700, cursor: 'pointer',
            }}
          >
            🗑 Cleanup
          </button>
        </div>
      </div>

      {/* ── Error banners ────────────────────────────────────────────────────── */}
      {apiErr && (
        <div style={{ background: 'rgba(239,68,68,0.1)', borderBottom: '1px solid rgba(239,68,68,0.3)', padding: '10px 24px', fontSize: 12, color: C.red, fontFamily: 'monospace' }}>
          ⚠ {apiErr}
        </div>
      )}
      {launchErr && (
        <div style={{ background: 'rgba(239,68,68,0.1)', borderBottom: '1px solid rgba(239,68,68,0.3)', padding: '10px 24px', fontSize: 12, color: C.red }}>
          Launch failed: {launchErr}
        </div>
      )}

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '24px 24px 48px' }}>

        {/* ── Active Pipelines — 3D viz always visible ───────────────────────── */}
        <section style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>
              Active Pipeline
              {activeRuns.length > 0 && (
                <span style={{ marginLeft: 8, fontSize: 11, background: `${C.blue}22`, color: C.blue, padding: '2px 8px', borderRadius: 10, fontWeight: 600 }}>
                  {activeRuns.length} running
                </span>
              )}
            </h2>
            <span style={{ fontSize: 10, color: C.fgDim, fontFamily: 'monospace', letterSpacing: '0.05em' }}>
              🔍→👔→📋→📝→⚙️→🧪→🛡️→⚖️→🚀→📢→📈
            </span>
          </div>

          {/* 3D visualization — always mounted */}
          <AgentPipeline3D run={activeRuns[0] ?? null} />

          {/* Run cards below the viz */}
          {activeRuns.length > 0 ? (
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {activeRuns.map(run => (
                <ActivePipelineCard
                  key={run.run_id}
                  run={run}
                  onRefresh={refresh}
                  onKill={() => api.killVenture(run.venture_id).then(refresh).catch(() => {})}
                />
              ))}
            </div>
          ) : (
            <div style={{ marginTop: 18, textAlign: 'center', padding: '16px 0' }}>
              <div style={{ fontSize: 13, color: C.fgMuted, marginBottom: 14 }}>
                No active pipelines — launch one to start building.
              </div>
              <button
                onClick={launchPipeline} disabled={launching}
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
          )}
        </section>

        {/* ── Confidence (left) + Recent Runs (right) ────────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: '290px 1fr', gap: 20, marginBottom: 28 }}>

          {/* Confidence score card */}
          <div style={{
            background: C.panel, border: `1px solid ${C.border}`,
            borderRadius: 12, padding: '20px',
            boxShadow: conf > 0 ? `0 0 0 1px ${confColor}18` : 'none',
          }}>
            <div style={{ fontSize: 9, color: C.fgMuted, fontWeight: 700, letterSpacing: '0.14em', marginBottom: 12, fontFamily: 'monospace' }}>
              CONFIDENCE SCORE
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 6 }}>
              <span style={{ fontSize: 52, fontWeight: 900, color: confColor, fontFamily: 'monospace', lineHeight: 1 }}>
                {conf}
              </span>
              <span style={{ fontSize: 13, color: C.fgMuted }}>/100</span>
            </div>
            {confidence && (
              <div style={{ fontSize: 10, color: confColor, fontWeight: 700, marginBottom: 12, letterSpacing: '0.06em' }}>
                {confidence.confidence_tier}
              </div>
            )}
            <div style={{ background: C.border, borderRadius: 4, height: 6, overflow: 'hidden', marginBottom: 14 }}>
              <div style={{
                width: `${conf}%`, height: '100%', background: confColor,
                transition: 'width 0.8s ease',
                boxShadow: conf > 0 ? `0 0 8px ${confColor}88` : 'none',
              }} />
            </div>
            {confidence ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {([
                  ['12mo p50 MRR', usd(confidence.forecast_p50_mrr_12mo)],
                  ['QA pass rate', `${confidence.leading_indicators?.qa_first_pass_rate_pct ?? 0}%`],
                  ['Completed runs', String(confidence.leading_indicators?.completed_pipeline_runs ?? 0)],
                ] as [string, string][]).map(([label, value]) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                    <span style={{ color: C.fgDim }}>{label}</span>
                    <span style={{ color: C.fg, fontFamily: 'monospace', fontWeight: 600 }}>{value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 11, color: C.fgDim, textAlign: 'center', padding: '8px 0' }}>
                Run a pipeline to establish score
              </div>
            )}
          </div>

          {/* Recent Runs — 2 max */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>
                Recent Runs
                {historyRuns.length > 0 && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: C.fgMuted, fontWeight: 400 }}>
                    {historyRuns.length} total
                  </span>
                )}
              </h2>
              {historyRuns.length > 2 && (
                <button
                  onClick={() => setShowHistory(true)}
                  style={{
                    padding: '5px 14px', borderRadius: 6,
                    border: `1px solid ${C.border}`, background: 'none',
                    color: C.accent, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  See All ({historyRuns.length}) →
                </button>
              )}
            </div>

            {recentTwo.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {recentTwo.map(run => <HistoryRow key={run.run_id} run={run} />)}
              </div>
            ) : (
              <div style={{
                background: C.panel, border: `1px solid ${C.border}`,
                borderRadius: 10, padding: '32px 20px',
                textAlign: 'center', color: C.fgDim, fontSize: 12,
              }}>
                No completed runs yet
              </div>
            )}
          </div>
        </div>

        {/* ── Portfolio + Agent Health ──────────────────────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20 }}>

          {/* Portfolio */}
          <section>
            <h2 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>
              Portfolio
              <span style={{ marginLeft: 8, fontSize: 11, color: C.fgMuted, fontWeight: 400 }}>
                {slots.length} venture{slots.length !== 1 ? 's' : ''}
                {liveVentures.length > 0 && ` · ${liveVentures.length} live`}
              </span>
            </h2>
            {slots.length === 0 ? (
              <div style={{
                background: C.panel, border: `1px solid ${C.border}`,
                borderRadius: 10, padding: '32px 24px',
                textAlign: 'center', color: C.fgMuted, fontSize: 12,
              }}>
                No ventures yet — launch a pipeline to build your first SaaS product.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(270px,1fr))', gap: 10 }}>
                {slots.map(s => <PortfolioCard key={s.venture_id} slot={s} />)}
              </div>
            )}
          </section>

          {/* Agent Health */}
          <section>
            <h2 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>Agent Health</h2>
            <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, padding: '12px 16px' }}>
              {agents.length === 0 ? (
                <div style={{ fontSize: 11, color: C.fgDim, textAlign: 'center', padding: '20px 0' }}>
                  No agent data yet
                </div>
              ) : (
                agents.map(a => <AgentHealthRow key={a.agent_name} agent={a} />)
              )}
            </div>
          </section>
        </div>
      </div>

      {/* See All history popup */}
      {showHistory && <HistoryPopup runs={historyRuns} onClose={() => setShowHistory(false)} />}
    </div>
  )
}
