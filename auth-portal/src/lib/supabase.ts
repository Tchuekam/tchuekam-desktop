import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://fzoiiusuqvjhwivstbyb.supabase.co'
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ6b2lpdXN1cXZqaHdpdnN0YnliIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQyNDgxNjUsImV4cCI6MjA5OTgyNDE2NX0.CH6Z7CxPaRxND2fivpcGu42RFmo8uxyBeeoeTuGEPCI'

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn('Supabase URL or Anon Key is missing in environment variables. Falling back to configured credentials.')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})
