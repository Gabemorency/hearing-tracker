import { ImageResponse } from "next/og";

// iOS "Add to Home Screen" icon. No rounding here — iOS applies its own
// mask, and a pre-rounded square shows up with a visible square behind
// the rounded mask.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
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
        }}
      >
        <svg width="108" height="108" viewBox="0 0 24 24" fill="none">
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
