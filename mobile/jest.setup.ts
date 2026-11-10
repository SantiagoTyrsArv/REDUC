// Test doubles shared by every suite. Tests never touch the network or native modules.
import "./src/i18n";

import { configure } from "@testing-library/react-native";

// Coverage instrumentation slows the first render; give async queries room.
configure({ asyncUtilTimeout: 5000 });
jest.setTimeout(20000);

jest.mock("react-native-mmkv", () => {
  const stores = new Map<string, Map<string, string>>();
  return {
    createMMKV: ({ id }: { id: string }) => {
      const data = stores.get(id) ?? new Map<string, string>();
      stores.set(id, data);
      return {
        getString: (key: string) => data.get(key),
        set: (key: string, value: string) => void data.set(key, value),
        remove: (key: string) => data.delete(key),
      };
    },
  };
});

jest.mock("expo-location", () => ({
  PermissionStatus: { GRANTED: "granted", DENIED: "denied", UNDETERMINED: "undetermined" },
  Accuracy: { High: 4 },
  getForegroundPermissionsAsync: jest.fn(async () => ({ status: "undetermined", canAskAgain: true })),
  requestForegroundPermissionsAsync: jest.fn(async () => ({ status: "granted", canAskAgain: true })),
  watchPositionAsync: jest.fn(async () => ({ remove: jest.fn() })),
}));

// The map needs native code (or WebGL); screens are tested through their text alternative.
jest.mock("./src/features/map/MapCanvas", () => {
  const { View } = jest.requireActual("react-native");
  return {
    MapCanvas: ({ accessibilityLabel }: { accessibilityLabel: string }) => (
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      jest.requireActual("react").createElement(View, { testID: "map-canvas", accessibilityLabel })
    ),
  };
});

jest.mock("@react-native-community/slider", () => {
  const { View } = jest.requireActual("react-native");
  return {
    __esModule: true,
    default: (props: Record<string, unknown>) => jest.requireActual("react").createElement(View, props),
  };
});

const mockRouter = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  dismissTo: jest.fn(),
};
let mockParams: Record<string, string> = {};

jest.mock("expo-router", () => ({
  useRouter: () => mockRouter,
  useLocalSearchParams: () => mockParams,
  Redirect: ({ href }: { href: string }) => {
    const { Text } = jest.requireActual("react-native");
    return jest.requireActual("react").createElement(Text, { testID: "redirect" }, href);
  },
  Stack: Object.assign(() => null, { Screen: () => null }),
}));

(globalThis as Record<string, unknown>).__router = mockRouter;
(globalThis as Record<string, unknown>).__setRouteParams = (params: Record<string, string>) => {
  mockParams = params;
};

beforeEach(() => {
  mockParams = {};
  Object.values(mockRouter).forEach((fn) => fn.mockClear());
});
