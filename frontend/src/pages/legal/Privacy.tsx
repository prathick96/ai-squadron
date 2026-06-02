import LegalLayout from './LegalLayout'

const EFFECTIVE = '31 May 2026'
const EMAIL     = 'privacy@ai-squadron.com'

export default function Privacy() {
  return (
    <LegalLayout title="Privacy Policy" effective={EFFECTIVE}>

      <section style={sec}>
        <h2 style={h2}>1. Introduction and Scope</h2>
        <p style={p}>
          AI Squadron ("we", "us", "our") is committed to protecting your personal information. This Privacy Policy
          explains what data we collect, how we use it, who we share it with, and your rights in relation to it.
        </p>
        <p style={p}>
          This policy applies to all users of our website, platform, and services, regardless of location.
          Where EU/UK General Data Protection Regulation (GDPR) applies, we act as the Data Controller.
          Where applicable Indian data protection law applies (including the Digital Personal Data Protection Act, 2023),
          we act as the Data Fiduciary.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>2. Data We Collect</h2>
        <p style={p}><strong style={strong}>Account data:</strong> Email address, password (hashed — never stored in plain text), account preferences, and subscription status.</p>
        <p style={p}><strong style={strong}>Payment data:</strong> All payment transactions are handled by Paddle (our Merchant of Record). We do not store your credit card number, bank account details, or full payment instrument information. We receive only transaction metadata (subscription status, amount, currency) from Paddle.</p>
        <p style={p}><strong style={strong}>Usage data:</strong> Pipeline runs initiated, ventures created, agents invoked, API calls made, feature interactions, and session duration. This data is used for platform improvement and abuse prevention.</p>
        <p style={p}><strong style={strong}>Technical data:</strong> IP address, browser type, operating system, referring URL, and device identifiers. Collected automatically when you use the Services.</p>
        <p style={p}><strong style={strong}>Content data:</strong> Any instructions, prompts, briefs, or custom data you provide to the platform to guide AI-generated output. This data is processed to provide the Services and is not used to train our AI models without your explicit consent.</p>
        <p style={p}><strong style={strong}>Communications:</strong> Emails or messages you send to our support team.</p>
      </section>

      <section style={sec}>
        <h2 style={h2}>3. How We Use Your Data</h2>
        <ul style={ul}>
          <li style={li}>To provide, operate, and maintain the Services you have requested.</li>
          <li style={li}>To process your subscription and communicate billing information through Paddle.</li>
          <li style={li}>To send transactional emails (account confirmation, password reset, subscription receipts).</li>
          <li style={li}>To monitor and improve platform performance, security, and reliability.</li>
          <li style={li}>To enforce our Terms of Service and prevent fraudulent or abusive activity.</li>
          <li style={li}>To comply with applicable legal obligations, including tax reporting requirements.</li>
          <li style={li}>To send product updates and service announcements (you may opt out at any time).</li>
        </ul>
        <p style={p}>
          We do not use your data for automated decision-making that produces legal or similarly significant effects,
          except for subscription status enforcement (e.g., downgrading access if a payment fails).
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>4. Data Processors and Third-Party Services</h2>
        <p style={p}>We share your data with the following categories of processors, solely to provide the Services:</p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {['Processor', 'Purpose', 'Data shared'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 12px', background: '#0f0f1a', color: '#64748b', borderBottom: '1px solid #1e1e3a' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              ['Supabase', 'Database and authentication', 'Email, hashed password, usage data'],
              ['Paddle', 'Payment processing', 'Email, billing address, transaction data'],
              ['Anthropic', 'AI code generation (Claude)', 'Prompts and technical specs you provide'],
              ['Google', 'AI inference (Gemini)', 'Prompts and technical specs you provide'],
              ['PostHog', 'Product analytics (opt-in)', 'Anonymised usage events'],
              ['ElevenLabs', 'Voice synthesis', 'Script text for voice generation'],
              ['Railway', 'Cloud deployment', 'Generated application code'],
            ].map(([proc, purpose, data]) => (
              <tr key={proc} style={{ borderBottom: '1px solid #1e1e3a' }}>
                <td style={td}><strong style={{ color: '#cbd5e1' }}>{proc}</strong></td>
                <td style={td}>{purpose}</td>
                <td style={td}>{data}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ ...p, marginTop: 16 }}>
          We do not sell, rent, or share your personal data with third parties for their independent marketing purposes.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>5. Data Retention</h2>
        <p style={p}>
          We retain your account data for as long as your account is active or as needed to provide the Services.
          If you close your account, we will delete or anonymise your personal data within 90 days, unless we are
          required by law to retain it longer (e.g., for tax or fraud prevention purposes).
        </p>
        <p style={p}>
          Aggregated, anonymised usage statistics that cannot be re-identified may be retained indefinitely for
          platform analytics.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>6. Your Rights</h2>
        <p style={p}>Depending on your location, you may have the following rights regarding your personal data:</p>
        <ul style={ul}>
          <li style={li}><strong style={strong}>Access:</strong> Request a copy of the personal data we hold about you.</li>
          <li style={li}><strong style={strong}>Correction:</strong> Request correction of inaccurate or incomplete data.</li>
          <li style={li}><strong style={strong}>Deletion:</strong> Request deletion of your personal data ("right to be forgotten").</li>
          <li style={li}><strong style={strong}>Portability:</strong> Receive your data in a structured, machine-readable format.</li>
          <li style={li}><strong style={strong}>Objection / Restriction:</strong> Object to or restrict certain processing activities.</li>
          <li style={li}><strong style={strong}>Opt-out of marketing:</strong> Unsubscribe from marketing emails at any time via the link in any email.</li>
        </ul>
        <p style={p}>
          To exercise any of these rights, email us at <a href={`mailto:${EMAIL}`} style={{ color: '#7c3aed' }}>{EMAIL}</a>.
          We will respond within 30 days (or within 72 hours for breach notifications as required by applicable law).
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>7. Cookies and Tracking</h2>
        <p style={p}>
          Our website uses strictly necessary cookies for session management and authentication. We do not use
          third-party advertising cookies. PostHog analytics is loaded only when you have opted in (or by default
          when you have not opted out, subject to applicable law).
        </p>
        <p style={p}>
          You may disable cookies in your browser settings, but this may impact the functionality of the Services.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>8. International Data Transfers</h2>
        <p style={p}>
          Our service providers may process your data in countries outside India, including the United States and
          the European Union. Where such transfers occur, we rely on appropriate safeguards including Standard
          Contractual Clauses (SCCs) or the provider's adequacy decision under applicable data protection law.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>9. Children's Privacy</h2>
        <p style={p}>
          The Services are not directed to persons under 18 years of age. We do not knowingly collect personal data
          from minors. If you believe we have inadvertently collected data from a minor, contact us immediately and
          we will delete it promptly.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>10. Changes to This Policy</h2>
        <p style={p}>
          We may update this Privacy Policy periodically. For material changes, we will notify you by email or
          prominent notice on the platform at least 14 days before the change takes effect.
          Your continued use of the Services after the effective date constitutes acceptance of the updated policy.
        </p>
      </section>

      <section style={sec}>
        <h2 style={h2}>Contact</h2>
        <p style={p}>
          For privacy enquiries, contact our Privacy Officer at:{' '}
          <a href={`mailto:${EMAIL}`} style={{ color: '#7c3aed' }}>{EMAIL}</a>
        </p>
      </section>

    </LegalLayout>
  )
}

const sec: React.CSSProperties = { marginBottom: 40 }
const h2: React.CSSProperties  = { fontSize: 20, fontWeight: 700, color: '#e2e8f0', marginBottom: 14, borderBottom: '1px solid #1e1e3a', paddingBottom: 10 }
const p: React.CSSProperties   = { color: '#94a3b8', fontSize: 14, lineHeight: 1.8, marginBottom: 10 }
const ul: React.CSSProperties  = { paddingLeft: 20, marginBottom: 12 }
const li: React.CSSProperties  = { color: '#94a3b8', fontSize: 14, lineHeight: 1.8, marginBottom: 6 }
const strong: React.CSSProperties = { color: '#cbd5e1' }
const td: React.CSSProperties  = { padding: '10px 12px', color: '#94a3b8', verticalAlign: 'top' }
