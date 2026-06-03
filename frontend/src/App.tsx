/**
 * src/App.tsx — top-level router
 *
 * Public routes  →  Landing, Products, Pricing, Auth, Legal pages
 * Admin route    →  /command-center  (existing Command Center dashboard)
 *
 * The admin route is hidden from navigation.  Admins log in via /auth and
 * are redirected to /command-center based on VITE_ADMIN_EMAIL matching.
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { isSupabaseConfigured }  from './lib/supabase'
import SetupRequired             from './components/SetupRequired'
import Navbar                    from './components/Navbar'
import Footer                    from './components/Footer'
import AdminGuard                from './components/AdminGuard'
import AdminLogin                from './pages/AdminLogin'

// Public pages (lazy imports keep initial bundle small)
import Landing      from './pages/Landing'
import Pricing      from './pages/Pricing'
import Auth         from './pages/Auth'
import Onboarding   from './pages/Onboarding'
import Terms        from './pages/legal/Terms'
import Privacy      from './pages/legal/Privacy'
import Refund       from './pages/legal/Refund'

// Admin dashboard (loaded only when admin navigates there)
import CommandCenter from './pages/CommandCenter'

/** Routes that show Navbar + Footer */
const PUBLIC_ROUTES = ['/', '/products', '/pricing', '/auth', '/legal']

function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      {children}
      <Footer />
    </>
  )
}

/** Products page — placeholder until /api/products is populated */
function Products() {
  return (
    <div style={{ background: '#080810', minHeight: '100vh', color: '#e2e8f0', padding: '80px 24px' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <h1 style={{ fontSize: 40, fontWeight: 900, letterSpacing: '-1.5px', marginBottom: 12, color: '#f1f5f9' }}>
          All Products
        </h1>
        <p style={{ color: '#64748b', fontSize: 16, marginBottom: 48 }}>
          AI-built SaaS tools and media channels. Each product is autonomously designed, coded, and deployed.
        </p>
        <div style={{ color: '#475569', padding: 40, border: '1px solid #1e1e3a', borderRadius: 12, textAlign: 'center' }}>
          Products launching soon. Launch the pipeline to generate your first venture.
        </div>
      </div>
    </div>
  )
}

/** Dashboard placeholder for logged-in non-admin users */
function UserDashboard() {
  return (
    <div style={{ background: '#080810', minHeight: '80vh', color: '#e2e8f0', padding: '80px 24px', textAlign: 'center' }}>
      <h1 style={{ fontSize: 32, fontWeight: 800, color: '#f1f5f9', marginBottom: 12 }}>Your Dashboard</h1>
      <p style={{ color: '#64748b' }}>Your purchased products and subscription details will appear here.</p>
    </div>
  )
}

export default function App() {
  // Show setup screen when Supabase is not yet configured (local dev without .env)
  // This replaces the global SetupRequired from the old scaffold.
  // The Command Center has its own auth gate; public pages work without Supabase.
  const showSetupForAdmin = !isSupabaseConfigured &&
    (typeof window !== 'undefined' && window.location.pathname.startsWith('/command-center'))

  if (showSetupForAdmin) {
    return <SetupRequired />
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* ── Public routes (with Navbar + Footer) ──────────────────────── */}
        <Route path="/" element={<PublicLayout><Landing /></PublicLayout>} />
        <Route path="/products" element={<PublicLayout><Products /></PublicLayout>} />
        <Route path="/pricing"  element={<PublicLayout><Pricing /></PublicLayout>} />
        <Route path="/auth"     element={<Auth />} />
        <Route path="/dashboard"   element={<PublicLayout><UserDashboard /></PublicLayout>} />
        <Route path="/onboarding" element={<Onboarding />} />

        {/* Legal pages */}
        <Route path="/legal/terms"   element={<Legal><Terms /></Legal>} />
        <Route path="/legal/privacy" element={<Legal><Privacy /></Legal>} />
        <Route path="/legal/refund"  element={<Legal><Refund /></Legal>} />
        <Route path="/legal"         element={<Navigate to="/legal/terms" replace />} />

        {/* ── Admin routes — protected by AdminGuard (session + email + idle) ── */}
        <Route path="/admin-login"    element={<AdminLogin />} />
        <Route path="/command-center" element={
          <AdminGuard>
            <CommandCenter />
          </AdminGuard>
        } />
        {/* Legacy /admin redirect → secure login page (not public auth) */}
        <Route path="/admin"          element={<Navigate to="/admin-login" replace />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

/** Thin wrapper that adds Navbar to legal pages (legal pages have their own sidebar) */
function Legal({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      {children}
      <Footer />
    </>
  )
}
