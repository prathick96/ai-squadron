import { Link, useLocation, useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { useEffect, useState } from 'react'
import type { User } from '@supabase/supabase-js'

const LOGO = (
  <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
    <rect width="28" height="28" rx="7" fill="#7c3aed"/>
    <path d="M8 14l4 4 8-8" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

export default function Navbar() {
  const location   = useLocation()
  const navigate   = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [open, setOpen] = useState(false)

  const isAdmin      = location.pathname.startsWith('/admin') || location.pathname === '/command-center'
  const isPublic     = !isAdmin

  useEffect(() => {
    supabase?.auth.getUser().then(({ data }) => setUser(data.user ?? null))
    const { data: sub } = supabase?.auth.onAuthStateChange((_, s) => setUser(s?.user ?? null)) ?? { data: null }
    return () => sub?.subscription.unsubscribe()
  }, [])

  async function handleLogout() {
    await supabase?.auth.signOut()
    navigate('/')
  }

  if (!isPublic) return null

  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100,
      background: 'rgba(8,8,16,0.92)', backdropFilter: 'blur(12px)',
      borderBottom: '1px solid #1e1e3a',
      padding: '0 24px', height: 60,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }}>
      {/* Logo */}
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
        {LOGO}
        <span style={{ fontWeight: 800, fontSize: 18, color: '#e2e8f0', letterSpacing: '-0.5px' }}>
          AI Squadron
        </span>
      </Link>

      {/* Center nav */}
      <div style={{ display: 'flex', gap: 32, alignItems: 'center' }}>
        {[
          { to: '/products', label: 'Products' },
          { to: '/pricing',  label: 'Pricing'  },
          { to: '/about',    label: 'About'    },
        ].map(({ to, label }) => (
          <Link key={to} to={to} style={{
            color: location.pathname === to ? '#7c3aed' : '#94a3b8',
            textDecoration: 'none', fontSize: 14, fontWeight: 500,
            transition: 'color 0.15s',
          }}>
            {label}
          </Link>
        ))}
      </div>

      {/* Right actions */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {user ? (
          <>
            <span style={{ fontSize: 13, color: '#64748b' }}>{user.email}</span>
            <button onClick={handleLogout} style={{
              padding: '6px 16px', background: 'transparent',
              border: '1px solid #1e1e3a', color: '#94a3b8',
              borderRadius: 8, cursor: 'pointer', fontSize: 13,
            }}>
              Sign out
            </button>
          </>
        ) : (
          <>
            <Link to="/auth?mode=login" style={{
              padding: '6px 16px', color: '#94a3b8',
              textDecoration: 'none', fontSize: 14,
            }}>
              Log in
            </Link>
            <Link to="/auth?mode=signup" style={{
              padding: '8px 20px', background: '#3ecf8e',
              color: '#0a0a10', borderRadius: 8, fontSize: 14,
              fontWeight: 700, textDecoration: 'none',
              transition: 'opacity 0.15s',
            }}>
              Get started →
            </Link>
          </>
        )}
      </div>
    </nav>
  )
}
