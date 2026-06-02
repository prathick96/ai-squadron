import { Link } from 'react-router-dom'

const LEGAL_PAGES = [
  { label: 'Terms of Service', to: '/legal/terms'   },
  { label: 'Privacy Policy',   to: '/legal/privacy' },
  { label: 'Refund Policy',    to: '/legal/refund'  },
]

export default function LegalLayout({
  title, effective, children,
}: { title: string; effective: string; children: React.ReactNode }) {
  return (
    <div style={{ background: '#080810', minHeight: '100vh', color: '#e2e8f0', padding: '60px 24px' }}>
      <div style={{ maxWidth: 900, margin: '0 auto', display: 'grid', gridTemplateColumns: '200px 1fr', gap: 48, alignItems: 'start' }}>

        {/* Sidebar */}
        <aside style={{ position: 'sticky', top: 80 }}>
          <Link to="/" style={{ color: '#7c3aed', fontSize: 13, fontWeight: 600, textDecoration: 'none', display: 'block', marginBottom: 24 }}>
            ← Back to home
          </Link>
          <div style={{ fontWeight: 700, fontSize: 11, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 14 }}>
            Legal
          </div>
          <nav style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {LEGAL_PAGES.map(({ label, to }) => (
              <Link key={to} to={to} style={{
                fontSize: 13, color: window.location.pathname === to ? '#7c3aed' : '#64748b',
                textDecoration: 'none', fontWeight: window.location.pathname === to ? 600 : 400,
              }}>
                {label}
              </Link>
            ))}
          </nav>
        </aside>

        {/* Content */}
        <article>
          <div style={{ marginBottom: 8, fontSize: 12, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Legal
          </div>
          <h1 style={{ fontSize: 36, fontWeight: 900, color: '#f1f5f9', letterSpacing: '-1px', marginBottom: 6 }}>
            {title}
          </h1>
          <p style={{ color: '#475569', fontSize: 13, marginBottom: 40 }}>
            Effective date: {effective} · AI Squadron
          </p>
          {children}
        </article>
      </div>
    </div>
  )
}
