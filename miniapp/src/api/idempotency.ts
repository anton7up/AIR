type PendingEvent = {
  key: string;
  promise?: Promise<unknown>;
  failedAt?: number;
};

export class EventRequestRegistry {
  private readonly pending = new Map<string, PendingEvent>();

  constructor(
    private readonly createKey: () => string,
    private readonly retryTtlMs = 10 * 60 * 1000,
  ) {}

  run<T>(
    fingerprint: string,
    request: (key: string) => Promise<T>,
    isNetworkError: (error: unknown) => boolean,
  ): Promise<T> {
    let operation = this.pending.get(fingerprint);
    if (
      !operation
      || (operation.failedAt !== undefined
        && Date.now() - operation.failedAt > this.retryTtlMs)
    ) {
      operation = { key: this.createKey() };
      this.pending.set(fingerprint, operation);
    }
    if (operation.promise) return operation.promise as Promise<T>;

    const current = operation;
    const promise = request(current.key);
    current.promise = promise;
    return promise.then(result => {
      this.pending.delete(fingerprint);
      return result;
    }).catch(error => {
      if (isNetworkError(error)) {
        current.promise = undefined;
        current.failedAt = Date.now();
      } else {
        this.pending.delete(fingerprint);
      }
      throw error;
    });
  }
}
