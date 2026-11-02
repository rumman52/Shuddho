export function getStandaloneAppRoute(pathname) {
  const path = pathname.split(/[?#]/, 1)[0].replace(/\/+$/, "") || "/";
  if (path === "/coworker" || path.startsWith("/coworker/")) return "coworker";
  if (path === "/editor" || path.startsWith("/editor/")) return "editor";
  return "default";
}

export function getWorkspaceAppRoute(pathname, coworkerEnabled = false) {
  const route = getStandaloneAppRoute(pathname);
  if (!coworkerEnabled && route !== "editor") return "editor";
  return route;
}
