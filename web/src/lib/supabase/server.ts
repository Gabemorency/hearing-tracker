import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

// Server-side client for use in Server Components / Route Handlers.
// Cookie-based session plumbing is here now so it's ready for anonymous
// sign-in (Phase 4's alerts/subscriptions) without needing to revisit
// this file — today's read-only pages don't require a session at all.
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component with no response to write
            // to — fine as long as middleware refreshes the session.
          }
        },
      },
    },
  );
}
