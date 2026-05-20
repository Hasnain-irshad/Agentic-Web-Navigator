interface Props {
  url: string;
  errorCode?: number;
  errorDescription?: string;
  onRetry: () => void;
  onHome: () => void;
}

export default function ErrorPage({
  url,
  errorCode,
  errorDescription,
  onRetry,
  onHome,
}: Props) {
  return (
    <div style={container}>
      <h1 style={title}>😵 Page failed to load</h1>

      <p style={subtitle}>
        Something went wrong while trying to open:
      </p>

      <div style={urlBox}>{url}</div>

      <p style={errorText}>
        {errorDescription || 'The website may be down or you are offline.'}
        {errorCode && <span> (Error code: {errorCode})</span>}
      </p>

      <div style={actions}>
        <button style={retryBtn} onClick={onRetry}>
          🔄 Retry
        </button>
        <button style={homeBtn} onClick={onHome}>
          🏠 Go Home
        </button>
      </div>
    </div>
  );
}

/* ---------- Styles ---------- */
const container: React.CSSProperties = {
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  textAlign: 'center',
  padding: '20px',
};

const title: React.CSSProperties = {
  fontSize: '32px',
  marginBottom: '10px',
};

const subtitle: React.CSSProperties = {
  color: '#aaa',
};

const urlBox: React.CSSProperties = {
  margin: '12px 0',
  padding: '8px 12px',
  background: '#222',
  borderRadius: '6px',
  maxWidth: '80%',
  overflowWrap: 'break-word',
};

const errorText: React.CSSProperties = {
  color: '#ff7777',
  maxWidth: '600px',
};

const actions: React.CSSProperties = {
  display: 'flex',
  gap: '12px',
  marginTop: '20px',
};

const retryBtn: React.CSSProperties = {
  padding: '8px 16px',
  borderRadius: '20px',
  border: 'none',
  cursor: 'pointer',
};

const homeBtn: React.CSSProperties = {
  padding: '8px 16px',
  borderRadius: '20px',
  border: 'none',
  background: '#333',
  color: 'white',
  cursor: 'pointer',
};
