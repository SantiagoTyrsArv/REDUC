import "../src/i18n";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useLocationWatcher } from "../src/features/location/useLocation";
import { useActiveRegionSync } from "../src/features/region/useActiveRegion";
import { useTheme } from "../src/theme";

function AppServices() {
  useActiveRegionSync();
  useLocationWatcher();
  return null;
}

export default function RootLayout() {
  const { t } = useTranslation();
  const { colors, isDark } = useTheme();
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } }),
  );

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AppServices />
        <StatusBar style={isDark ? "light" : "dark"} />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.background },
            headerTintColor: colors.text,
            headerBackTitle: t("common.back"),
            contentStyle: { backgroundColor: colors.background },
          }}
        >
          <Stack.Screen name="index" options={{ title: t("nav.map"), headerShown: false }} />
          <Stack.Screen name="onboarding" options={{ title: t("nav.onboarding"), headerShown: false }} />
          <Stack.Screen name="search" options={{ title: t("nav.search") }} />
          <Stack.Screen name="route/index" options={{ title: t("nav.route") }} />
          <Stack.Screen name="route/segments" options={{ title: t("nav.segments") }} />
          <Stack.Screen name="navigate" options={{ title: t("nav.navigate"), headerBackVisible: false }} />
          <Stack.Screen name="barrier/[id]" options={{ title: t("nav.barrier") }} />
          <Stack.Screen name="profiles/index" options={{ title: t("nav.profiles") }} />
          <Stack.Screen name="profiles/[id]" options={{ title: t("nav.editProfile") }} />
          <Stack.Screen name="settings" options={{ title: t("nav.settings") }} />
        </Stack>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
