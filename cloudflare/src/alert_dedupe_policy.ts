export interface AlertDedupeState {
  last_committed_at: number | null;
  pending_token: string | null;
  pending_until: number | null;
}

export interface AlertClaim {
  allowed: boolean;
  token: string | null;
  state: AlertDedupeState;
}

const PENDING_LEASE_MS = 60_000;

export const claimAlert = (
  stored: AlertDedupeState | undefined,
  now: number,
  windowMs: number,
  token: string,
): AlertClaim => {
  const state = stored ?? emptyState();
  const recentlyCommitted =
    state.last_committed_at !== null && now - state.last_committed_at < windowMs;
  const activelyPending =
    state.pending_token !== null &&
    state.pending_until !== null &&
    state.pending_until > now;
  if (recentlyCommitted || activelyPending) {
    return { allowed: false, token: null, state };
  }
  return {
    allowed: true,
    token,
    state: {
      last_committed_at: state.last_committed_at,
      pending_token: token,
      pending_until: now + PENDING_LEASE_MS,
    },
  };
};

export const commitAlert = (
  stored: AlertDedupeState | undefined,
  token: string,
  now: number,
): AlertDedupeState | null => {
  if (!stored || stored.pending_token !== token) {
    return null;
  }
  return {
    last_committed_at: now,
    pending_token: null,
    pending_until: null,
  };
};

export const releaseAlert = (
  stored: AlertDedupeState | undefined,
  token: string,
): AlertDedupeState | null => {
  if (!stored || stored.pending_token !== token) {
    return null;
  }
  return {
    last_committed_at: stored.last_committed_at,
    pending_token: null,
    pending_until: null,
  };
};

const emptyState = (): AlertDedupeState => ({
  last_committed_at: null,
  pending_token: null,
  pending_until: null,
});
