import { useEffect, useRef } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  onOptionClick?: (target: 'bookmarks' | 'history' | 'settings') => void;
}

export default function BrowserMenu({ open, onClose, onOptionClick }: Props) {
  const menuRef = useRef<HTMLDivElement>(null);
  const ignoreNextClick = useRef(true);

  useEffect(() => {
    if (!open) return;

    ignoreNextClick.current = true;

    const handleMouseDown = (e: MouseEvent) => {
      if (ignoreNextClick.current) {
        ignoreNextClick.current = false;
        return;
      }

      if (!menuRef.current) return;

      if (!menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div ref={menuRef} style={menuStyle}>
      <MenuItem label="Bookmarks" onClick={() => onOptionClick?.('bookmarks')} />
      <MenuItem label="History" onClick={() => onOptionClick?.('history')} />
      {/* <MenuItem label="Settings" onClick={() => onOptionClick?.('settings')} /> */}
    </div>
  );
}

function MenuItem({ label, onClick }: { label: string; onClick?: () => void }) {
  return (
    <div
      style={menuItemStyle}
      onMouseEnter={(e) => (e.currentTarget.style.background = '#2a2a2a')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
      onClick={onClick}
    >
      {label}
    </div>
  );
}


/* ---------- Styles ---------- */

const menuStyle: React.CSSProperties = {
  position: 'absolute',
  top: '52px',
  right: '10px',
  background: '#393939',
  borderRadius: '12px',
  padding: '6px 0',
  minWidth: '180px',
  boxShadow: '0 8px 30px rgba(0,0,0,0.45)',
  zIndex: 1000,
};

const menuItemStyle: React.CSSProperties = {
  padding: '10px 14px',
  color: '#fff',
  cursor: 'pointer',
  fontSize: '14px',
  userSelect: 'none',
};
