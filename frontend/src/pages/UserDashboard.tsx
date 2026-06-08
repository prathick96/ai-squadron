/**
 * UserDashboard.tsx — Customer-facing dashboard for AI Squadron users.
 *
 * Shows:
 *  - Plan badge + monthly run counter (free tier: 1/month)
 *  - "Launch Venture" CTA (disabled when limit reached)
 *  - Pipeline runs in progress (live polling)
 *  - Completed ventures with Download + Deploy buttons
 *
 * Route: /dashboard  (customers only, admin goes to /command-center)
 */
import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'

// ─── Types ─────────────────────────────────────────────────────────────────
interface UserProfile {
  user_id: string; email: string; plan: string
  runs_used: number; runs_limit: number; runs_remaining: number; unlimited: boolean
  onboarding_done: boolean
}

interface Venture {
  run_id: string; venture_id: string; status: string
  current_stage: string; started_at: string; completed_at: string | null
  department: string; niche: string; live_url: string | null; venture_type: string
}

const PLAN_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  starter: { label: 'Starter (Free)', color: '#64748b', bg: '#1e293b' },
  builder: { label: 'Builder',         color: '#7c3aed', bg: '#1a0a2e' },
  studio:  { label: 'Studio',          color: '#3ecf8e', bg: '#0a1f18' },
}

const API = import.meta.env.VITE_API_URL ?? ''

export default function UserDashboard() {
  const navigate = useNavigate()
  const [profile, setProfile]   = useState<UserProfile | null>(null)
  const [ventures, setVentures] = useState<Venture[]>([])
  const [loading, setLoading]   = useState(true)
  const [launching, setLaunching] = useState(false)
  const [launchErr, setLaunchErr] = useState('')
  const [deployState, setDeployState] = useState<Record<string, { loading: boolean; url?: string; err?: string }>>({})

  // Get Supabase JWT for API calls
  const getJwt = useCallback(async () => {
    const { data } = await (supabase?.auth.getSession() ?? Promise.resolve({ data: { session: null } }))
    return data.session?.access_token ?? ''
  }, [])

  const fetchData = useCallback(async () => {
    const jwt = await getJwt()
    if (!jwt) { navigate('/auth?mode=login', { replace: true }); return }
    try {
      const [pRes, vRes] = await Promise.all([
        fetch(`${API}/api/user/profile`, { headers: { Authorization: `Bearer ${jwt}` } }),
        fetch(`${API}/api/user/ventures`, { headers: { Authorization: `Bearer ${jwt}` } }),
      ])
      if (!pRes.ok) throw new Error('Session expired')
      setProfile(await pRes.json())
      const vData = await vRes.json()
      setVentures(vData.ventures ?? [])
    } catch {
      navigate('/auth?mode=login', { replace: true })
    } finally {
      setLoading(false)
    }
  }, [getJwt, navigate])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 8000)  // live refresh
    return () => clearInterval(id)
  }, [fetchData])

  async function launchVenture() {
    setLaunching(true); setLaunchErr('')
    const jwt = await getJwt()
    try {
      const res = await fetch(`${API}/api/pipeline/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwt}` },
        body: JSON.stringify({ department: 'PRODUCT' }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? `Error ${res.status}`)
      await fetchData()
    } catch (e) {
      setLaunchErr(e instanceof Error ? e.message : 'Launch failed')
    } finally {
      setLaunching(false)
    }
  }

  async function deployVenture(ventureId: string) {
    setDeployState(p => ({ ...p, [ventureId]: { loading: true } }))
    const jwt = await getJwt()
    try {
      const res = await fetch(`${API}/api/ventures/${encodeURIComponent(ventureId)}/deploy`, {
        method: 'POST', headers: { Authorization: `Bearer ${jwt}` },
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? `Deploy error ${res.status}`)
      setDeployState(p => ({ ...p, [ventureId]: { loading: false, url: data.url } }))
      await fetchData()
    } catch (e) {
      setDeployState(p => ({ ...p, [ventureId]: { loading: false, err: e instanceof Error ? e.message : 'Deploy failed' } }))
    }
  }

  async function signOut() {
    await supabase?.auth.signOut()
    navigate('/')
  }

  if (loading) {
    return (
      <div style={{ background: '#080810', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: '#475569', fontFamily: 'monospace', fontSize: 13 }}>Loading your ventures…</div>
      </div>
    )
  }

  const plan     = profile?.plan ?? 'starter'
  const planInfo = PLAN_LABELS[plan] ?? PLAN_LABELS.starter
  const canLaunch = profile?.unlimited || (profile?.runs_remaining ?? 0) > 0
  const active   = ventures.filter(v => ['STARTED', 'RUNNING'].includes(v.status))
  const done     = ventures.filter(v => v.status === 'COMPLETED')
  const failed   = ventures.filter(v => ['FAILED', 'MANUAL_REVIEW'].includes(v.status))

  return (
    <div style={{ background: '#080810', minHeight: '100vh', color: '#e2e8f0', padding: '40px 24px' }}>
      <div style={{ maxWidth: 960, margin: '0 auto' }}>

        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 40, flexWrap: 'wrap', gap: 16 }}>
          <div>
            <Link to="/" style={{ fontWeight: 800, fontSize: 20, color: '#7c3aed', textDecoration: 'none' }}>
              AI Squadron
            </Link>
            <p style={{ color: '#64748b', fontSize: 13, marginTop: 4 }}>{profile?.email}</p>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <span style={{ padding: '4px 12px', borderRadius: 99, background: planInfo.bg, color: planInfo.color, fontSize: 12, fontWeight: 700, border: `1px solid ${planInfo.color}33` }}>
              {planInfo.label}
            </span>
            {plan === 'starter' && (
              <Link to="/pricing" style={{ fontSize: 12, color: '#3ecf8e', textDecoration: 'none', fontWeight: 600 }}>
                Upgrade →
              </Link>
            )}
            <button onClick={signOut} style={{ fontSize: 12, color: '#475569', background: 'none', border: 'none', cursor: 'pointer' }}>
              Sign out
            </button>
          </div>
        </div>

        {/* ── Plan usage bar ────────────────────────────────────────────── */}
        <div style={{ background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 12, padding: 24, marginBottom: 28 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontWeight: 700, color: '#e2e8f0' }}>Pipeline runs this month</span>
            <span style={{ fontFamily: 'monospace', fontSize: 13, color: '#64748b' }}>
              {profile?.unlimited ? '∞ unlimited' : `${profile?.runs_used ?? 0} / ${profile?.runs_limit ?? 1}`}
            </span>
          </div>
          {!profile?.unlimited && (
            <div style={{ height: 6, background: '#1e1e3a', borderRadius: 99 }}>
              <div style={{
                height: '100%', borderRadius: 99,
                width: `${Math.min(100, ((profile?.runs_used ?? 0) / (profile?.runs_limit ?? 1)) * 100)}%`,
                background: canLaunch ? '#7c3aed' : '#ef4444',
                transition: 'width 0.4s',
              }} />
            </div>
          )}
          {!canLaunch && (
            <p style={{ fontSize: 12, color: '#ef4444', marginTop: 8 }}>
              Monthly limit reached. <Link to="/pricing" style={{ color: '#3ecf8e', textDecoration: 'none' }}>Upgrade to Builder →</Link>
            </p>
          )}
        </div>

        {/* ── Launch CTA ───────────────────────────────────────────────── */}
        <div style={{ marginBottom: 40 }}>
          <button
            onClick={launchVenture}
            disabled={!canLaunch || launching}
            style={{
              padding: '14px 32px', borderRadius: 10, border: 'none',
              background: canLaunch && !launching ? 'linear-gradient(135deg,#7c3aed,#6d28d9)' : '#1e1e3a',
              color: canLaunch && !launching ? '#fff' : '#475569',
              fontWeight: 800, fontSize: 16, cursor: canLaunch && !launching ? 'pointer' : 'not-allowed',
              boxShadow: canLaunch && !launching ? '0 0 20px rgba(124,58,237,0.3)' : 'none',
            }}
          >
            {launching ? '⏳ Launching…' : '🚀 Launch New Venture'}
          </button>
          <p style={{ fontSize: 12, color: '#334155', marginTop: 8 }}>
            AI agents research a niche, build a React SaaS app, and deploy it — all automatically.
          </p>
          {launchErr && <p style={{ fontSize: 12, color: '#ef4444', marginTop: 6 }}>⚠ {launchErr}</p>}
        </div>

        {/* ── Active runs ──────────────────────────────────────────────── */}
        {active.length > 0 && (
          <section style={{ marginBottom: 40 }}>
            <h2 style={sectionHead}>Building now</h2>
            {active.map(v => <RunCard key={v.run_id} venture={v} />)}
          </section>
        )}

        {/* ── Completed ventures ────────────────────────────────────────── */}
        {done.length > 0 && (
          <section style={{ marginBottom: 40 }}>
            <h2 style={sectionHead}>Your ventures</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 16 }}>
              {done.map(v => {
                const ds = deployState[v.venture_id]
                const liveUrl = ds?.url || v.live_url
                return (
                  <div key={v.run_id} style={{ background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 12, padding: 24 }}>
                    <div style={{ fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                      {v.venture_type?.replace(/_/g, ' ') ?? 'MICRO SAAS'}
                    </div>
                    <h3 style={{ fontWeight: 700, fontSize: 15, color: '#e2e8f0', marginBottom: 8 }}>
                      {v.niche || 'AI Tool'}
                    </h3>
                    <div style={{ fontSize: 11, color: '#334155', marginBottom: 16, fontFamily: 'monospace' }}>
                      {v.venture_id}
                    </div>

                    {liveUrl ? (
                      <a href={liveUrl} target="_blank" rel="noreferrer" style={{
                        display: 'block', padding: '8px 16px', background: 'linear-gradient(135deg,#166534,#14532d)',
                        border: '1px solid #4ade80', color: '#4ade80', borderRadius: 8,
                        textDecoration: 'none', fontWeight: 700, fontSize: 13, marginBottom: 8,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        🟢 View live app →
                      </a>
                    ) : (
                      <button
                        onClick={() => deployVenture(v.venture_id)}
                        disabled={ds?.loading}
                        style={{
                          display: 'block', width: '100%', padding: '8px 16px',
                          background: ds?.loading ? '#1e1e3a' : '#7c3aed',
                          color: ds?.loading ? '#475569' : '#fff', border: 'none',
                          borderRadius: 8, fontWeight: 700, fontSize: 13, cursor: ds?.loading ? 'wait' : 'pointer',
                          marginBottom: 8,
                        }}
                      >
                        {ds?.loading ? '⏳ Deploying…' : '🚀 Deploy to Railway'}
                      </button>
                    )}

                    {ds?.err && <p style={{ fontSize: 11, color: '#ef4444', marginBottom: 8 }}>⚠ {ds.err}</p>}

                    <div style={{ display: 'flex', gap: 8 }}>
                      <a href={`${API}/api/builds/${v.venture_id}`} target="_blank" rel="noreferrer"
                        style={{ fontSize: 11, color: '#64748b', textDecoration: 'none' }}>📁 Files</a>
                      <a href={`${API}/api/builds/${v.venture_id}/download`}
                        style={{ fontSize: 11, color: '#64748b', textDecoration: 'none' }}>⬇ Download</a>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* ── Failed / manual review ─────────────────────────────────── */}
        {failed.length > 0 && (
          <section style={{ marginBottom: 40 }}>
            <h2 style={sectionHead}>Needs attention</h2>
            {failed.map(v => (
              <div key={v.run_id} style={{ background: '#0f0f1a', border: '1px solid #7f1d1d', borderRadius: 8, padding: 16, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#fca5a5' }}>{v.venture_id}</span>
                  <span style={{ fontSize: 11, color: '#ef4444', marginLeft: 12 }}>{v.status}</span>
                </div>
                <button onClick={launchVenture} style={{ fontSize: 12, padding: '4px 12px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
                  Retry
                </button>
              </div>
            ))}
          </section>
        )}

        {/* ── Empty state ────────────────────────────────────────────── */}
        {ventures.length === 0 && !launching && (
          <div style={{ textAlign: 'center', padding: '60px 24px', color: '#334155' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🤖</div>
            <h3 style={{ color: '#64748b', marginBottom: 8 }}>No ventures yet</h3>
            <p style={{ fontSize: 14 }}>Click "Launch New Venture" and AI agents will research a niche, build a product, and deploy it for you.</p>
          </div>
        )}

      </div>
    </div>
  )
}

function RunCard({ venture: v }: { venture: Venture }) {
  const STAGES = ['RESEARCH','CEO','PRODUCT_VP','PRODUCT_MANAGER','ENGINEERING','QA_TECHNICAL','SECURITY','LEGAL','DEPLOYMENT','MARKETING_SEO','PRODUCT_GROWTH']
  const stage = v.current_stage.replace(/_NODE$/, '').replace(/_/g, ' ')
  const idx   = STAGES.findIndex(s => v.current_stage.includes(s))
  const pct   = idx >= 0 ? Math.round(((idx + 1) / STAGES.length) * 100) : 5

  return (
    <div style={{ background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 10, padding: '14px 18px', marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#64748b' }}>{v.venture_id}</span>
        <span style={{ fontSize: 11, color: '#4af', fontFamily: 'monospace', fontWeight: 700 }}>● RUNNING</span>
      </div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>{stage} — {pct}%</div>
      <div style={{ height: 4, background: '#1e1e3a', borderRadius: 99 }}>
        <div style={{ height: '100%', borderRadius: 99, width: `${pct}%`, background: '#7c3aed', transition: 'width 0.4s' }} />
      </div>
    </div>
  )
}

const sectionHead: React.CSSProperties = {
  fontSize: 18, fontWeight: 700, color: '#e2e8f0', marginBottom: 16, letterSpacing: '-0.5px',
}
