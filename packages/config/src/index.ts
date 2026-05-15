export interface ApiEnv { NODE_ENV: string; PORT: number; DATABASE_URL: string; REDIS_URL: string; API_AUTH_TOKEN: string; CORS_ORIGIN: string; MAX_TEXT_CHARS: number; }
export const loadApiEnv = (source = process.env): ApiEnv => ({
  NODE_ENV: source.NODE_ENV ?? 'development',
  PORT: Number(source.PORT ?? 4000),
  DATABASE_URL: source.DATABASE_URL ?? 'postgresql://shuddho:shuddho@localhost:5432/shuddho',
  REDIS_URL: source.REDIS_URL ?? 'redis://localhost:6379',
  API_AUTH_TOKEN: source.API_AUTH_TOKEN ?? 'dev-token',
  CORS_ORIGIN: source.CORS_ORIGIN ?? 'http://localhost:3000',
  MAX_TEXT_CHARS: Number(source.MAX_TEXT_CHARS ?? 20000),
});
