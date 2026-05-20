/* eslint global-require: off, no-console: off, promise/always-return: off */

/**
 * This module executes inside of electron's main process. You can start
 * electron renderer process from here and communicate with the other processes
 * through IPC.
 *
 * When running `npm run build` or `npm run build:main`, this file is compiled to
 * `./src/main.js` using webpack. This gives us some performance wins.
 */
import path from 'path';
import { app, BrowserWindow, shell, ipcMain, globalShortcut } from 'electron';
import { autoUpdater } from 'electron-updater';
import log from 'electron-log';
import { resolveHtmlPath } from './util';
import { initHistoryFile, addHistoryItem, readHistory, HistoryItem, writeHistory } from './history';
import { initBookmarkFile, addBookmark, readBookmarks, deleteBookmark, clearBookmarks, BookmarkItem } from './bookmarks';

class AppUpdater {
  constructor() {
    log.transports.file.level = 'info';
    autoUpdater.logger = log;
    autoUpdater.checkForUpdatesAndNotify();
  }
}

process.env['ELECTRON_DISABLE_SECURITY_WARNINGS'] = 'true';
app.commandLine.appendSwitch('disable-features', 'WebAuthentication');

let mainWindow: BrowserWindow | null = null;

ipcMain.on('ipc-example', async (event, arg) => {
  const msgTemplate = (pingPong: string) => `IPC test: ${pingPong}`;
  console.log(msgTemplate(arg));
  event.reply('ipc-example', msgTemplate('pong'));
});

ipcMain.on('navigate', (_, url: string) => {
  mainWindow?.webContents.send('navigate-to', url);
});

// // add item to history
// ipcMain.on('history-add', (_, item: HistoryItem) => {
//   addHistoryItem(item);
//   console.log('History added:', item.url); // debug
// });

// // get history for renderer
// ipcMain.handle('history-get', () => {
//   return readHistory();
// });


if (process.env.NODE_ENV === 'production') {
  const sourceMapSupport = require('source-map-support');
  sourceMapSupport.install();
}

const isDebug =
  process.env.NODE_ENV === 'development' || process.env.DEBUG_PROD === 'true';

if (isDebug) {
  require('electron-debug').default({ showDevTools: false });
}

const installExtensions = async () => {
  const installer = require('electron-devtools-installer');
  const forceDownload = !!process.env.UPGRADE_EXTENSIONS;
  const extensions = ['REACT_DEVELOPER_TOOLS'];

  return installer
    .default(
      extensions.map((name) => installer[name]),
      forceDownload,
    )
    .catch(console.log);
};

const createWindow = async () => {
  if (isDebug) {
    await installExtensions();
  }

  const RESOURCES_PATH = app.isPackaged
    ? path.join(process.resourcesPath, 'assets')
    : path.join(__dirname, '../../assets');

  const getAssetPath = (...paths: string[]): string => {
    return path.join(RESOURCES_PATH, ...paths);
  };

  mainWindow = new BrowserWindow({
  show: false,
  width: 1024,
  height: 728,
  icon: getAssetPath('logo.png'),
  webPreferences: {
    preload: app.isPackaged
      ? path.join(__dirname, 'preload.js')
      : path.join(__dirname, '../../.erb/dll/preload.js'),
    contextIsolation: true,
    nodeIntegration: false,
    webviewTag: true,           // Enable <webview>
    webSecurity: false,         // Important for sites that block embedding
    allowRunningInsecureContent: true, // optional if you want http content
  },
});


  mainWindow.loadURL(resolveHtmlPath('index.html'));

  mainWindow.on('ready-to-show', () => {
    if (!mainWindow) {
      throw new Error('"mainWindow" is not defined');
    }
    if (process.env.START_MINIMIZED) {
      mainWindow.minimize();
    } else {
      mainWindow.show();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

mainWindow.setMenuBarVisibility(false); // hide the menu
mainWindow.autoHideMenuBar = true; 

  // Open urls in the user's browser
  mainWindow.webContents.setWindowOpenHandler((edata) => {
    shell.openExternal(edata.url);
    return { action: 'deny' };
  });

  // Remove this if your app does not use auto updates
  // eslint-disable-next-line
  new AppUpdater();
};

/**
 * Add event listeners...
 */

app.on('window-all-closed', () => {
  // Respect the OSX convention of having the application in memory even
  // after all windows have been closed
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app
  .whenReady()
  .then(() => {
    initHistoryFile(); // initialize JSON file
    initBookmarkFile();

    createWindow();
    app.on('activate', () => {
      // On macOS it's common to re-create a window in the app when the
      // dock icon is clicked and there are no other windows open.
      if (mainWindow === null) createWindow();
    });
    // globalShortcut.register('Alt', () => {
    // if (mainWindow) {
    //   mainWindow.setMenuBarVisibility(!mainWindow.isMenuBarVisible());
    // }
  // });
  })
  .catch(console.log);
// 2️⃣ Listen for history-add messages
ipcMain.on('history-add', (_, item: HistoryItem) => {
  addHistoryItem(item);
});

// 3️⃣ Provide history-get for renderer
ipcMain.handle('history-get', () => {
  return readHistory();
});

// Delete a single history item by timestamp
ipcMain.on('history-delete', (_, timestamp: number) => {
  const history = readHistory();
  const filtered = history.filter((item) => item.timestamp !== timestamp);
  writeHistory(filtered);
});


// Clear all history
ipcMain.on('history-clear', () => {
  writeHistory([]);
});

// Optional: allow clicking a history item to navigate
ipcMain.on('navigate-to', (_, url: string) => {
  if (mainWindow) mainWindow.webContents.loadURL(url);
});


// Add bookmark
ipcMain.on('bookmark-add', (_, item: BookmarkItem) => {
  addBookmark(item);
});

// Get bookmarks
ipcMain.handle('bookmark-get', () => {
  return readBookmarks();
});

// Delete bookmark by URL
ipcMain.on('bookmark-delete', (_, url: string) => {
  deleteBookmark(url);
});

// Clear all bookmarks
ipcMain.on('bookmark-clear', () => {
  clearBookmarks();
});
