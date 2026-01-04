/**
 * Electron IPC Message types
 */

/**
 * Message structure sent from backend via Electron IPC
 */
export interface BackendMessage {
  type: string;
  data?: any;
  success?: boolean;
  error?: string;
  message?: string;
  [key: string]: any; // Allow additional properties
}

/**
 * Response structure from backend commands
 */
export interface BackendResponse extends BackendMessage {
  id?: number;
  success?: boolean;
  error?: string;
  message?: string;
  folders?: any[];
  mountpoints?: any[];
  [key: string]: any;
}

/**
 * Common message types
 */
export enum MessageType {
  SyncFolders = 'sync_folders',
  SyncStats = 'sync_stats',
  SystemInfo = 'system_info',
  RaidStatus = 'raid_status',
  Error = 'error',
}
