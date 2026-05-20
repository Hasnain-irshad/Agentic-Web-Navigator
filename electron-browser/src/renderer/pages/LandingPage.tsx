import { useState } from 'react';
import logo from '../../../assets/logo.png';

interface Props {
  onNavigate: (url: string) => void; // callback to tell App.tsx to open a URL
}

export default function LandingPage({ onNavigate }: Props) {
  const [input, setInput] = useState('');

  const handleSubmit = () => {
    let finalUrl = input.trim();

    if (!finalUrl) return;

    // If it looks like a URL, use it directly, otherwise search on Google
    if (!/^https?:\/\//i.test(finalUrl)) {
      // If it contains spaces, assume it's a search query
      if (/\s/.test(finalUrl) || !finalUrl.includes('.')) {
        finalUrl = `https://www.google.com/search?q=${encodeURIComponent(finalUrl)}`;
      } else {
        finalUrl = 'https://' + finalUrl;
      }
    }

    onNavigate(finalUrl);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSubmit();
  };

  return (
    <div style={containerStyle}>
      <div style={brandStyle}>
        <img
          src={logo}
          alt="NaviGo logo"
          style={logoImageStyle}
        />
        <h1 style={logoTextStyle}>NaviGo</h1>
      </div>

      <p style={taglineStyle}>Your gateway to the web</p>
      <div style={inputContainerStyle}>
        <input
          style={inputStyle}
          placeholder="Enter a URL or search..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button style={buttonStyle} onClick={handleSubmit}>
          Go
        </button>
      </div>
    </div>
  );
}

/* ---------- Styles ---------- */
const containerStyle: React.CSSProperties = {
  height: '100vh',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'linear-gradient(135deg, #1f1f1f, #3a3a3a)',
  color: 'white',
  fontFamily: 'Arial, sans-serif',
  textAlign: 'center',
};

const brandStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  marginBottom: '10px',
};

const logoImageStyle: React.CSSProperties = {
  height: '120px', // matches text size visually
  width: 'auto',
};

const logoTextStyle: React.CSSProperties = {
  fontSize: '64px',
  margin: 0,
};

const logoStyle: React.CSSProperties = {
  fontSize: '64px',
  marginBottom: '10px',
};

const taglineStyle: React.CSSProperties = {
  fontSize: '18px',
  color: '#ccc',
  marginBottom: '30px',
};

const inputContainerStyle: React.CSSProperties = {
  display: 'flex',
  width: '600px',
  maxWidth: '90%',
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: '12px 16px',
  borderRadius: '30px 0 0 30px',
  border: 'none',
  outline: 'none',
  fontSize: '16px',
};

const buttonStyle: React.CSSProperties = {
  padding: '12px 20px',
  borderRadius: '0 30px 30px 0',
  border: 'none',
  backgroundColor: '#dd9a0a',
  color: 'white',
  fontWeight: 'bold',
  cursor: 'pointer',
};
