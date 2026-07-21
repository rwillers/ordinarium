export type RateLimitCounter = {
  count: number;
  window_started_at: number;
};

export type RateLimitOutcome = {
  success: boolean;
  retry_after_seconds: number;
  remaining: number;
};

export const consumeRateLimit = (
  stored: RateLimitCounter | undefined,
  now: number,
  limit: number,
  windowMs = 60_000,
): { counter: RateLimitCounter; outcome: RateLimitOutcome } => {
  const counter =
    stored && now - stored.window_started_at < windowMs
      ? { ...stored }
      : { count: 0, window_started_at: now };
  if (counter.count >= limit) {
    return {
      counter,
      outcome: {
        success: false,
        retry_after_seconds: Math.max(
          1,
          Math.ceil((counter.window_started_at + windowMs - now) / 1000),
        ),
        remaining: 0,
      },
    };
  }
  counter.count += 1;
  return {
    counter,
    outcome: {
      success: true,
      retry_after_seconds: 0,
      remaining: Math.max(0, limit - counter.count),
    },
  };
};
