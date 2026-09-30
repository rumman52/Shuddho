export type NotificationCoworkerView = "automations";

export function requestedNotificationView(search: string): NotificationCoworkerView | null {
  try {
    return new URLSearchParams(search).get("view") === "automations" ? "automations" : null;
  } catch {
    return null;
  }
}
