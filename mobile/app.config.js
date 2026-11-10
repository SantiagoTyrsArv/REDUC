// Extends app.json. The only dynamic part: local builds that talk to an http:// backend
// (EXPO_PUBLIC_API_URL / EXPO_PUBLIC_TILES_URL) need cleartext traffic enabled on Android.
module.exports = ({ config }) => {
  const urls = [process.env.EXPO_PUBLIC_API_URL, process.env.EXPO_PUBLIC_TILES_URL];
  const usesHttp = urls.some((url) => typeof url === "string" && url.trim().toLowerCase().startsWith("http://"));
  return {
    ...config,
    plugins: [...(config.plugins ?? []), ...(usesHttp ? ["./plugins/with-cleartext-traffic"] : [])],
  };
};
