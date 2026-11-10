// Allows plain-HTTP requests on Android. Applied by app.config.js ONLY when the API or tile
// URL of the build is http:// (a development machine on the local network). Builds that
// point to HTTPS servers keep Android's default and reject cleartext traffic.
const { withAndroidManifest } = require("expo/config-plugins");

module.exports = function withCleartextTraffic(config) {
  return withAndroidManifest(config, (result) => {
    const application = result.modResults.manifest.application?.[0];
    if (application) {
      application.$["android:usesCleartextTraffic"] = "true";
    }
    return result;
  });
};
