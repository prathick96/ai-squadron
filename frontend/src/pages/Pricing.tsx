import { useState } from 'react'
import { Link } from 'react-router-dom'

const TIERS = [
  {
    name: 'Starter',
    monthly: 0,
    annual: 0,
    desc: 'Explore the platform and build your first venture at no cost.',
    highlight: false,
    paddleMonthlyId: '',
    paddleAnnualId: '',
    features: [
      '1 pipeline run per month',
      '1 active venture',
      'Product pipeline only',
      'Mock research (no live niche data)',
      'Community support',
      'Build inspection & download',
    ],
    cta: 'Start free',
    ctaLink: '/auth?mode=signup',
  },
  {
    name: 'Builder',
    monthly: 49,
    annual: 39,
    desc: 'For solo founders shipping their first real product or channel.',
    highlight: true,
    paddleMonthlyId: import.meta.env.VITE_PADDLE_BUILDER_MONTHLY ?? '',
    paddleAnnualId:  import.meta.env.VITE_PADDLE_BUILDER_ANNUAL  ?? '',
    features: [
      '10 pipeline runs per month',
      '5 active ventures',
      'Product + Media pipelines',
      'Live niche research (Kimi + Tavily)',
      'ElevenLabs voice generation',
      'Real Railway deployment',
      'Priority email support',
      '14-day money-back guarantee',
    ],
    cta: 'Start building',
    ctaLink: '/auth?mode=signup&plan=builder',
  },
  {
    name: 'Studio',
    monthly: 149,
    annual: 119,
    desc: 'Unlimited ventures, full API integrations, and white-glove onboarding.',
    highlight: false,
    paddleMonthlyId: import.meta.env.VITE_PADDLE_STUDIO_MONTHLY ?? '',
    paddleAnnualId:  import.meta.env.VITE_PADDLE_STUDIO_ANNUAL  ?? '',
    features: [
      'Unlimited pipeline runs',
      'Unlimited ventures',
      'Product + Media pipelines',
      'YouTube + TikTok publishing',
      'Stripe / Paddle revenue sync',
      'PostHog analytics per product',
      'Custom niche briefs',
      'Dedicated Slack channel',
      '14-day money-back guarantee',
    ],
    cta: 'Go Studio',
    ctaLink: '/auth?mode=signup&plan=studio',
  },
]

const FAQ = [
  { q: 'Do I need a credit card to start?', a: 'No. Starter is completely free with no card required. You only enter payment details when upgrading.' },
  { q: 'Who processes payments?', a: 'All payments are processed by Paddle, our Merchant of Record. Paddle handles global tax (VAT, GST, US sales tax) automatically — you receive clean revenue.' },
  { q: 'What is the refund policy?', a: 'We offer a 14-day full refund on all paid plans, no questions asked. See our Refund Policy for details.' },
  { q: 'Can I cancel anytime?', a: 'Yes. Cancel from your dashboard at any time. Your plan remains active until the end of the billing period.' },
  { q: 'What APIs do I need to provide?', a: 'For the full experience: ElevenLabs (voice), Railway (deploy), YouTube OAuth (publish), Supabase (database). Starter works without any external APIs.' },
  { q: 'Is my data safe?', a: 'Your data is stored in Supabase (ISO 27001 certified). We never sell or share personal data. See our Privacy Policy.' },
]

export default function Pricing() {
  const [annual, setAnnual] = useState(false)

  function checkout(tier: typeof TIERS[0]) {
    const priceId = annual ? tier.paddleAnnualId : tier.paddleMonthlyId
    if (!priceId) {
      window.location.href = tier.ctaLink
      return
    }
    // Paddle.js checkout
    const win = window as unknown as { Paddle?: { Checkout?: { open: (opts: { items: { priceId: string; quantity: number }[] }) => void } } }
    win.Paddle?.Checkout?.open({ items: [{ priceId, quantity: 1 }] })
  }

  return (
    <div style={{ background: '#080810', minHeight: '100vh', color: '#e2e8f0', padding: '80px 24px' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 56 }}>
          <h1 style={{ fontSize: 48, fontWeight: 900, letterSpacing: '-2px', color: '#f1f5f9', marginBottom: 12 }}>
            Simple, transparent pricing
          </h1>
          <p style={{ color: '#64748b', fontSize: 18, maxWidth: 520, margin: '0 auto 32px' }}>
            Start free. Pay only when your ventures generate real value.
            All plans include a 14-day money-back guarantee.
          </p>

          {/* Annual toggle */}
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12, background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 99, padding: '6px 8px' }}>
            <button onClick={() => setAnnual(false)} style={{
              padding: '6px 18px', borderRadius: 99, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
              background: !annual ? '#7c3aed' : 'transparent', color: !annual ? '#fff' : '#64748b',
            }}>Monthly</button>
            <button onClick={() => setAnnual(true)} style={{
              padding: '6px 18px', borderRadius: 99, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
              background: annual ? '#7c3aed' : 'transparent', color: annual ? '#fff' : '#64748b',
            }}>
              Annual <span style={{ color: '#3ecf8e', marginLeft: 4 }}>−20%</span>
            </button>
          </div>
        </div>

        {/* Tiers */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 20, marginBottom: 80 }}>
          {TIERS.map((tier) => {
            const price = annual ? tier.annual : tier.monthly
            return (
              <div key={tier.name} style={{
                background: tier.highlight ? 'linear-gradient(145deg,#150d2e,#0f0f1a)' : '#0f0f1a',
                border: `1px solid ${tier.highlight ? '#4c1d95' : '#1e1e3a'}`,
                borderRadius: 16, padding: 32, display: 'flex', flexDirection: 'column', gap: 0,
                position: 'relative', boxShadow: tier.highlight ? '0 0 60px rgba(124,58,237,0.15)' : 'none',
              }}>
                {tier.highlight && (
                  <div style={{
                    position: 'absolute', top: -12, left: '50%', transform: 'translateX(-50%)',
                    background: '#7c3aed', color: '#fff', fontSize: 11, fontWeight: 700,
                    padding: '4px 14px', borderRadius: 99, letterSpacing: '0.06em',
                  }}>MOST POPULAR</div>
                )}

                <div style={{ fontWeight: 800, fontSize: 20, color: '#f1f5f9', marginBottom: 6 }}>{tier.name}</div>
                <p style={{ color: '#64748b', fontSize: 13, lineHeight: 1.6, marginBottom: 24 }}>{tier.desc}</p>

                <div style={{ marginBottom: 28 }}>
                  <span style={{ fontSize: 48, fontWeight: 900, color: '#f1f5f9' }}>
                    {price === 0 ? 'Free' : `$${price}`}
                  </span>
                  {price > 0 && <span style={{ color: '#64748b', fontSize: 14 }}> / month</span>}
                  {annual && price > 0 && (
                    <div style={{ color: '#3ecf8e', fontSize: 12, marginTop: 4 }}>
                      Billed annually · Save ${(tier.monthly - tier.annual) * 12}/yr
                    </div>
                  )}
                </div>

                <button
                  onClick={() => checkout(tier)}
                  style={{
                    padding: '12px', width: '100%', borderRadius: 10, border: 'none', cursor: 'pointer',
                    fontWeight: 700, fontSize: 15, marginBottom: 28,
                    background: tier.highlight ? '#7c3aed' : '#1e1e3a',
                    color: tier.highlight ? '#fff' : '#e2e8f0',
                    transition: 'opacity 0.15s',
                  }}
                >
                  {tier.cta}
                </button>

                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {tier.features.map((f) => (
                    <li key={f} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 13, color: '#94a3b8' }}>
                      <span style={{ color: '#3ecf8e', flexShrink: 0, marginTop: 1 }}>✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>

        {/* Paddle trust badge */}
        <div style={{ textAlign: 'center', padding: '24px', background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 12, marginBottom: 80 }}>
          <p style={{ color: '#475569', fontSize: 13, margin: 0 }}>
            🔒 Payments processed by{' '}
            <a href="https://paddle.com" target="_blank" rel="noreferrer" style={{ color: '#7c3aed', textDecoration: 'none', fontWeight: 600 }}>Paddle</a>
            {' '} (Merchant of Record) · SSL encrypted · Global tax handled automatically ·{' '}
            <Link to="/legal/refund" style={{ color: '#7c3aed', textDecoration: 'none' }}>14-day refund guarantee</Link>
          </p>
        </div>

        {/* FAQ */}
        <h2 style={{ fontSize: 32, fontWeight: 800, color: '#f1f5f9', letterSpacing: '-1px', marginBottom: 32 }}>
          Frequently asked questions
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(440px,1fr))', gap: 20 }}>
          {FAQ.map(({ q, a }) => (
            <div key={q} style={{ background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 12, padding: 24 }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#e2e8f0', marginBottom: 8 }}>{q}</div>
              <div style={{ color: '#64748b', fontSize: 13, lineHeight: 1.7 }}>{a}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
