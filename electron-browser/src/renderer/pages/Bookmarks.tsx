import { useEffect, useState } from 'react';
import { MdDeleteForever } from 'react-icons/md';
import PageHeader from '../components/PageHeader';

type BookmarkItem = { url: string; title?: string; timestamp: number };

interface Props {
  onBack: (url?: string) => void; // optional URL to open in webview
}

export default function Bookmarks({ onBack }: Props) {
  const [bookmarks, setBookmarks] = useState<BookmarkItem[]>([]);

  // Fetch bookmarks from main
  const fetchBookmarks = async () => {
    const items = await window.electron.ipcRenderer.invoke('bookmark-get');
    setBookmarks(items);
  };

  useEffect(() => {
    fetchBookmarks();
  }, []);

  // Delete a single bookmark
  const handleDelete = (url: string) => {
    window.electron.ipcRenderer.sendMessage('bookmark-delete', url);
    setBookmarks((prev) => prev.filter((b) => b.url !== url));
  };

  // Clear all bookmarks
  const handleClearAll = () => {
    if (!confirm('Are you sure you want to delete all bookmarks?')) return;
    window.electron.ipcRenderer.sendMessage('bookmark-clear');
    setBookmarks([]);
  };

  return (
    <div style={pageStyle}>
      <PageHeader onBack={() => onBack()} title="Bookmarks" />

      {bookmarks.length === 0 ? (
        <p style={{ marginTop: 20 }}>No bookmarks yet.</p>
      ) : (
        <>
          <button style={clearButtonStyle} onClick={handleClearAll}>
            <MdDeleteForever /> Clear All
          </button>
          <div style={listStyle}>
            {bookmarks.map((item) => (
              <BookmarkRow
                key={item.timestamp}
                item={item}
                onDelete={handleDelete}
                onBack={onBack}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function BookmarkRow({
  item,
  onDelete,
  onBack,
}: {
  item: BookmarkItem;
  onDelete: (url: string) => void;
  onBack: (url?: string) => void;
}) {
  const [hover, setHover] = useState(false);
  const date = new Date(item.timestamp);

  return (
    <div
      style={{ ...rowStyle, background: hover ? '#2a2a2a' : 'transparent' }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={item.url}
      onClick={() => {
        console.log('CLICKED BOOKMARK:', item.url);
        window.electron.ipcRenderer.sendMessage('renderer-navigate', item.url);
        onBack(item.url); // switch back to webview
      }}
    >
      {/* Left side: title + URL */}
      <div style={textContainerStyle}>
        <div style={titleStyle}>{item.title || item.url}</div>
        <div style={urlStyle}>{item.url}</div>
      </div>

      {/* Right side: timestamp + delete */}
      <div style={rightSideStyle}>
        <div style={timestampStyle}>{date.toLocaleString()}</div>
        <button
          style={deleteButtonStyle}
          onClick={(e) => {
            e.stopPropagation(); // prevent row click
            onDelete(item.url);
          }}
          title="Delete"
        >
          <MdDeleteForever size={18} />
        </button>
      </div>
    </div>
  );
}

/* ---------- Styles ---------- */
const pageStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  padding: '0px 20px 20px 20px',
  fontFamily: 'Arial, sans-serif',
  height: '100%',
};
const listStyle: React.CSSProperties = {
  marginTop: '10px',
  overflowY: 'auto',
  flex: 1,
};
const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '10px',
  borderBottom: '1px solid #333',
  cursor: 'pointer',
  borderRadius: '6px',
  transition: 'background 0.2s',
  gap: '10px',
};
const textContainerStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};
const titleStyle: React.CSSProperties = {
  fontWeight: 500,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};
const urlStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#888',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};
const rightSideStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
};
const timestampStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#888',
};
const clearButtonStyle: React.CSSProperties = {
  marginTop: 10,
  background: 'transparent',
  border: '1px solid #ff5555',
  borderRadius: 6,
  color: '#ff5555',
  cursor: 'pointer',
  padding: '4px 10px',
  display: 'flex',
  alignItems: 'center',
  gap: '4px',
};
const deleteButtonStyle: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  color: '#ff5555',
  cursor: 'pointer',
};
