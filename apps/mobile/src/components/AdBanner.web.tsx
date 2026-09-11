import React from 'react';

/**
 * Web build of the AdMob banner: nothing.
 *
 * This file exists because Metro resolves `.web.tsx` ahead of `.tsx` on web,
 * which keeps `react-native-google-mobile-ads` out of the web dependency graph
 * entirely. A `Platform.OS` check inside the native file is not enough — Metro
 * still follows the import while bundling, and the SDK's native-only internals
 * then fail to resolve at build time.
 *
 * Ads on the website are a separate product (AdSense) and a separate decision.
 */
export function AdBanner() {
  return null;
}
