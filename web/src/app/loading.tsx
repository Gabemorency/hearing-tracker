import { CapitolIcon } from "@/components/icons";

// Next's loading.js convention: this is the fallback shown automatically
// while any page (no closer loading.tsx overrides it) fetches its data —
// every page here is force-dynamic and awaits its Supabase queries before
// rendering, so this is what fills that wait instead of a blank screen.
export default function Loading() {
  return (
    <div className="app-loading">
      <CapitolIcon size={52} className="app-loading__icon" />
    </div>
  );
}
