/**
 * Secure Token Storage using OS Keyring
 * 
 * Uses electron's safeStorage for secure credential storage.
 * Falls back to sessionStorage in development/web mode.
 */

const TOKEN_KEY = 'baludesk-api-token';
const USERNAME_KEY = 'baludesk-username';

/**
 * Check if we're running in Electron environment
 */
function isElectron(): boolean {
  return typeof window !== 'undefined' && 
         window.electronAPI !== undefined &&
         window.electronAPI.safeStorage !== undefined;
}

/**
 * Store authentication token securely
 */
export async function storeToken(token: string, username: string): Promise<void> {
  if (isElectron()) {
    try {
      // Use Electron's safeStorage API for encrypted storage
      await window.electronAPI!.safeStorage.setItem(TOKEN_KEY, token);
      await window.electronAPI!.safeStorage.setItem(USERNAME_KEY, username);
      console.log('[SecureStore] Token stored securely in OS keyring');
    } catch (error) {
      console.error('[SecureStore] Failed to store token:', error);
      throw new Error('Failed to store authentication token securely');
    }
  } else {
    // Fallback to sessionStorage in dev/web mode (NOT secure for production!)
    console.warn('[SecureStore] Using sessionStorage (dev mode only - not secure!)');
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USERNAME_KEY, username);
  }
}

/**
 * Retrieve stored authentication token
 */
export async function getToken(): Promise<string | null> {
  if (isElectron()) {
    try {
      const token = await window.electronAPI!.safeStorage.getItem(TOKEN_KEY);
      return token || null;
    } catch (error) {
      console.error('[SecureStore] Failed to retrieve token:', error);
      return null;
    }
  } else {
    return sessionStorage.getItem(TOKEN_KEY);
  }
}

/**
 * Retrieve stored username
 */
export async function getStoredUsername(): Promise<string | null> {
  if (isElectron()) {
    try {
      const username = await window.electronAPI!.safeStorage.getItem(USERNAME_KEY);
      return username || null;
    } catch (error) {
      console.error('[SecureStore] Failed to retrieve username:', error);
      return null;
    }
  } else {
    return sessionStorage.getItem(USERNAME_KEY);
  }
}

/**
 * Clear stored authentication data
 */
export async function clearToken(): Promise<void> {
  if (isElectron()) {
    try {
      await window.electronAPI!.safeStorage.deleteItem(TOKEN_KEY);
      await window.electronAPI!.safeStorage.deleteItem(USERNAME_KEY);
      console.log('[SecureStore] Token cleared from OS keyring');
    } catch (error) {
      console.error('[SecureStore] Failed to clear token:', error);
    }
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USERNAME_KEY);
  }
}

/**
 * Check if user is authenticated (has valid token)
 */
export async function isAuthenticated(): Promise<boolean> {
  const token = await getToken();
  return token !== null && token.length > 0;
}
