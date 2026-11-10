import { AccessibilityInfo } from "react-native";

/** Speak an important change through the screen reader (docs/07 §5). */
export function announce(message: string): void {
  try {
    AccessibilityInfo.announceForAccessibility(message);
  } catch {
    // Not every platform implements announcements; visible text carries the same message.
  }
}
