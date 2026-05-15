type LogFields = Record<string, unknown>;
function scrub(fields: LogFields = {}) {
  const clone = { ...fields };
  delete clone.text; delete clone.plainText; delete clone.password; delete clone.token;
  return clone;
}
export const logger = {
  info: (fields: LogFields, message: string) => console.log(JSON.stringify({ level: 'info', message, ...scrub(fields) })),
  warn: (fields: LogFields, message: string) => console.warn(JSON.stringify({ level: 'warn', message, ...scrub(fields) })),
  error: (fields: LogFields, message: string) => console.error(JSON.stringify({ level: 'error', message, ...scrub(fields) })),
};
export async function measure<T>(name: string, fn: () => Promise<T>): Promise<{ value: T; durationMs: number; name: string }> {
  const start = performance.now();
  const value = await fn();
  return { name, value, durationMs: Math.round((performance.now() - start) * 100) / 100 };
}
