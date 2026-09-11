/**
 * Web build of the CSRF token store.
 *
 * `expo-secure-store` wraps the Android keystore and has no browser
 * implementation, so it must stay out of the web bundle altogether — Metro
 * resolves this `.web.ts` file first on web, which is why the native file can
 * import it directly.
 *
 * `localStorage` is the right home for this value and not a downgrade: the
 * CSRF token is a double-submit value the page is *meant* to be able to read.
 * The session itself lives in an httpOnly cookie that JavaScript never sees.
 */
export const secureStorage = {
  async get(key: string): Promise<string | null> {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      // Private mode, or site data blocked. Sign-in must still work.
      return null;
    }
  },

  async set(key: string, value: string | null): Promise<void> {
    try {
      if (value) globalThis.localStorage?.setItem(key, value);
      else globalThis.localStorage?.removeItem(key);
    } catch {
      // As above.
    }
  },
};
