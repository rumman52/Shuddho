export type StandaloneAppRoute = "coworker" | "editor" | "default";
export type WorkspaceAppRoute = "coworker" | "editor" | "home";
export function getStandaloneAppRoute(pathname: string): StandaloneAppRoute;
export function getWorkspaceAppRoute(pathname: string, coworkerEnabled?: boolean): WorkspaceAppRoute;
