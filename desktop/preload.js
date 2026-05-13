const { contextBridge, ipcMain } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  platform: process.platform,
  getPlatform: () => ipcMain.invoke('get-platform'),
  getVersion: () => ipcMain.invoke('get-version'),
});
