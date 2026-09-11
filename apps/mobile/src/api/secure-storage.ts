import * as SecureStore from 'expo-secure-store';

/**
 * Native store for the CSRF token, backed by the platform keystore.
 *
 * The web build uses secure-storage.web.ts instead — Metro picks that file on
 * web, so `expo-secure-store`, which has no browser implementation, never
 * enters the web bundle.
 */
export const secureStorage = {
  async get(key: string): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(key);
    } catch {
      // A device with no keystore still works; the next state-changing call
      // simply re-authenticates.
      return null;
    }
  },

  async set(key: string, value: string | null): Promise<void> {
    try {
      if (value) await SecureStore.setItemAsync(key, value);
      else await SecureStore.deleteItemAsync(key);
    } catch {
      // As above.
    }
  },
};
