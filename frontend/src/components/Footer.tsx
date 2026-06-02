import { Link } from 'react-router-dom'

const cols = [
  {
    heading: 'Products',
    links: [
      { label: 'All Products', to: '/products' },
      { label: 'Pricing',      to: '/pricing'  },
      { label: 'Changelog',    to: '/changelog'},
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About',       to: '/about'   },
      { label: 'Blog',        to: '/blog'    },
      { label: 'Careers',     to: '/careers' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Terms of Service', to: '/legal/terms'   },
      { label: 'Privacy Policy',   to: '/legal/privacy' },
      { label: 'Refund Policy',    to: '/legal/refund'  },
    ],
  },
  {
    heading: 'Connect',
    links: [
      { label: 'Twitter / X', to: 'https://twitter.com', external: true },
      { label: 'GitHub',      to: 'https://github.com',  external: true },
      { label: 'Support',     to: 'mailto:support@ai-squadron.com', external: true },
    ],
  },
]

export default function Footer() {
  return (
    <footer style={{
      background: '#050508',
      borderTop: '1px solid #1e1e3a',
      padding: '64px 24px 32px',
    }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Top row */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr', gap: 40, marginBottom: 48 }}>
          {/* Brand */}
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#e2e8f0', marginBottom: 12 }}>
              AI Squadron
            </div>
            <p style={{ color: '#64748b', fontSize: 13, lineHeight: 1.7, maxWidth: 280 }}>
              Autonomous venture & media orchestration. We build AI-powered SaaS tools
              and content channels — then help you run them.
            </p>
            <p style={{ color: '#475569', fontSize: 12, marginTop: 16 }}>
              Payments secured by{' '}
              <a href="https://paddle.com" target="_blank" rel="noreferrer" style={{ color: '#7c3aed', textDecoration: 'none' }}>
                Paddle
              </a>
            </p>
          </div>

          {/* Nav columns */}
          {cols.map((col) => (
            <div key={col.heading}>
              <div style={{ fontWeight: 600, fontSize: 12, color: '#475569', marginBottom: 14, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                {col.heading}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {col.links.map((l) =>
                  (l as { external?: boolean }).external ? (
                    <a key={l.label} href={l.to} target="_blank" rel="noreferrer" style={{ color: '#64748b', fontSize: 13, textDecoration: 'none' }}>
                      {l.label}
                    </a>
                  ) : (
                    <Link key={l.label} to={l.to} style={{ color: '#64748b', fontSize: 13, textDecoration: 'none' }}>
                      {l.label}
                    </Link>
                  )
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Bottom */}
        <div style={{
          borderTop: '1px solid #1e1e3a',
          paddingTop: 24,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
        }}>
          <p style={{ color: '#334155', fontSize: 12 }}>
            © {new Date().getFullYear()} AI Squadron. All rights reserved.
          </p>
          <p style={{ color: '#334155', fontSize: 12 }}>
            Built with AI · Governed by Indian law · Payments via Paddle (MoR)
          </p>
        </div>
      </div>
    </footer>
  )
}
