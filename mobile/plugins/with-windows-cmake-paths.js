const { withAppBuildGradle, withGradleProperties } = require("expo/config-plugins");

// CMake 3.22.1 bundles an old Ninja that cannot handle Windows' long native object paths.
// Expo's root Gradle plugin applies this version to the app and every native library.
// Hash object paths too, for machines where Windows long-path support is disabled.

module.exports = function withWindowsCmakePaths(config) {
  config = withGradleProperties(config, (result) => {
    const properties = {
      "android.cmakeVersion": "3.31.6",
      "expo.android.cmakeObjectPathMax": "240",
      ...(process.env.REDUC_NATIVE_BUILD_ROOT
        ? { "reduc.nativeBuildRoot": process.env.REDUC_NATIVE_BUILD_ROOT.replace(/\\/g, "/") }
        : {}),
    };
    result.modResults = result.modResults.filter(
      (entry) => entry.type !== "property" ||
        (entry.key !== "reduc.nativeBuildRoot" && !Object.hasOwn(properties, entry.key)),
    );
    for (const [key, value] of Object.entries(properties)) {
      result.modResults.push({ type: "property", key, value });
    }
    return result;
  });
  return withAppBuildGradle(config, (result) => {
    const marker = "// REDUC: optional short CMake staging directory";
    if (!result.modResults.contents.includes(marker)) {
      result.modResults.contents += `
${marker}
def reducNativeBuildRoot = findProperty('reduc.nativeBuildRoot')
if (reducNativeBuildRoot) {
    android.externalNativeBuild.cmake.buildStagingDirectory = new File(reducNativeBuildRoot, 'app')
}
`;
    }
    const envMarker = "// REDUC: rebuild the JS bundle when Expo environment files change";
    if (!result.modResults.contents.includes(envMarker)) {
      result.modResults.contents += `
${envMarker}
tasks.matching { it.name.startsWith('createBundle') && it.name.endsWith('JsAndAssets') }.configureEach {
    inputs.files(fileTree(rootProject.file('..')) { include '.env*' })
    inputs.property('reduc.expoPublicEnvironment', providers.environmentVariablesPrefixedBy('EXPO_PUBLIC_'))
}
`;
    }
    return result;
  });
};
