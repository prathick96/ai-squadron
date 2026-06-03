import { useState } from 'react'
import { Link } from 'react-router-dom'

// ─── Style tokens ────────────────────────────────────────────────────────────
const S = {
  section: { maxWidth: 1100, margin: '0 auto', padding: '0 24px' },
  badge: {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '4px 12px', borderRadius: 99,
    border: '1px solid #3b1d8a', background: 'rgba(124,58,237,0.12)',
    color: '#a78bfa', fontSize: 12, fontWeight: 600, letterSpacing: '0.04em',
    marginBottom: 20,
  } as React.CSSProperties,
  h1: {
    fontSize: 'clamp(36px, 6vw, 72px)', fontWeight: 900, lineHeight: 1.08,
    letterSpacing: '-2px', color: '#f1f5f9', margin: '0 0 24px',
  } as React.CSSProperties,
  sub: { fontSize: 18, color: '#64748b', lineHeight: 1.7, maxWidth: 560 },
  ctaPrimary: {
    padding: '14px 32px', background: '#3ecf8e', color: '#080810',
    borderRadius: 10, fontWeight: 800, fontSize: 16, textDecoration: 'none',
    display: 'inline-block', transition: 'opacity 0.15s',
  } as React.CSSProperties,
  ctaGhost: {
    padding: '14px 32px', border: '1px solid #1e1e3a', color: '#94a3b8',
    borderRadius: 10, fontWeight: 600, fontSize: 16, textDecoration: 'none',
    display: 'inline-block',
  } as React.CSSProperties,
}

// ─── Feature tiles ────────────────────────────────────────────────────────────
const FEATURES = [
  { icon: '🤖', title: 'AI-Built, Human-Owned', desc: 'Every product is autonomously designed, coded, and deployed by AI agents — you own the result.' },
  { icon: '⚡', title: 'Live in Minutes', desc: 'From niche idea to deployed SaaS or YouTube channel in under 10 minutes. No engineers needed.' },
  { icon: '🌍', title: 'USD Revenue, Worldwide', desc: 'Payments via Paddle (Merchant of Record). Sell globally. No foreign entity required.' },
  { icon: '📊', title: 'Revenue Intelligence', desc: 'SCALE/KILL/MAINTAIN signals automatically. Every venture tracked. Dead weight auto-cut.' },
  { icon: '🔐', title: 'Legal & Compliant', desc: 'Legal Agent reviews every deployment. Terms, privacy, refund policies included by default.' },
  { icon: '🎬', title: 'Product + Media', desc: 'Both SaaS (React + FastAPI) and faceless media channels (YouTube, TikTok) in one pipeline.' },
]

// ─── Product catalogue ────────────────────────────────────────────────────────
const PRODUCTS = [
  {
    id: 'receipt-scanner',
    name: 'ReceiptIQ',
    tagline: 'AI Expense Receipt Scanner',
    desc: 'Snap a receipt — AI extracts vendor, amount, category and date instantly. Bulk-export to CSV or Google Sheets. Zero manual data entry for freelancers and contractors.',
    category: 'Finance SaaS',
    price: '$19/mo',
    status: 'live' as const,
    liveUrl: 'https://aisq-receipt-scanner.up.railway.app/',
  },
  {
    id: 'freelancerflow',
    name: 'FreelancerFlow',
    tagline: 'CRM & Invoicing for Solo Operators',
    desc: 'Lightweight CRM that turns your client list into a revenue machine. Track leads, send invoices, automate follow-ups — without the enterprise bloat of HubSpot or the chaos of spreadsheets.',
    category: 'Productivity SaaS',
    price: '$29/mo',
    status: 'notify' as const,
  },
  {
    id: 'channelmind',
    name: 'ChannelMind',
    tagline: 'Faceless YouTube Channel Automation',
    desc: 'AI writes scripts, generates voiceovers, assembles videos and publishes to YouTube on autopilot. Pick a niche, watch the channel grow. Zero on-camera time required.',
    category: 'Media Automation',
    price: '$49/mo',
    status: 'notify' as const,
  },
]

export default function Landing() {
  return (
    <div style={{ background: '#080810', minHeight: '100vh', color: '#e2e8f0' }}>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section style={{ padding: '120px 24px 80px', textAlign: 'center' }}>
        <div style={S.section}>
          <div style={S.badge}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#3ecf8e', display: 'inline-block' }} />
            Autonomous venture orchestration
          </div>
          <h1 style={S.h1}>
            AI builds the product.{' '}
            <span style={{ background: 'linear-gradient(135deg,#7c3aed,#3ecf8e)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              You collect the revenue.
            </span>
          </h1>
          <p style={{ ...S.sub, margin: '0 auto 40px' }}>
            AI Squadron autonomously researches niches, builds SaaS products and
            media channels, handles legal &amp; compliance, and deploys — so you don't have to.
          </p>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link to="/auth?mode=signup" style={S.ctaPrimary}>Start for free →</Link>
            <Link to="/pricing" style={S.ctaGhost}>View pricing</Link>
          </div>

          {/* Social proof bar */}
          <div style={{ marginTop: 64, display: 'flex', gap: 40, justifyContent: 'center', flexWrap: 'wrap' }}>
            {[
              { n: '3', label: 'Live products' },
              { n: '16', label: 'AI agents' },
              { n: '$0', label: 'No-code required' },
              { n: '~5m', label: 'Avg. deploy time' },
            ].map(({ n, label }) => (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#7c3aed' }}>{n}</div>
                <div style={{ fontSize: 12, color: '#475569', marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Products ──────────────────────────────────────────────────────── */}
      <section style={{ padding: '80px 24px', background: '#0a0a14' }}>
        <div style={S.section}>
          <h2 style={{ fontSize: 36, fontWeight: 800, color: '#f1f5f9', marginBottom: 8, letterSpacing: '-1px' }}>
            Our Products
          </h2>
          <p style={{ ...S.sub, marginBottom: 48 }}>
            Each product is autonomously researched, built, and deployed by AI agents.
            One live now — two shipping soon.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))', gap: 24 }}>
            {PRODUCTS.map((p) => (
              <ProductCard key={p.id} {...p} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────────────────────── */}
      <section style={{ padding: '80px 24px' }}>
        <div style={S.section}>
          <h2 style={{ fontSize: 36, fontWeight: 800, color: '#f1f5f9', marginBottom: 8, letterSpacing: '-1px', textAlign: 'center' }}>
            Why AI Squadron
          </h2>
          <p style={{ ...S.sub, textAlign: 'center', margin: '0 auto 48px' }}>
            One platform. Two revenue streams. Zero engineering team.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 20 }}>
            {FEATURES.map((f) => (
              <div key={f.title} style={{
                background: '#0f0f1a', border: '1px solid #1e1e3a',
                borderRadius: 12, padding: 28,
              }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>{f.icon}</div>
                <div style={{ fontWeight: 700, fontSize: 16, color: '#e2e8f0', marginBottom: 8 }}>{f.title}</div>
                <div style={{ color: '#64748b', fontSize: 14, lineHeight: 1.7 }}>{f.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA banner ────────────────────────────────────────────────────── */}
      <section style={{ padding: '80px 24px', background: '#0a0a14' }}>
        <div style={{ ...S.section, textAlign: 'center' }}>
          <h2 style={{ fontSize: 40, fontWeight: 900, color: '#f1f5f9', letterSpacing: '-1px', marginBottom: 16 }}>
            Ready to run your first venture?
          </h2>
          <p style={{ ...S.sub, margin: '0 auto 40px' }}>
            Sign up free. No credit card required to explore. Upgrade when your first product goes live.
          </p>
          <Link to="/auth?mode=signup" style={S.ctaPrimary}>
            Launch your first product →
          </Link>
          <p style={{ marginTop: 16, color: '#334155', fontSize: 13 }}>
            Payments powered by Paddle · 14-day money-back guarantee
          </p>
        </div>
      </section>
    </div>
  )
}

// ─── Product Card ────────────────────────────────────────────────────────────
type ProductStatus = 'live' | 'notify'

interface ProductCardProps {
  id: string
  name: string
  tagline: string
  desc: string
  category: string
  price: string
  status: ProductStatus
  liveUrl?: string
}

function ProductCard({ id, name, tagline, desc, category, price, status, liveUrl }: ProductCardProps) {
  const isLive = status === 'live'
  return (
    <div style={{
      background: '#0f0f1a',
      border: `1px solid ${isLive ? '#166534' : '#1e1e3a'}`,
      borderRadius: 14, padding: 28,
      display: 'flex', flexDirection: 'column', gap: 12,
      position: 'relative',
    }}>
      {/* Live pulse indicator */}
      {isLive && (
        <div style={{ position: 'absolute', top: 18, right: 18, display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', background: '#3ecf8e',
            boxShadow: '0 0 6px #3ecf8e', display: 'inline-block',
          }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: '#3ecf8e', letterSpacing: '0.05em' }}>LIVE</span>
        </div>
      )}

      {/* Category badge */}
      <span style={{
        padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600,
        background: 'rgba(124,58,237,0.15)', color: '#a78bfa', border: '1px solid #3b1d8a',
        alignSelf: 'flex-start',
      }}>{category}</span>

      <div>
        <h3 style={{ fontWeight: 800, fontSize: 20, color: '#f1f5f9', margin: '0 0 2px' }}>{name}</h3>
        <p style={{ margin: 0, fontSize: 12, color: '#7c3aed', fontWeight: 600 }}>{tagline}</p>
      </div>

      <p style={{ color: '#64748b', fontSize: 14, lineHeight: 1.65, margin: 0, flex: 1 }}>{desc}</p>

      <div style={{ fontWeight: 800, fontSize: 22, color: isLive ? '#f1f5f9' : '#475569' }}>{price}</div>

      {/* CTA area */}
      {isLive ? (
        <a
          href={liveUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'block', textAlign: 'center',
            padding: '11px 0', background: '#3ecf8e', color: '#080810',
            borderRadius: 9, fontSize: 14, fontWeight: 800, textDecoration: 'none',
            transition: 'opacity 0.15s',
          }}
        >
          Get Access →
        </a>
      ) : (
        <NotifyForm productId={id} productName={name} />
      )}
    </div>
  )
}

// ─── Notify Me form ──────────────────────────────────────────────────────────
function NotifyForm({ productId, productName }: { productId: string; productName: string }) {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setState('loading')
    setErrorMsg('')
    try {
      const res = await fetch(`/api/waitlist/${productId}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `HTTP ${res.status}`)
      }
      setState('done')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong')
      setState('error')
    }
  }

  if (state === 'done') {
    return (
      <div style={{
        textAlign: 'center', padding: '12px 0',
        background: 'rgba(62,207,142,0.08)', borderRadius: 9,
        border: '1px solid #166534',
      }}>
        <div style={{ color: '#3ecf8e', fontWeight: 700, fontSize: 14 }}>You're on the list!</div>
        <div style={{ color: '#475569', fontSize: 12, marginTop: 4 }}>
          We'll email you when {productName} launches.
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          type="email"
          required
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={state === 'loading'}
          style={{
            flex: 1, padding: '10px 12px',
            background: '#1a1a2e', border: '1px solid #1e1e3a',
            borderRadius: 8, color: '#e2e8f0', fontSize: 13,
            outline: 'none',
          }}
        />
        <button
          type="submit"
          disabled={state === 'loading'}
          style={{
            padding: '10px 16px',
            background: '#7c3aed', color: '#fff',
            borderRadius: 8, fontSize: 13, fontWeight: 700,
            border: 'none', cursor: state === 'loading' ? 'not-allowed' : 'pointer',
            opacity: state === 'loading' ? 0.7 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {state === 'loading' ? '...' : 'Notify Me'}
        </button>
      </div>
      {state === 'error' && (
        <p style={{ margin: 0, fontSize: 12, color: '#f87171' }}>{errorMsg}</p>
      )}
      <p style={{ margin: 0, fontSize: 11, color: '#334155' }}>
        No spam. One email when it ships.
      </p>
    </form>
  )
}
