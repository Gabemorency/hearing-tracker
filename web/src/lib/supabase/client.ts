import { createBrowserClient } from "@supabase/ssr";

// Public anon key only — safe for the browser. Public content is
// readable by anyone per the RLS policies in
// supabase/migrations/0001_init.sql; the service_role key never belongs
// in this app at all (only the Python scraper, writing from GitHub
// Actions, needs it).
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
