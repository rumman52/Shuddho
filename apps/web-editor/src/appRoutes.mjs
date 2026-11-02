export function getStandaloneAppRoute(pathname) {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/coworker" || path.startsWith("/coworker/")) return "coworker";
  if (path === "/editor" || path.startsWith("/editor/")) return "editor";
  return "default";
}
