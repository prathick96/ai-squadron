import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { supabase } from '../lib/supabase'

const ADMIN_EMAIL = import.meta.env.VITE_ADMIN_EMAIL as string | undefined

export default function Auth() {
  const navigate   = useNavigate()
  const [params]   = useSearchParams()
  const mode       = params.get('mode') === 'signup' ? 'signup' : 'login'

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const [sent,     setSent]     = useState(false)

  // Redirect if already logged in
  useEffect(() => {
    supabase?.auth.getUser().then(({ data }) => {
      if (!data.user) return
      if (data.user.email === ADMIN_EMAIL) {
        navigate('/command-center', { replace: true })
      } else {
        navigate('/dashboard', { replace: true })
      }
    })
  }, [navigate])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!supabase) { setError('Database not connected. Contact support.'); return }
    setError(''); setLoading(true)

    try {
      if (mode === 'signup') {
        const { error: err } = await supabase.auth.signUp({ email, password })
        if (err) throw err
        setSent(true)
      } else {
        const { data, error: err } = await supabase.auth.signInWithPassword({ email, password })
        if (err) throw err
        // Admin → Command Center; new users → onboarding; returning users → dashboard
        if (data.user?.email === ADMIN_EMAIL) {
          navigate('/command-center', { replace: true })
        } else {
          // Check if user has completed onboarding
          const { data: profile } = await supabase.from('user_profiles').select('onboarding_done').eq('id', data.user!.id).single()
          if (profile?.onboarding_done) {
            navigate('/dashboard', { replace: true })
          } else {
            navigate('/onboarding', { replace: true })
          }
        }
      }
    } catch (err: unknown) {
      setError((err as { message?: string }).message ?? 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div style={pageStyle}>
        <div style={cardStyle}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📧</div>
          <h2 style={headingStyle}>Check your email</h2>
          <p style={subStyle}>
            We sent a confirmation link to <strong>{email}</strong>.
            Click it to activate your account, then come back to log in.
          </p>
          <Link to="/auth?mode=login" style={btnPrimary}>Go to login →</Link>
        </div>
      </div>
    )
  }

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <Link to="/" style={{ textDecoration: 'none' }}>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#7c3aed', marginBottom: 28, textAlign: 'center' }}>
            AI Squadron
          </div>
        </Link>

        <h1 style={headingStyle}>
          {mode === 'signup' ? 'Create your account' : 'Welcome back'}
        </h1>
        <p style={{ ...subStyle, marginBottom: 28, textAlign: 'center' }}>
          {mode === 'signup' ? 'Start your first venture today.' : 'Sign in to manage your ventures.'}
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={labelStyle}>Email address</label>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              required placeholder="you@example.com" style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Password</label>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              required placeholder="••••••••" style={inputStyle} minLength={8}
            />
          </div>

          {error && (
            <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #7f1d1d', borderRadius: 8, padding: '10px 14px', color: '#fca5a5', fontSize: 13 }}>
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} style={{ ...btnPrimary, border: 'none', cursor: loading ? 'wait' : 'pointer', opacity: loading ? 0.7 : 1 }}>
            {loading ? 'Please wait…' : mode === 'signup' ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <p style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: '#475569' }}>
          {mode === 'signup' ? 'Already have an account? ' : "Don't have an account? "}
          <Link
            to={`/auth?mode=${mode === 'signup' ? 'login' : 'signup'}`}
            style={{ color: '#7c3aed', textDecoration: 'none', fontWeight: 600 }}
          >
            {mode === 'signup' ? 'Sign in' : 'Create one'}
          </Link>
        </p>

        {/* Legal notice */}
        <p style={{ textAlign: 'center', marginTop: 20, fontSize: 11, color: '#334155', lineHeight: 1.6 }}>
          By continuing you agree to our{' '}
          <Link to="/legal/terms" style={{ color: '#64748b', textDecoration: 'underline' }}>Terms of Service</Link>
          {' '}and{' '}
          <Link to="/legal/privacy" style={{ color: '#64748b', textDecoration: 'underline' }}>Privacy Policy</Link>.
        </p>
      </div>
    </div>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const pageStyle: React.CSSProperties = {
  minHeight: '100vh', background: '#080810',
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
}
const cardStyle: React.CSSProperties = {
  width: '100%', maxWidth: 420,
  background: '#0f0f1a', border: '1px solid #1e1e3a',
  borderRadius: 16, padding: 40,
}
const headingStyle: React.CSSProperties = {
  fontSize: 24, fontWeight: 800, color: '#f1f5f9',
  textAlign: 'center', marginBottom: 8, letterSpacing: '-0.5px',
}
const subStyle: React.CSSProperties = { color: '#64748b', fontSize: 14, lineHeight: 1.6 }
const labelStyle: React.CSSProperties = { display: 'block', fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 6 }
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 14px', borderRadius: 8,
  background: '#080810', border: '1px solid #1e1e3a',
  color: '#e2e8f0', fontSize: 14, outline: 'none', boxSizing: 'border-box',
}
const btnPrimary: React.CSSProperties = {
  display: 'block', textAlign: 'center', width: '100%',
  padding: '12px', background: '#7c3aed', color: '#fff',
  borderRadius: 10, fontWeight: 700, fontSize: 15, textDecoration: 'none',
}
