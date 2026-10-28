export interface QueueMetricsObservation {
  healthy: boolean;
  observed_at: number;
}

export interface QueueMetricsHealthState {
  last_observed_at: number;
  first_failure_at: number | null;
  failures: number;
}

const MIN_FAILURES = 3;
const MIN_FAILURE_DURATION_MS = 120_000;
const MAX_OBSERVATION_GAP_MS = 150_000;

export const observeQueueMetrics = (
  stored: QueueMetricsHealthState | undefined,
  observation: QueueMetricsObservation,
): { state: QueueMetricsHealthState; sustained: boolean } => {
  if (stored && observation.observed_at <= stored.last_observed_at) {
    return {
      state: stored,
      // A duplicate can retry failed alert publication, but cannot add failures.
      sustained: observation.observed_at === stored.last_observed_at &&
        !observation.healthy && isSustained(stored),
    };
  }
  const continuing = stored && stored.failures > 0 &&
    observation.observed_at - stored.last_observed_at <= MAX_OBSERVATION_GAP_MS;
  const state: QueueMetricsHealthState = {
    last_observed_at: observation.observed_at,
    first_failure_at: observation.healthy
      ? null
      : continuing ? stored.first_failure_at : observation.observed_at,
    failures: observation.healthy ? 0 : continuing ? stored.failures + 1 : 1,
  };
  return { state, sustained: isSustained(state) };
};

const isSustained = (state: QueueMetricsHealthState): boolean =>
  state.failures >= MIN_FAILURES && state.first_failure_at !== null &&
  state.last_observed_at - state.first_failure_at >= MIN_FAILURE_DURATION_MS;

export const parseQueueMetricsObservation = (
  value: unknown,
): QueueMetricsObservation | null => {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  return Object.keys(record).length === 2 &&
      typeof record.healthy === "boolean" &&
      typeof record.observed_at === "number" &&
      Number.isFinite(record.observed_at) && record.observed_at >= 0
    ? { healthy: record.healthy, observed_at: record.observed_at }
    : null;
};
