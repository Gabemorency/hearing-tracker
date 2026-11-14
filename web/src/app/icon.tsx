import { ImageResponse } from "next/og";

// Browser tab / bookmark icon. Next.js serves whatever this exports at
// /icon automatically and wires up the <link rel="icon"> itself — same
// navy capitol-dome mark as the header eyebrow, so the brand is
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
          background: "#0A0E1A",
          borderRadius: 7,
        }}
      >
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none">
          <path d="M12 2.5 20 7.5V9H4V7.5L12 2.5Z" fill="#5B8CDB" />
          <rect x="11" y="9" width="2" height="10" fill="#5B8CDB" />
          <rect x="6" y="9" width="2" height="10" fill="#5B8CDB" />
          <rect x="16" y="9" width="2" height="10" fill="#5B8CDB" />
          <rect x="3" y="19.5" width="18" height="2" fill="#5B8CDB" />
        </svg>
      </div>
    ),
    { ...size },
  );
}
