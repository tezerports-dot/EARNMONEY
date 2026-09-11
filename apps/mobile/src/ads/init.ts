import mobileAds from 'react-native-google-mobile-ads';

/**
 * Starts the Google Mobile Ads SDK.
 *
 * Native builds only. The web build resolves init.web.ts instead, which keeps
 * the ads SDK out of the browser bundle entirely — a `Platform.OS` check is
 * not enough, because Metro follows the import while bundling and the SDK's
 * native-only internals then fail to resolve at build time.
 */
export function initialiseAds(): void {
  void mobileAds().initialize();
}
