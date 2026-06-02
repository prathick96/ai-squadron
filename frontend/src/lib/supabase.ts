import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

/** True when both VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are configured */
export const isSupabaseConfigured = Boolean(
  url && url.startsWith('https://') && key && key.length > 20
)

/**
 * Supabase client — null when env vars are not configured.
 * Always guard with: if (!supabase) return
 */
export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(url!, key!)
  : null
