import { createClient as createSupabaseClient } from "@supabase/supabase-js";

// For read-only, public pages (everything except future auth-requiring
// routes). Unlike the cookie-based client in `server.ts`, this never calls
// cookies()/headers() — those are Next.js "dynamic APIs" that force a page
// into fully uncached, per-request rendering the moment they're touched,
// no matter what `revalidate` says. Every page here reads nothing but
// public, RLS-"public read" data, so there's nothing a session would add;
// using this client instead is what actually lets `revalidate` cache the
// rendered page between visits instead of re-querying Supabase every time.
export function createPublicClient() {
  // Falls back to an unreachable placeholder instead of throwing when the
  // env vars are unset (a CI build-time prerender, a fresh checkout) —
  // createClient() itself throws synchronously on an empty URL, which
  // would crash the build; a placeholder URL just makes the query fail at
  // request time instead, which every page already renders as its normal
  // ErrorPanel state.
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://placeholder.invalid";
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "placeholder-anon-key";
  return createSupabaseClient(url, key);
}
