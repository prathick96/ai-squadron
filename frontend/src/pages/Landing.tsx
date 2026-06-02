import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

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

import { type FC } from 'react'

const Landing: FC = () => {
  const { data: productsData } = useQuery({
    queryKey: ['products'],
    queryFn: () => api.products?.() ?? Promise.resolve({ products: [], count: 0 }),
  })

  const products = productsData?.products ?? []

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
            media channels, handles legal & compliance, and deploys — so you don't have to.
          </p>
          <div style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link to="/auth?mode=signup" style={S.ctaPrimary}>Start for free →</Link>
            <Link to="/products" style={S.ctaGhost}>View products</Link>
          </div>

          {/* Social proof bar */}
          <div style={{ marginTop: 64, display: 'flex', gap: 40, justifyContent: 'center', flexWrap: 'wrap' }}>
            {[
              { n: '2+', label: 'Live ventures' },
              { n: '16', label: 'AI agents' },
              { n: '$0', label: 'No-code required' },
              { n: '5m', label: 'Avg. deploy time' },
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
            Each product is autonomously built by AI agents responding to real market demand.
          </p>

          {products.length === 0 ? (
            /* Placeholder cards while ventures are in development */
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 20 }}>
              {[
                { name: 'TaxFlow AI', desc: 'Automated quarterly tax estimation and deduction scanner for freelancers.', category: 'Finance', price: '$29/mo', status: 'Coming soon' },
                { name: 'ChannelMind', desc: 'Faceless YouTube channel automation — scripts, voice, video, upload.', category: 'Media', price: '$49/mo', status: 'Coming soon' },
                { name: 'SoloStack', desc: 'CRM and invoicing built for solopreneurs. No enterprise bloat.', category: 'Productivity', price: '$19/mo', status: 'Coming soon' },
              ].map((p) => (
                <ProductCard key={p.name} {...p} />
              ))}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 20 }}>
              {products.map((p: { niche: string; venture_id: string; status: string; venture_type: string }) => (
                <ProductCard
                  key={p.venture_id}
                  name={p.niche || 'AI Tool'}
                  desc={`Autonomously built ${p.venture_type === 'MEDIA_CHANNEL' ? 'media channel' : 'SaaS tool'} — powered by AI Squadron.`}
                  category={p.venture_type === 'MEDIA_CHANNEL' ? 'Media' : 'SaaS'}
                  price="$29/mo"
                  status={p.status === 'LIVE' ? 'Live' : 'Coming soon'}
                />
              ))}
            </div>
          )}

          <div style={{ marginTop: 40, textAlign: 'center' }}>
            <Link to="/products" style={S.ctaGhost}>View all products →</Link>
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

function ProductCard({ name, desc, category, price, status }: {
  name: string; desc: string; category: string; price: string; status: string
}) {
  const isLive = status === 'Live'
  return (
    <div style={{
      background: '#0f0f1a', border: '1px solid #1e1e3a',
      borderRadius: 14, padding: 28, display: 'flex', flexDirection: 'column', gap: 12,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{
          padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600,
          background: 'rgba(124,58,237,0.15)', color: '#a78bfa', border: '1px solid #3b1d8a',
        }}>{category}</span>
        <span style={{
          padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600,
          background: isLive ? 'rgba(62,207,142,0.12)' : 'rgba(71,85,105,0.3)',
          color: isLive ? '#3ecf8e' : '#64748b',
          border: `1px solid ${isLive ? '#166534' : '#334155'}`,
        }}>{status}</span>
      </div>
      <h3 style={{ fontWeight: 800, fontSize: 18, color: '#f1f5f9', margin: 0 }}>{name}</h3>
      <p style={{ color: '#64748b', fontSize: 14, lineHeight: 1.6, margin: 0, flex: 1 }}>{desc}</p>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
        <span style={{ fontWeight: 800, fontSize: 20, color: '#7c3aed' }}>{price}</span>
        <Link to="/pricing" style={{
          padding: '8px 18px', background: '#7c3aed', color: '#fff',
          borderRadius: 8, fontSize: 13, fontWeight: 700, textDecoration: 'none',
          opacity: isLive ? 1 : 0.5,
          pointerEvents: isLive ? 'auto' : 'none',
        }}>
          {isLive ? 'Get access' : 'Notify me'}
        </Link>
      </div>
    </div>
  )
}

export default Landing
