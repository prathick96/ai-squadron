/**
 * Onboarding wizard — shown after a user's first login.
 * Walks them through connecting Supabase and deploying to Railway.
 * Automatically marks onboarding_done=true in user_profiles when complete.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'

const STEPS = [
  { id: 1, label: 'Account ready',      icon: '✅' },
  { id: 2, label: 'Get Supabase keys',  icon: '🔑' },
  { id: 3, label: 'Deploy to Railway',  icon: '🚂' },
  { id: 4, label: 'Your app is live!',  icon: '🎉' },
]

export default function Onboarding() {
  const navigate  = useNavigate()
  const [step, setStep] = useState(1)
  const [copied, setCopied]  = useState('')

  async function finish() {
    const { data: { user } } = await (supabase?.auth.getUser() ?? Promise.resolve({ data: { user: null } }))
    if (user && supabase) {
      await supabase.from('user_profiles').update({ onboarding_done: true }).eq('id', user.id)
    }
    navigate('/dashboard')
  }

  function copy(text: string, key: string) {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(''), 2000)
  }

  return (
    <div style={{ background: '#080810', minHeight: '100vh', color: '#e2e8f0', padding: '60px 24px' }}>
      <div style={{ maxWidth: 680, margin: '0 auto' }}>

        {/* Progress bar */}
        <div style={{ marginBottom: 48 }}>
          <div style={{ display: 'flex', gap: 0, marginBottom: 12 }}>
            {STEPS.map((s, i) => (
              <div key={s.id} style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 700,
                  background: step >= s.id ? '#7c3aed' : '#1e1e3a',
                  color: step >= s.id ? '#fff' : '#475569',
                  transition: 'background 0.3s',
                }}>
                  {step > s.id ? '✓' : s.id}
                </div>
                {i < STEPS.length - 1 && (
                  <div style={{ flex: 1, height: 2, background: step > s.id ? '#7c3aed' : '#1e1e3a', transition: 'background 0.3s' }} />
                )}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            {STEPS.map((s) => (
              <div key={s.id} style={{ fontSize: 11, color: step >= s.id ? '#a78bfa' : '#475569', textAlign: 'center', flex: 1 }}>
                {s.label}
              </div>
            ))}
          </div>
        </div>

        {/* Step content */}
        <div style={{ background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 16, padding: 40 }}>

          {step === 1 && (
            <>
              <div style={{ fontSize: 48, marginBottom: 20 }}>✅</div>
              <h1 style={H1}>Your account is ready!</h1>
              <p style={P}>
                Welcome to AI Squadron. This quick setup connects your account to Supabase (your database)
                and Railway (where your generated apps deploy). Takes about 5 minutes.
              </p>
              <div style={{ background: '#080810', border: '1px solid #1e1e3a', borderRadius: 10, padding: 20, marginBottom: 28 }}>
                <div style={{ fontWeight: 700, color: '#a78bfa', marginBottom: 12 }}>What you'll get:</div>
                {['Your own database for your generated SaaS products', 'Live Railway deployments at a real HTTPS URL', 'Customer login + subscription management via Paddle', 'Full control — your accounts, your data, your revenue'].map(item => (
                  <div key={item} style={{ display: 'flex', gap: 10, marginBottom: 8, color: '#94a3b8', fontSize: 14 }}>
                    <span style={{ color: '#3ecf8e', flexShrink: 0 }}>✓</span> {item}
                  </div>
                ))}
              </div>
              <Button onClick={() => setStep(2)}>Let's set up your database →</Button>
            </>
          )}

          {step === 2 && (
            <>
              <div style={{ fontSize: 48, marginBottom: 20 }}>🔑</div>
              <h1 style={H1}>Create your Supabase project</h1>
              <p style={P}>
                Supabase gives you a free PostgreSQL database, authentication, and storage.
                Your generated apps will connect to it automatically.
              </p>
              <Step n="1" title="Create a free account">
                <p style={P}>Go to <a href="https://supabase.com" target="_blank" rel="noreferrer" style={LINK}>supabase.com</a> → click <strong style={{ color: '#e2e8f0' }}>Start your project</strong> → sign in with GitHub.</p>
              </Step>
              <Step n="2" title="Create a new project">
                <p style={P}>Click <strong style={{ color: '#e2e8f0' }}>New Project</strong>. Give it a name (e.g., "my-saas-app"). Choose the region nearest to your users. Set a database password (save it somewhere safe).</p>
              </Step>
              <Step n="3" title="Copy your API keys">
                <p style={{ ...P, marginBottom: 12 }}>
                  In your project dashboard: go to <strong style={{ color: '#e2e8f0' }}>Settings → API</strong>.
                  You need two values:
                </p>
                <CodeBlock label="Project URL" value="https://xxxxxxxxxxxx.supabase.co" copyKey="url" copied={copied} onCopy={copy} />
                <CodeBlock label="anon / public key" value="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." copyKey="key" copied={copied} onCopy={copy} note="Use the anon key (not the service_role key) for the frontend." />
              </Step>
              <div style={{ display: 'flex', gap: 12 }}>
                <Button variant="ghost" onClick={() => setStep(1)}>← Back</Button>
                <Button onClick={() => setStep(3)}>I have my keys →</Button>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <div style={{ fontSize: 48, marginBottom: 20 }}>🚂</div>
              <h1 style={H1}>Deploy your app to Railway</h1>
              <p style={P}>
                Railway is a cloud platform that hosts your generated apps with zero devops.
                Free hobby tier, automatic HTTPS, custom domains.
              </p>
              <Step n="1" title="Create a Railway account">
                <p style={P}>Go to <a href="https://railway.app" target="_blank" rel="noreferrer" style={LINK}>railway.app</a> → sign in with GitHub → it's free to start.</p>
              </Step>
              <Step n="2" title="Download your app code">
                <p style={P}>From the AI Squadron dashboard, find your completed product run and click <strong style={{ color: '#e2e8f0' }}>⬇ Download ZIP</strong>. Extract it on your computer.</p>
              </Step>
              <Step n="3" title="Deploy via Railway CLI">
                <p style={{ ...P, marginBottom: 8 }}>In your terminal, inside the extracted folder:</p>
                <pre style={CODE}>
{`npm install -g @railway/cli   # install once
railway login                 # opens browser auth
railway init                  # creates a Railway project
railway up                    # deploys your app!`}
                </pre>
              </Step>
              <Step n="4" title="Set your environment variables">
                <p style={{ ...P, marginBottom: 8 }}>In Railway dashboard → your service → <strong style={{ color: '#e2e8f0' }}>Variables</strong>. Add these:</p>
                <pre style={CODE}>
{`VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGci...
PORT=3000`}
                </pre>
                <p style={{ ...P, marginTop: 8, fontSize: 13 }}>Railway redeploys automatically after you save variables.</p>
              </Step>
              <Step n="5" title="Your app goes live">
                <p style={P}>Railway gives you a URL like <code style={{ color: '#a78bfa' }}>https://your-app.up.railway.app</code>. Visit it — you'll see the Supabase setup screen, which disappears once the env vars are set.</p>
              </Step>
              <div style={{ display: 'flex', gap: 12 }}>
                <Button variant="ghost" onClick={() => setStep(2)}>← Back</Button>
                <Button onClick={() => setStep(4)}>My app is deployed →</Button>
              </div>
            </>
          )}

          {step === 4 && (
            <>
              <div style={{ fontSize: 64, marginBottom: 20, textAlign: 'center' }}>🎉</div>
              <h1 style={{ ...H1, textAlign: 'center' }}>You're all set!</h1>
              <p style={{ ...P, textAlign: 'center' }}>
                Your app is live on Railway, connected to Supabase, and ready for customers.
                Here's what happens next:
              </p>
              <div style={{ display: 'grid', gap: 12, margin: '24px 0 32px' }}>
                {[
                  { icon: '💳', title: 'Add Paddle checkout', desc: 'Set up Paddle products and connect VITE_PADDLE_*_PRICE_ID in Railway to activate the pricing page.' },
                  { icon: '📊', title: 'Track growth with PostHog', desc: 'Set VITE_POSTHOG_KEY in Railway to automatically track signups, pageviews, and conversions.' },
                  { icon: '🚀', title: 'Launch your next venture', desc: 'Go back to the dashboard and hit "Launch New Venture" to build your second product — both Product and Media pipelines available.' },
                ].map(({ icon, title, desc }) => (
                  <div key={title} style={{ background: '#080810', border: '1px solid #1e1e3a', borderRadius: 10, padding: 20, display: 'flex', gap: 16 }}>
                    <span style={{ fontSize: 28, flexShrink: 0 }}>{icon}</span>
                    <div>
                      <div style={{ fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>{title}</div>
                      <div style={{ color: '#64748b', fontSize: 13, lineHeight: 1.6 }}>{desc}</div>
                    </div>
                  </div>
                ))}
              </div>
              <Button onClick={finish} style={{ width: '100%' }}>Go to your dashboard →</Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function Step({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#7c3aed', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>{n}</div>
        <div style={{ fontWeight: 700, fontSize: 15, color: '#e2e8f0' }}>{title}</div>
      </div>
      <div style={{ paddingLeft: 40 }}>{children}</div>
    </div>
  )
}

function CodeBlock({ label, value, copyKey, copied, onCopy, note }: {
  label: string; value: string; copyKey: string; copied: string;
  onCopy: (v: string, k: string) => void; note?: string
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <code style={{ flex: 1, background: '#080810', border: '1px solid #1e1e3a', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: '#a78bfa', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {value}
        </code>
        <button onClick={() => onCopy(value, copyKey)} style={{ padding: '8px 14px', background: copied === copyKey ? '#166534' : '#1e1e3a', color: copied === copyKey ? '#3ecf8e' : '#94a3b8', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, flexShrink: 0 }}>
          {copied === copyKey ? 'Copied!' : 'Copy'}
        </button>
      </div>
      {note && <div style={{ fontSize: 11, color: '#475569', marginTop: 4 }}>{note}</div>}
    </div>
  )
}

function Button({ children, onClick, variant, style }: { children: React.ReactNode; onClick?: () => void; variant?: 'ghost'; style?: React.CSSProperties }) {
  return (
    <button onClick={onClick} style={{
      padding: '12px 28px', borderRadius: 10, border: variant === 'ghost' ? '1px solid #1e1e3a' : 'none',
      background: variant === 'ghost' ? 'transparent' : '#7c3aed',
      color: variant === 'ghost' ? '#64748b' : '#fff',
      fontWeight: 700, fontSize: 15, cursor: 'pointer', ...style,
    }}>{children}</button>
  )
}

// ─── Style constants ─────────────────────────────────────────────────────────
const H1: React.CSSProperties = { fontSize: 26, fontWeight: 800, color: '#f1f5f9', marginBottom: 12, letterSpacing: '-0.5px' }
const P:  React.CSSProperties = { color: '#64748b', fontSize: 14, lineHeight: 1.8, marginBottom: 8 }
const LINK: React.CSSProperties = { color: '#7c3aed', textDecoration: 'none', fontWeight: 600 }
const CODE: React.CSSProperties = { background: '#080810', border: '1px solid #1e1e3a', borderRadius: 8, padding: '14px 16px', fontSize: 13, color: '#a78bfa', fontFamily: 'monospace', lineHeight: 1.8, display: 'block', overflow: 'auto', marginBottom: 8 }
