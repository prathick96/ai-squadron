/**
 * AdminGuard.tsx — Wraps the Command Center with session-based auth protection.
 *
 * Checks performed on every render:
 *   1. Supabase session present (JWT valid)
 *   2. Logged-in email === VITE_ADMIN_EMAIL
 *   3. Session not idle-expired (2 hours)
 *   4. Refreshes activity timestamp on mouse/keyboard events
 *
 * On any failure: redirects to /admin-login immediately.
 * On success:     renders children (the Command Center dashboard).
 */
import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { markAdminActivity, isAdminSessionExpired } from '../pages/AdminLogin'

const ADMIN_EMAIL = import.meta.env.VITE_ADMIN_EMAIL as string | undefined
const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'touchstart', 'scroll'] as const

export default function AdminGuard({ children }: { children: React.ReactNode }) {
  const navigate  = useNavigate()
  const [authed, setAuthed] = useState<boolean | null>(null)   // null = checking

  const kick = useCallback(() => {
    supabase?.auth.signOut().catch(() => {})
    navigate('/admin-login', { replace: true })
  }, [navigate])

  // Refresh activity timestamp on interaction
  useEffect(() => {
    const refresh = () => markAdminActivity()
    ACTIVITY_EVENTS.forEach(e => window.addEventListener(e, refresh, { passive: true }))
    return () => ACTIVITY_EVENTS.forEach(e => window.removeEventListener(e, refresh))
  }, [])

  // Session check on mount and every 60 seconds
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>

    async function checkSession() {
      if (!supabase) { kick(); return }

      // 1. Idle-expired check (client-side, no network call)
      if (isAdminSessionExpired()) {
        kick()
        return
      }

      // 2. Supabase session check (network)
      const { data: { user } } = await supabase.auth.getUser()
      if (!user || user.email !== ADMIN_EMAIL) {
        kick()
        return
      }

      markAdminActivity()
      setAuthed(true)
    }

    void checkSession()
    interval = setInterval(checkSession, 60_000)   // re-verify every minute
    return () => clearInterval(interval)
  }, [kick])

  // Splash while checking
  if (authed === null) {
    return (
      <div style={{
        minHeight: '100vh', background: '#030305',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <div style={{ color: '#334155', fontSize: 13, fontFamily: 'monospace' }}>
          Verifying session…
        </div>
      </div>
    )
  }

  return <>{children}</>
}
