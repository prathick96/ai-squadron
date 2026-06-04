import LegalLayout from './LegalLayout'
import { Link } from 'react-router-dom'

const EFFECTIVE = '31 May 2026'
const EMAIL     = 'billing@ai-squadron.com'

export default function Refund() {
  return (
    <LegalLayout title="Refund Policy" effective={EFFECTIVE}>

      <section style={sec}>
        <h2 style={h2}>Overview</h2>
        <p style={p}>
          AI Squadron aims to deliver real value from day one. If we fall short, we want to make it right.
          This Refund Policy describes the conditions under which we issue refunds for subscriptions and
          one-time purchases made through Razorpay.
        </p>
        <p style={p}>
          All refund requests are subject to this policy, which applies in addition to any rights you may
          have under the mandatory consumer protection laws of your jurisdiction.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>1. Subscription Refunds — 14-Day Guarantee</h2>
        <p style={p}>
          We offer a <strong style={strong}>14-day full refund</strong> on all paid subscription plans (Builder and Studio),
          measured from:
        </p>
        <ul style={ul}>
          <li style={li}>The date of your <strong style={strong}>initial subscription</strong> for new accounts.</li>
          <li style={li}>The date of each <strong style={strong}>subscription renewal</strong> for recurring payments.</li>
        </ul>
        <p style={p}>
          To request a refund within the 14-day window, email <a href={`mailto:${EMAIL}`} style={{ color: '#7c3aed' }}>{EMAIL}</a>{' '}
          with your registered email address and the reason for your request. Refunds are processed within 5–10 business days
          and returned to your original payment method via Razorpay.
        </p>
        <p style={p}>
          After the 14-day window, subscription fees are <strong style={strong}>non-refundable</strong> and your plan
          remains active until the end of the current billing period.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>2. One-Time Purchases</h2>
        <p style={p}>
          One-time purchases (e.g., lifetime plans or individual product access) are eligible for a full refund
          within 14 days of the purchase date, provided the purchased access has not been substantially used
          (e.g., more than 5 pipeline runs consumed).
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>3. Exceptions — When Refunds Are Not Available</h2>
        <p style={p}>Refunds will not be issued in the following circumstances:</p>
        <ul style={ul}>
          <li style={li}>Requests made after the 14-day refund window has expired.</li>
          <li style={li}>Accounts that have been suspended or terminated for violating our Terms of Service.</li>
          <li style={li}>Requests citing dissatisfaction with AI-generated output quality — as AI generation is inherently variable and we make no guarantee of output quality beyond reasonable effort.</li>
          <li style={li}>Requests arising from your failure to configure required third-party API keys (ElevenLabs, Railway, YouTube, etc.) that are necessary for specific features.</li>
          <li style={li}>Partial-month usage on monthly plans after the 14-day window.</li>
        </ul>
      </section>

      <section style={sec}>
        <h2 style={h2}>4. Service Credits (Technical Issues)</h2>
        <p style={p}>
          If the platform experiences a verified outage or technical failure that prevents you from using the
          Services for more than 24 consecutive hours within a billing period, you may be eligible for a
          pro-rata service credit applied to your next billing cycle.
        </p>
        <p style={p}>
          Credit requests must be submitted within 30 days of the incident to <a href={`mailto:${EMAIL}`} style={{ color: '#7c3aed' }}>{EMAIL}</a>,
          with a description of the issue. Credits are not redeemable for cash.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>5. How Refunds Are Processed</h2>
        <p style={p}>
          All refunds are processed through <strong style={strong}>Paddle</strong>, our payment processor.
          Razorpay will return the funds to your original payment method. Processing times depend on your card
          issuer or bank but typically take 5–10 business days after Paddle approves the refund.
        </p>
        <p style={p}>
          We cannot refund in cash, cryptocurrency, or to a different payment method than the one used for the
          original purchase.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>6. How to Request a Refund</h2>
        <ol style={{ ...ul, paddingLeft: 24 }}>
          <li style={li}>Email <a href={`mailto:${EMAIL}`} style={{ color: '#7c3aed' }}>{EMAIL}</a> from your registered account email address.</li>
          <li style={li}>Include your full name, the email associated with your account, and the date of the charge.</li>
          <li style={li}>Briefly describe the reason for your request (optional but helpful).</li>
          <li style={li}>We will confirm receipt within 1 business day and process your refund within 5 business days if eligible.</li>
        </ol>
      </section>

      <section style={sec}>
        <h2 style={h2}>7. Consumer Rights</h2>
        <p style={p}>
          Nothing in this Refund Policy limits or overrides any mandatory rights you have under the consumer
          protection laws of your jurisdiction. For EU/UK users, this includes the 14-day statutory right of
          withdrawal under the Consumer Rights Directive and the Consumer Contracts Regulations 2013 respectively.
          For Indian users, relevant provisions of the Consumer Protection Act, 2019 apply.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>Questions</h2>
        <p style={p}>
          For any billing or refund enquiries, contact us at:{' '}
          <a href={`mailto:${EMAIL}`} style={{ color: '#7c3aed' }}>{EMAIL}</a>
        </p>
        <p style={p}>
          See also: <Link to="/legal/terms" style={{ color: '#7c3aed' }}>Terms of Service</Link> ·{' '}
          <Link to="/legal/privacy" style={{ color: '#7c3aed' }}>Privacy Policy</Link>
        </p>
      </section>

    </LegalLayout>
  )
}

const sec: React.CSSProperties    = { marginBottom: 40 }
const h2: React.CSSProperties     = { fontSize: 20, fontWeight: 700, color: '#e2e8f0', marginBottom: 14, borderBottom: '1px solid #1e1e3a', paddingBottom: 10 }
const p: React.CSSProperties      = { color: '#94a3b8', fontSize: 14, lineHeight: 1.8, marginBottom: 10 }
const ul: React.CSSProperties     = { paddingLeft: 20, marginBottom: 12 }
const li: React.CSSProperties     = { color: '#94a3b8', fontSize: 14, lineHeight: 1.8, marginBottom: 6 }
const strong: React.CSSProperties = { color: '#cbd5e1' }
