export default function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="panel error-panel" style={{ marginTop: 18 }}>
      <div className="row">
        <div className="error-panel__title">Something went wrong loading this page</div>
        <div className="error-panel__sub">We couldn&apos;t reach the database just now — try refreshing in a moment.</div>
        <details className="error-panel__details">
          <summary>Technical details</summary>
          <code>{message}</code>
        </details>
      </div>
    </div>
  );
}
