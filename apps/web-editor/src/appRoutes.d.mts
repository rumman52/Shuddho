export type StandaloneAppRoute = "coworker" | "writing" | "home" | "default";
export type WorkspaceAppRoute = "coworker" | "writing" | "home";
export function getStandaloneAppRoute(pathname: string): StandaloneAppRoute;
export function getWorkspaceAppRoute(pathname: string, coworkerEnabled?: boolean): WorkspaceAppRoute;
