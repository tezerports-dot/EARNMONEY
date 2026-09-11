/**
 * Expo's Babel preset. It supplies the JSX runtime, the module resolution the
 * web build needs (react-native → react-native-web), and the platform-file
 * extension order. Without this file the web bundle reaches into React
 * Native's native-only internals and fails to resolve.
 */
module.exports = function (api) {
  api.cache(true);
  return { presets: ['babel-preset-expo'] };
};
