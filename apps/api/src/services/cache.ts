export interface CacheClient {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, ttlSeconds?: number): Promise<void>;
}

export class MemoryCache implements CacheClient {
  private values = new Map<string, { value: string; expiresAt?: number }>();
  async get(key: string): Promise<string | null> {
    const item = this.values.get(key);
    if (!item) return null;
    if (item.expiresAt && item.expiresAt < Date.now()) {
      this.values.delete(key);
      return null;
    }
    return item.value;
  }
  async set(key: string, value: string, ttlSeconds?: number): Promise<void> {
    this.values.set(key, { value, expiresAt: ttlSeconds ? Date.now() + ttlSeconds * 1000 : undefined });
  }
}
