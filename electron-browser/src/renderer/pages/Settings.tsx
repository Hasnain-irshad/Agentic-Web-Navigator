export default function Settings() {
  return (
    <div style={pageStyle}>
      <h1>⚙️ Settings</h1>
      <p>Configure your browser here.</p>
    </div>
  );
}

const pageStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  height: '100%',
  fontFamily: 'Arial, sans-serif',
};
