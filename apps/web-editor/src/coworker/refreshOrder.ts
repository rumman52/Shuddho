/** P-01: monotonically fence overlapping conversation refresh responses. */
export class RefreshOrder {
  private revision = 0;

  start(): number {
    this.revision += 1;
    return this.revision;
  }

  invalidate(): void {
    this.revision += 1;
  }

  isCurrent(revision: number): boolean {
    return revision === this.revision;
  }
}
