import { app } from 'electron';
import fs from 'fs';
import path from 'path';

export type HistoryItem = {
  url: string;
  title?: string;
  timestamp: number;
};

let HISTORY_FILE: string;

/**
 * Initialize the history file.
 * Must be called after app.whenReady()
 */
export function initHistoryFile() {
  if (!app.isReady()) {
    throw new Error('initHistoryFile must be called after app.whenReady()');
  }

  HISTORY_FILE = path.join(app.getPath('userData'), 'history.json');

  if (!fs.existsSync(HISTORY_FILE)) {
    fs.writeFileSync(HISTORY_FILE, '[]', 'utf-8');
  }
}

/**
 * Read all history items
 */
export function readHistory(): HistoryItem[] {
  if (!HISTORY_FILE) throw new Error('History file not initialized');
  try {
    const data = fs.readFileSync(HISTORY_FILE, 'utf-8');
    return JSON.parse(data) as HistoryItem[];
  } catch (err) {
    console.error('Failed to read history:', err);
    return [];
  }
}

/**
 * Write the entire history array
 */
export function writeHistory(history: HistoryItem[]) {
  if (!HISTORY_FILE) throw new Error('History file not initialized');
  fs.writeFileSync(HISTORY_FILE, JSON.stringify(history, null, 2), 'utf-8');
}

/**
 * Add a new history item.
 * Avoids consecutive duplicates, updates title if URL exists.
 * Keeps maximum of 500 entries.
 */
export function addHistoryItem(item: HistoryItem) {
  const history = readHistory();

  // Check if last added item is same URL
  if (history.length > 0 && history[0].url === item.url) {
    // Update title & timestamp
    history[0].title = item.title || history[0].title;
    history[0].timestamp = item.timestamp;
    writeHistory(history);
    return;
  }

  // Otherwise, insert at the top
  history.unshift(item);

  // Keep max 500 entries
  writeHistory(history.slice(0, 500));
}

/**
 * Delete a single history item by URL
 */
export function deleteHistoryItem(url: string) {
  const history = readHistory();
  const filtered = history.filter((item) => item.url !== url);
  writeHistory(filtered);
}

/**
 * Clear entire history
 */
export function clearHistory() {
  writeHistory([]);
}
