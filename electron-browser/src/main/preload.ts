// Disable no-unused-vars, broken for spread args
/* eslint no-unused-vars: off */
import { contextBridge, ipcRenderer, IpcRendererEvent } from 'electron';

// All IPC channels your renderer can use
export type Channels =
  | 'ipc-example'
  | 'navigate-to'
  | 'history-get'
  | 'history-add'
  | 'history-delete'   
  | 'history-clear'
  | 'bookmark-add'
  | 'bookmark-delete'
  | 'bookmark-get'
  | 'bookmark-clear'
  | 'renderer-navigate'; 


const electronHandler = {
  ipcRenderer: {
    // Send a message without expecting a return
    sendMessage(channel: Channels, ...args: unknown[]) {
      ipcRenderer.send(channel, ...args);
    },

    // Listen to a channel continuously
    on(channel: Channels, func: (...args: unknown[]) => void) {
      const subscription = (_event: IpcRendererEvent, ...args: unknown[]) => func(...args);
      ipcRenderer.on(channel, subscription);

      return () => ipcRenderer.removeListener(channel, subscription);
    },

    // Listen once to a channel
    once(channel: Channels, func: (...args: unknown[]) => void) {
      ipcRenderer.once(channel, (_event, ...args) => func(...args));
    },

    // Invoke a channel (expect a promise return)
    invoke(channel: Channels, ...args: unknown[]) {
      return ipcRenderer.invoke(channel, ...args);
    },
  },
};

// Expose to renderer. We expose under TWO names to keep the old `window.electron`
// call sites working AND support the newer `window.electronAPI` convention.
// Both point at the same object — no behavioural difference.
contextBridge.exposeInMainWorld('electron', electronHandler);
contextBridge.exposeInMainWorld('electronAPI', electronHandler);

// TS type for renderer
export type ElectronHandler = typeof electronHandler;
