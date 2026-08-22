const D1_READ_RETRY_DELAYS_MS = [250, 1_000, 2_500] as const;

const RETRYABLE_D1_ERROR_FRAGMENTS = [
  "Network connection lost",
  "caused object to be reset",
  "reset because its code was updated",
  "Cannot resolve D1 DB due to transient issue",
  "Replica disconnected from primary",
  "D1 DB is overloaded. Requests queued for too long.",
  "D1 DB is overloaded. Too many requests queued.",
] as const;

export interface D1ReadRetryEvent {
  error: unknown;
  attempts: number;
  retryDelayMs: number;
}

export interface D1ReadRetryOptions {
  sleep?: (milliseconds: number) => Promise<void>;
  random?: () => number;
  onRetry?: (event: D1ReadRetryEvent) => void;
}

export const retryD1Read = async <T>(
  operation: () => Promise<T>,
  options: D1ReadRetryOptions = {},
): Promise<T> => {
  const sleep = options.sleep ?? wait;
  const random = options.random ?? Math.random;
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation();
    } catch (error: unknown) {
      const delay = D1_READ_RETRY_DELAYS_MS[attempt];
      if (delay === undefined || !isRetryableD1ReadError(error)) {
        throw error;
      }
      const retryDelayMs = jitteredDelay(delay, random());
      options.onRetry?.({
        error,
        attempts: attempt + 1,
        retryDelayMs,
      });
      await sleep(retryDelayMs);
    }
  }
};

export const isRetryableD1ReadError = (error: unknown): boolean => {
  const message = error instanceof Error ? error.message : String(error);
  return RETRYABLE_D1_ERROR_FRAGMENTS.some((fragment) =>
    message.includes(fragment),
  );
};

const jitteredDelay = (baseDelayMs: number, randomValue: number): number =>
  Math.round(baseDelayMs * (0.75 + Math.min(1, Math.max(0, randomValue)) * 0.5));

const wait = (milliseconds: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));
