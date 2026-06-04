import { useState } from 'react'
import { Link } from 'react-router-dom'

const TIERS = [
  {
    name: 'Starter',
    tagline: 'Taste it',
    monthly: 0,
    annual: 0,
    desc: 'One venture, one run. No credit card. No commitment. See what AI builds.',
    highlight: false,
    planKey: '',
    features: [
      '1 active venture',
      '1 pipeline run per month',
      'SaaS or Media — your choice',
      'Build inspection & ZIP download',
      'Community support',
    ],
    cta: 'Start free →',
    ctaLink: '/auth?mode=signup',
  },
  {
    name: 'Builder',
    tagline: 'Run it',
    monthly: 49,
    annual: 39,
    desc: 'Run multiple ventures simultaneously. Spend credits on SaaS, Media, or Affiliate — any mix you want.',
    highlight: true,
    planKey: 'builder',
    features: [
      '5 active ventures',
      '10 pipeline runs / month (any type)',
      'SaaS apps + Media channels + Affiliate sites',
      'Live niche research (Kimi + Tavily)',
      'ElevenLabs voice generation',
      'Real Railway deployments (live HTTPS URLs)',
      'Priority email support',
      '14-day money-back guarantee',
    ],
    cta: 'Start building →',
    ctaLink: '/auth?mode=signup&plan=builder',
  },
  {
    name: 'Studio',
    tagline: 'Scale it',
    monthly: 149,
    annual: 119,
    desc: 'Unlimited portfolio. Build and run as many ventures as you want, across every pipeline type.',
    highlight: false,
    planKey: 'studio',
    features: [
      'Unlimited pipeline runs',
      'Unlimited ventures',
      'Unlimited active ventures',
      'Unlimited pipeline runs (SaaS + Media + Affiliate)',
      'YouTube + TikTok auto-publishing',
      'Razorpay revenue sync',
      'PostHog analytics on every product',
      'Custom niche research briefs',
      'Dedicated Slack support channel',
      '14-day money-back guarantee',
    ],
    cta: 'Go Studio →',
    ctaLink: '/auth?mode=signup&plan=studio',
  },
]

const PIPELINE_NOTE = {
  heading: 'One plan. Every venture type.',
  body: 'You choose what to build at run time — SaaS app, YouTube channel, or affiliate site. Your monthly runs work across all three. No locked tiers. No up-charges for switching.',
}

const FAQ = [
  { q: 'Do I need a credit card to start?', a: 'No. Starter is completely free with no card required. You only enter payment details when upgrading to Builder or Studio.' },
  { q: 'Can I build a YouTube channel AND a SaaS on the same plan?', a: 'Yes. Builder and Studio plan runs work across every venture type — SaaS apps, Media channels, and Affiliate sites. You choose at run time, not at purchase.' },
  { q: 'Who processes payments?', a: 'All payments are processed by Razorpay. International cards (Visa, Mastercard, Amex) are accepted. Customers are charged in USD. Indian accounts receive INR settlement after conversion — this is standard for all Indian payment gateways under RBI regulations.' },
  { q: 'What is the refund policy?', a: 'We offer a 14-day full refund on all paid plans, no questions asked. See our Refund Policy for details.' },
  { q: 'Can I cancel anytime?', a: 'Yes. Cancel from your dashboard at any time. Your plan stays active until the end of the billing period — no partial refunds after 14 days.' },
  { q: 'What APIs do I need?', a: 'Starter: nothing — works out of the box. Builder: ElevenLabs (voice) + Railway (deploy) for full features. Studio: all of the above + YouTube OAuth for publishing.' },
  { q: 'Is my data safe?', a: 'Your data is stored in Supabase (ISO 27001 certified). We never sell or share personal data. Row-Level Security ensures you only see your own ventures.' },
]

// ─── Razorpay checkout hook ────────────────────────────────────────────────────
// Razorpay Checkout.js is loaded from their CDN (already allowed in our CSP).
// The backend creates the subscription_id and returns key_id + subscription_id.
// The frontend opens the Razorpay modal, collects payment, then verifies on the backend.

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => {
      open: () => void
      on: (event: string, handler: (resp: RazorpayResponse) => void) => void
    }
  }
}

interface RazorpayOptions {
  key: string
  subscription_id: string
  name: string
  description: string
  image?: string
  currency: string
  handler: (response: RazorpayResponse) => void
  prefill?: { email?: string; contact?: string }
  theme?: { color?: string }
  modal?: { ondismiss?: () => void }
}

interface RazorpayResponse {
  razorpay_payment_id: string
  razorpay_subscription_id: string
  razorpay_signature: string
}

function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) { resolve(); return }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Razorpay checkout script'))
    document.head.appendChild(script)
  })
}

async function openRazorpayCheckout(planKey: string, isAnnual: boolean): Promise<void> {
  await loadRazorpayScript()

  // Ask our backend to create a Razorpay subscription and return the subscription_id + key_id
  const resp = await fetch('/api/payments/create-subscription', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_key: `${planKey}_${isAnnual ? 'annual' : 'monthly'}` }),
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail || `Subscription creation failed (HTTP ${resp.status})`)
  }

  const { key_id, subscription_id } = await resp.json()

  return new Promise((resolve, reject) => {
    const rzp = new window.Razorpay!({
      key: key_id,
      subscription_id,
      name: 'AI Squadron',
      description: 'Subscription',
      currency: 'USD',
      handler: async (response) => {
        // Verify signature on backend before marking subscription active
        await fetch('/api/payments/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(response),
        })
        resolve()
      },
      theme: { color: '#7c3aed' },
      modal: { ondismiss: () => reject(new Error('Payment cancelled')) },
    })
    rzp.open()
  })
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Pricing() {
  const [annual, setAnnual] = useState(false)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState('')

  async function checkout(tier: typeof TIERS[0]) {
    if (!tier.planKey) {
      window.location.href = tier.ctaLink
      return
    }

    setError('')
    setLoading(tier.planKey)
    try {
      await openRazorpayCheckout(tier.planKey, annual)
      window.location.href = '/auth?mode=signup&payment=success'
    } catch (err) {
      if (err instanceof Error && err.message !== 'Payment cancelled') {
        setError(err.message)
      }
    } finally {
      setLoading(null)
    }
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

        {/* Error banner */}
        {error && (
          <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #7f1d1d', borderRadius: 8, padding: '12px 16px', marginBottom: 24, color: '#fca5a5', fontSize: 13 }}>
            {error}
          </div>
        )}

        {/* Tiers */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 20, marginBottom: 80 }}>
          {TIERS.map((tier) => {
            const price = annual ? tier.annual : tier.monthly
            const isLoading = loading === tier.planKey
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

                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
                  <div style={{ fontWeight: 800, fontSize: 20, color: '#f1f5f9' }}>{tier.name}</div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{tier.tagline}</div>
                </div>
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
                  disabled={isLoading}
                  style={{
                    padding: '12px', width: '100%', borderRadius: 10, border: 'none',
                    cursor: isLoading ? 'not-allowed' : 'pointer',
                    fontWeight: 700, fontSize: 15, marginBottom: 28,
                    background: tier.highlight ? '#7c3aed' : '#1e1e3a',
                    color: tier.highlight ? '#fff' : '#e2e8f0',
                    opacity: isLoading ? 0.7 : 1,
                    transition: 'opacity 0.15s',
                  }}
                >
                  {isLoading ? 'Opening checkout…' : tier.cta}
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

        {/* Pipeline note */}
        <div style={{ background: 'linear-gradient(135deg,rgba(124,58,237,0.1),rgba(62,207,142,0.06))', border: '1px solid #3b1d8a', borderRadius: 12, padding: '24px 28px', marginBottom: 24, display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          <span style={{ fontSize: 24, flexShrink: 0 }}>⚡</span>
          <div>
            <div style={{ fontWeight: 700, color: '#e2e8f0', marginBottom: 6 }}>{PIPELINE_NOTE.heading}</div>
            <div style={{ color: '#64748b', fontSize: 14, lineHeight: 1.7 }}>{PIPELINE_NOTE.body}</div>
          </div>
        </div>

        {/* Razorpay trust badge */}
        <div style={{ textAlign: 'center', padding: '24px', background: '#0f0f1a', border: '1px solid #1e1e3a', borderRadius: 12, marginBottom: 80 }}>
          <p style={{ color: '#475569', fontSize: 13, margin: 0 }}>
            🔒 Payments secured by{' '}
            <a href="https://razorpay.com" target="_blank" rel="noreferrer" style={{ color: '#7c3aed', textDecoration: 'none', fontWeight: 600 }}>Razorpay</a>
            {' '} · International cards accepted (Visa, Mastercard, Amex) · SSL encrypted ·{' '}
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
