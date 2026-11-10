// Expo configures Metro for the pnpm workspace automatically (watch folders and node_modules lookup).
const { getDefaultConfig } = require("expo/metro-config");

module.exports = getDefaultConfig(__dirname);
