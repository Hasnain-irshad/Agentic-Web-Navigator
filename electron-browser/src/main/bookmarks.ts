import { app } from 'electron';
import fs from 'fs';
import path from 'path';

export type BookmarkItem = {
  url: string;
  title?: string;
  timestamp: number; // when it was added
};

let BOOKMARK_FILE: string;

export function initBookmarkFile() {
  if (!app.isReady()) throw new Error('initBookmarkFile must be called after app.whenReady()');

  BOOKMARK_FILE = path.join(app.getPath('userData'), 'bookmarks.json');

  if (!fs.existsSync(BOOKMARK_FILE)) {
    fs.writeFileSync(BOOKMARK_FILE, '[]', 'utf-8');
  }
}

export function readBookmarks(): BookmarkItem[] {
  if (!BOOKMARK_FILE) throw new Error('Bookmark file not initialized');
  try {
    const data = fs.readFileSync(BOOKMARK_FILE, 'utf-8');
    return JSON.parse(data) as BookmarkItem[];
  } catch (err) {
    console.error('Failed to read bookmarks:', err);
    return [];
  }
}

export function writeBookmarks(items: BookmarkItem[]) {
  if (!BOOKMARK_FILE) throw new Error('Bookmark file not initialized');
  fs.writeFileSync(BOOKMARK_FILE, JSON.stringify(items, null, 2), 'utf-8');
}

export function addBookmark(item: BookmarkItem) {
  const bookmarks = readBookmarks();

  // Avoid duplicates
  if (bookmarks.some(b => b.url === item.url)) return;

  bookmarks.unshift(item);
  writeBookmarks(bookmarks.slice(0, 500)); // optional limit
}

export function deleteBookmark(url: string) {
  const bookmarks = readBookmarks();
  const filtered = bookmarks.filter(b => b.url !== url);
  writeBookmarks(filtered);
}

export function clearBookmarks() {
  writeBookmarks([]);
}
