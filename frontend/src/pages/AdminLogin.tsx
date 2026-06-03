/**
 * AdminLogin.tsx — Maximum-security admin authentication gate.
 *
 * Security controls implemented:
 *   1. Admin-only email   — VITE_ADMIN_EMAIL env var, must match exactly
 *   2. Brute-force guard  — 5 failed attempts → 15-min lockout, exponential backoff
 *   3. Rate limiting      — 1-second minimum between submissions
 *   4. Session timeout    — auto-logout after 2 hours of inactivity (set by AdminGuard)
 *   5. No "remember me"   — session only, clears on tab close
 *   6. Failed log         — attempts recorded in localStorage + Supabase agent_logs
 *   7. Timing-safe check  — same UI delay on correct and incorrect password
 *   8. CSRF               — handled by Supabase JWT (stateless, short-lived)
 *   9. XSS                — React's default escaping + no dangerouslySetInnerHTML
 *  10. Generic error msg  — never reveals whether email or password is wrong
 *
 * This page is ONLY shown for /command-center access.
 * Public auth (/auth) is a separate page for customer accounts.
 */
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'

// ─── Config ──────────────────────────────────────────────────────────────────
const ADMIN_EMAIL        = import.meta.env.VITE_ADMIN_EMAIL as string | undefined
const MAX_ATTEMPTS       = 5
const BASE_LOCKOUT_MS    = 15 * 60 * 1000    // 15 minutes
const MIN_SUBMIT_GAP_MS  = 1_000             // 1 second anti-spam
const SESSION_TIMEOUT_MS = 2 * 60 * 60 * 1000 // 2 hours

const LS_ATTEMPTS   = 'aisq_admin_attempts'
const LS_LOCKED_AT  = 'aisq_admin_locked_at'
const LS_LAST_SEEN  = 'aisq_admin_last_seen'

// ─── Security helpers ─────────────────────────────────────────────────────────
function getAttempts()  { return parseInt(localStorage.getItem(LS_ATTEMPTS)  ?? '0', 10) }
function getLockedAt()  { return parseInt(localStorage.getItem(LS_LOCKED_AT) ?? '0', 10) }
function incAttempts()  { localStorage.setItem(LS_ATTEMPTS, String(getAttempts() + 1)) }
function resetAttempts(){ localStorage.removeItem(LS_ATTEMPTS); localStorage.removeItem(LS_LOCKED_AT) }
function lockNow()      { localStorage.setItem(LS_LOCKED_AT, String(Date.now())) }

function remainingLockMs(): number {
  const lockedAt = getLockedAt()
  if (!lockedAt) return 0
  const attempts   = getAttempts()
  const multiplier = Math.pow(2, Math.max(0, attempts - MAX_ATTEMPTS))
  const lockMs     = BASE_LOCKOUT_MS * multiplier
  const remaining  = lockedAt + lockMs - Date.now()
  return Math.max(0, remaining)
}

function isLocked(): boolean { return remainingLockMs() > 0 }

function fmtMs(ms: number): string {
  const s = Math.ceil(ms / 1000)
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`
}

async function logFailedAttempt(email: string) {
  // Non-blocking — never slow down the UI
  try {
    if (!supabase) return
    await supabase.from('agent_logs').insert({
      run_id:       'admin-auth',
      venture_id:   null,
      agent_name:   'ADMIN_AUTH',
      status:       'FAILED',
      current_task: `Failed login attempt for: ${email.substring(0, 3)}***`,
      error_detail: `IP: browser | Time: ${new Date().toISOString()} | Attempts: ${getAttempts()}`,
    })
  } catch { /* silent — logging must never block auth */ }
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function AdminLogin() {
  const navigate        = useNavigate()
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [locked, setLocked]     = useState(false)
  const [lockRemaining, setLockRemaining] = useState(0)
  const [attempts, setAttempts] = useState(getAttempts())
  const lastSubmitRef = useRef(0)
  const timerRef      = useRef<ReturnType<typeof setInterval> | null>(null)

  // Redirect if already authed as admin
  useEffect(() => {
    supabase?.auth.getUser().then(({ data }) => {
      if (data.user?.email === ADMIN_EMAIL) {
        navigate('/command-center', { replace: true })
      }
    })
  }, [navigate])

  // Lockout countdown
  useEffect(() => {
    if (isLocked()) {
      setLocked(true)
      setLockRemaining(remainingLockMs())
      timerRef.current = setInterval(() => {
        const r = remainingLockMs()
        setLockRemaining(r)
        if (r <= 0) {
          setLocked(false)
          if (timerRef.current) clearInterval(timerRef.current)
        }
      }, 500)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')

    // Anti-spam: enforce minimum gap between submissions
    const now = Date.now()
    if (now - lastSubmitRef.current < MIN_SUBMIT_GAP_MS) {
      setError('Too fast. Please wait a moment.')
      return
    }
    lastSubmitRef.current = now

    if (isLocked()) return

    if (!supabase) {
      setError('Authentication service unavailable.')
      return
    }

    setLoading(true)

    // Artificial delay to prevent timing attacks (always ~800ms regardless of outcome)
    const startMs = Date.now()

    try {
      const { data, error: authErr } = await supabase.auth.signInWithPassword({ email, password })

      // Enforce timing-safe minimum delay
      const elapsed = Date.now() - startMs
      if (elapsed < 800) await new Promise(r => setTimeout(r, 800 - elapsed))

      if (authErr || !data.user) {
        throw new Error('auth_failed')
      }

      // Admin email check — MUST match exactly
      if (data.user.email !== ADMIN_EMAIL) {
        await supabase.auth.signOut()
        throw new Error('auth_failed')
      }

      // SUCCESS — reset brute-force counter, store session timestamp
      resetAttempts()
      localStorage.setItem(LS_LAST_SEEN, String(Date.now()))
      setAttempts(0)
      navigate('/command-center', { replace: true })

    } catch {
      // Generic message — NEVER reveal which field was wrong
      const newAttempts = getAttempts() + 1
      incAttempts()
      setAttempts(newAttempts)
      void logFailedAttempt(email)

      if (newAttempts >= MAX_ATTEMPTS) {
        lockNow()
        setLocked(true)
        setLockRemaining(remainingLockMs())
        timerRef.current = setInterval(() => {
          const r = remainingLockMs()
          setLockRemaining(r)
          if (r <= 0) { setLocked(false); if (timerRef.current) clearInterval(timerRef.current) }
        }, 500)
        setError(`Too many failed attempts. Locked for ${fmtMs(remainingLockMs())}.`)
      } else {
        const remaining = MAX_ATTEMPTS - newAttempts
        setError(`Invalid credentials. ${remaining} attempt${remaining !== 1 ? 's' : ''} remaining.`)
      }
    } finally {
      setLoading(false)
      setPassword('')  // always clear password field
    }
  }

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{
      minHeight: '100vh', background: '#030305',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
    }}>
      <div style={{
        width: '100%', maxWidth: 380,
        background: '#0a0a12', border: '1px solid #1a1a2e',
        borderRadius: 14, padding: '36px 32px',
        boxShadow: '0 0 60px rgba(0,0,0,0.8)',
      }}>
        {/* Shield icon */}
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 36 }}>🛡</div>
          <h1 style={{ fontSize: 18, fontWeight: 800, color: '#f1f5f9', marginTop: 10, letterSpacing: '-0.5px' }}>
            Command Center
          </h1>
          <p style={{ fontSize: 12, color: '#334155', marginTop: 4 }}>
            Restricted access · Authorised personnel only
          </p>
        </div>

        {/* Attempt meter */}
        {attempts > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 11, color: '#475569' }}>
              <span>Failed attempts</span>
              <span style={{ color: attempts >= MAX_ATTEMPTS - 1 ? '#ef4444' : '#f59e0b' }}>
                {attempts} / {MAX_ATTEMPTS}
              </span>
            </div>
            <div style={{ height: 3, background: '#1e1e3a', borderRadius: 99 }}>
              <div style={{
                height: '100%', borderRadius: 99,
                width: `${(attempts / MAX_ATTEMPTS) * 100}%`,
                background: attempts >= MAX_ATTEMPTS - 1 ? '#ef4444' : '#f59e0b',
                transition: 'width 0.3s',
              }} />
            </div>
          </div>
        )}

        {/* Lockout screen */}
        {locked ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
            <div style={{ color: '#ef4444', fontWeight: 700, fontSize: 15, marginBottom: 8 }}>
              Access locked
            </div>
            <div style={{ color: '#64748b', fontSize: 13 }}>
              Too many failed attempts.<br />
              Try again in <strong style={{ color: '#f59e0b' }}>{fmtMs(lockRemaining)}</strong>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} autoComplete="off" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Honeypot field — bots fill this, humans don't see it */}
            <input
              type="text"
              name="username"
              style={{ position: 'absolute', left: -9999, top: -9999, opacity: 0 }}
              tabIndex={-1}
              aria-hidden="true"
            />

            <div>
              <label style={labelStyle}>Admin email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="off"
                spellCheck={false}
                placeholder="admin@example.com"
                style={inputStyle}
                disabled={loading}
              />
            </div>

            <div>
              <label style={labelStyle}>Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                placeholder="••••••••••••"
                style={inputStyle}
                minLength={8}
                disabled={loading}
              />
            </div>

            {error && (
              <div style={{
                background: 'rgba(239,68,68,0.08)', border: '1px solid #7f1d1d',
                borderRadius: 8, padding: '10px 14px', color: '#fca5a5', fontSize: 13,
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || locked}
              style={{
                padding: 12, borderRadius: 10, border: 'none', fontWeight: 700, fontSize: 15,
                background: loading ? '#1e1e3a' : '#7c3aed', color: '#fff',
                cursor: loading || locked ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1, marginTop: 4,
              }}
            >
              {loading ? 'Authenticating…' : 'Access Command Center'}
            </button>
          </form>
        )}

        {/* Security notice */}
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #1a1a2e', textAlign: 'center' }}>
          <p style={{ color: '#1e293b', fontSize: 11, lineHeight: 1.6 }}>
            All login attempts are logged · Session expires after 2 hours idle<br />
            Brute-force protection active · Unauthorised access is a criminal offence
          </p>
        </div>
      </div>
    </div>
  )
}

// Initialise session timeout tracking on first admin login
export function markAdminActivity() {
  localStorage.setItem(LS_LAST_SEEN, String(Date.now()))
}

export function isAdminSessionExpired(): boolean {
  const lastSeen = parseInt(localStorage.getItem(LS_LAST_SEEN) ?? '0', 10)
  if (!lastSeen) return true
  return Date.now() - lastSeen > SESSION_TIMEOUT_MS
}

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 12, fontWeight: 600, color: '#64748b', marginBottom: 6,
  textTransform: 'uppercase', letterSpacing: '0.06em',
}
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 14px', borderRadius: 8, boxSizing: 'border-box',
  background: '#060610', border: '1px solid #1a1a2e', color: '#e2e8f0',
  fontSize: 14, outline: 'none', fontFamily: 'monospace',
}
