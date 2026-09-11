/**
 * Expo's Metro defaults, kept explicit so the web target is configured in the
 * repo rather than inferred. `expo/metro-config` is what aliases react-native
 * to react-native-web and resolves `.web.tsx` ahead of `.tsx` when bundling
 * for the browser.
 */
const { getDefaultConfig } = require('expo/metro-config');

module.exports = getDefaultConfig(__dirname);
