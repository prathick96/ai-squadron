export default function SetupRequired() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24, background: '#080810',
    }}>
      <div style={{
        maxWidth: 480, width: '100%',
        background: '#0f0f1a', border: '1px solid #1e1e3a',
        borderRadius: 12, padding: 40, textAlign: 'center',
      }}>
        <div style={{ fontSize: 48, marginBottom: 20 }}>⚙️</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#f1f5f9', marginBottom: 10 }}>
          Connect Your Database
        </h1>
        <p style={{ color: '#64748b', lineHeight: 1.6, marginBottom: 28, fontSize: 14 }}>
          This app needs Supabase for authentication and data storage.
          Add these two environment variables in Railway to get started.
        </p>
        <div style={{
          background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 8,
          padding: '14px 18px', fontFamily: 'monospace', fontSize: 13,
          textAlign: 'left', marginBottom: 24, lineHeight: 2, color: '#0f172a',
        }}>
          VITE_SUPABASE_URL=https://xxx.supabase.co<br />
          VITE_SUPABASE_ANON_KEY=eyJ...
        </div>
        <a
          href="https://supabase.com/dashboard"
          target="_blank"
          rel="noreferrer"
          style={{
            padding: '10px 22px', background: '#3ecf8e', color: '#080810',
            borderRadius: 8, textDecoration: 'none', fontWeight: 700, fontSize: 14,
          }}
        >
          Get Supabase Keys →
        </a>
      </div>
    </div>
  )
}
