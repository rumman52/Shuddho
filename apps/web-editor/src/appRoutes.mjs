function normalizePath(pathname) {
  return String(pathname ?? "/").split(/[?#]/, 1)[0].replace(/\/+$/, "") || "/";
}

export function getStandaloneAppRoute(pathname) {
  const path = normalizePath(pathname);
  // Provider redirects must return to the Coworker app so its callback
  // handler can validate state and finish the owner-scoped connection.
  if (["/oauth/google/callback", "/oauth/microsoft/callback", "/oauth/linkedin/callback"].includes(path)) return "coworker";
  if (path === "/coworker" || path.startsWith("/coworker/")) return "coworker";
  if (path === "/editor" || path.startsWith("/editor/")) return "editor";
  if (path === "/workspaces" || path.startsWith("/workspaces/")) return "home";
  return "default";
}

export function getWorkspaceAppRoute(pathname, coworkerEnabled = false) {
  const path = normalizePath(pathname);
  const route = getStandaloneAppRoute(path);
  if (route === "default") return path === "/" && coworkerEnabled ? "coworker" : "home";
  // Keep the execution rollout closed while making the requested workspace
  // discoverable. OAuth callbacks never enter the public draft surface.
  if (route === "coworker" && !coworkerEnabled) return path.startsWith("/coworker") ? "coworker-preview" : "home";
  return route;
}
