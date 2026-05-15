declare const process: { env: Record<string, string | undefined> };
declare const Buffer: any;
declare module 'node:http' {
  export interface IncomingMessage { method?: string; url?: string; headers: Record<string, string | string[] | undefined>; [Symbol.asyncIterator](): AsyncIterableIterator<unknown>; }
  export interface ServerResponse { statusCode: number; setHeader(name: string, value: string): void; end(body?: string): void; }
  export interface Server { listen(port: number, cb?: () => void): void; on(event: string, cb: (...args: any[]) => void): void; address(): unknown; close(cb?: (err?: Error) => void): void; }
  export function createServer(handler: (req: IncomingMessage, res: ServerResponse) => void): Server;
}
declare module 'node:crypto' { export function randomUUID(): string; export function createHash(algorithm: string): { update(value: string): { digest(encoding: 'base64' | 'hex'): string } }; }
