function normalizePath(pathname) {
  return String(pathname ?? "/").split(/[?#]/, 1)[0].replace(/\/+$/, "") || "/";
}

export function getStandaloneAppRoute(pathname) {
  const path = normalizePath(pathname);
  if (path === "/coworker" || path.startsWith("/coworker/")) return "coworker";
  if (path === "/editor" || path.startsWith("/editor/")) return "editor";
  if (path === "/workspaces" || path.startsWith("/workspaces/")) return "home";
  return "default";
}

export function getWorkspaceAppRoute(pathname, coworkerEnabled = false) {
  const path = normalizePath(pathname);
  const route = getStandaloneAppRoute(path);
  if (route === "default") return path === "/" && coworkerEnabled ? "coworker" : "home";
  if (route === "coworker" && !coworkerEnabled) return "home";
  return route;
}
