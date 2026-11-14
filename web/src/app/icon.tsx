import { ImageResponse } from "next/og";

// Browser tab / bookmark icon. Next.js serves whatever this exports at
// /icon automatically and wires up the <link rel="icon"> itself — same
// gold capitol-dome mark as the header eyebrow, so the brand is
// consistent everywhere instead of the framework's default globe icon.
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0D0C0A",
          borderRadius: 7,
        }}
      >
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none">
          <path d="M12 2.5 20 7.5V9H4V7.5L12 2.5Z" fill="#E0B870" />
          <rect x="11" y="9" width="2" height="10" fill="#E0B870" />
          <rect x="6" y="9" width="2" height="10" fill="#E0B870" />
          <rect x="16" y="9" width="2" height="10" fill="#E0B870" />
          <rect x="3" y="19.5" width="18" height="2" fill="#E0B870" />
        </svg>
      </div>
    ),
    { ...size },
  );
}
