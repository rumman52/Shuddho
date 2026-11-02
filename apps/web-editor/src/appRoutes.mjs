export function getStandaloneAppRoute(pathname) {
  const path = String(pathname ?? "/").split(/[?#]/, 1)[0].replace(/\/+$/, "") || "/";
  if (path === "/coworker" || path.startsWith("/coworker/")) return "coworker";
  if (path === "/editor" || path.startsWith("/editor/")) return "editor";
  return "default";
}

export function getWorkspaceAppRoute(pathname, coworkerEnabled = false) {
  const route = getStandaloneAppRoute(pathname);
  if (route === "default") return "home";
  if (route === "coworker" && !coworkerEnabled) return "home";
  return route;
}
