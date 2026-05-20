import { MdArrowBackIos } from 'react-icons/md';

interface Props {
  onBack: () => void;
  title: string;
}

export default function PageHeader({ onBack, title }: Props) {
  return (
    <div style={headerStyle}>
      <button
        style={backButtonStyle}
        onClick={() => onBack()} 
        title="Back"
      >
        <MdArrowBackIos size={20} />
      </button>

      <h2 style={{ margin: 0 }}>{title}</h2>
    </div>
  );
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  padding: '10px 20px',
  borderBottom: '1px solid #333',
  background: '#1e1e1e',
  color: '#fff',
};

const backButtonStyle: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  color: '#fff',
  cursor: 'pointer',
  marginRight: '10px',
};
