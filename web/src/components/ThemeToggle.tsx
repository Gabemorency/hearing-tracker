"use client";

import { useSyncExternalStore } from "react";

// Theme lives outside React — in the `.light` class on <html> (set by the
// pre-hydration bootstrap script in layout.tsx) and in localStorage — so
// this reads it via useSyncExternalStore rather than useEffect+setState,
// which is the correct tool for state that changes outside React's own
// render cycle (our own toggle, or the OS theme changing).
function subscribe(callback: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: light)");
  mq.addEventListener("change", callback);
  window.addEventListener("theme-change", callback);
  return () => {
    mq.removeEventListener("change", callback);
    window.removeEventListener("theme-change", callback);
  };
}

function getSnapshot(): "dark" | "light" {
  return document.documentElement.classList.contains("light") ? "light" : "dark";
}

function getServerSnapshot(): "dark" | "light" {
  return "dark"; // arbitrary — the real theme was already applied to the DOM
  // by the pre-hydration script before this ever renders client-side.
}

export default function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    localStorage.setItem("theme", next);
    document.documentElement.classList.toggle("light", next === "light");
    window.dispatchEvent(new Event("theme-change"));
  }

  return (
    <button
      className="theme-toggle"
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle light/dark mode"
    >
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}
