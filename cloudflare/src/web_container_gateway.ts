const TRANSIENT_CONTAINER_FAILURES = [
  {
    status: 429,
    prefix: "you are requesting too many containers per second",
    forceReadinessCheck: false,
  },
  {
    status: 500,
    prefix: "Failed to start container:",
    forceReadinessCheck: true,
  },
  {
    status: 500,
    prefix: "Container suddenly disconnected, try again",
    forceReadinessCheck: true,
  },
  {
    status: 500,
    prefix: "Error proxying request to container:",
    forceReadinessCheck: true,
  },
  {
    status: 503,
    prefix: "There is no Container instance available at this time.",
    forceReadinessCheck: true,
  },
] as const;
const NON_REPLAYABLE_GET_PATHS = new Set(["/integrations/pco/callback"]);
const MAX_TRANSIENT_RESPONSE_BYTES = 512;
const DEFAULT_RETRY_DELAYS_MS = [250, 750] as const;

interface WebContainerStub {
  fetchWithReadiness(
    request: Request,
    forceReadinessCheck: boolean,
  ): Promise<Response>;
}

export type WebContainerResult = {
  response: Response;
  retryOutcome: "none" | "succeeded" | "exhausted";
  attempts: number;
};

type WebContainerFetchOptions = {
  retryDelaysMs?: readonly number[];
  sleep?: (delayMs: number) => Promise<void>;
  random?: () => number;
};

export const fetchWebContainer = async (
  container: WebContainerStub,
  request: Request,
  options: WebContainerFetchOptions = {},
): Promise<WebContainerResult> => {
  const retryDelaysMs = options.retryDelaysMs ?? DEFAULT_RETRY_DELAYS_MS;
  const sleep = options.sleep ?? wait;
  const random = options.random ?? randomFraction;
  const canRetry = isReplaySafeRequest(request);
  const maxAttempts = canRetry ? retryDelaysMs.length + 1 : 1;
  let forceReadinessCheck = false;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    let response: Response;
    try {
      response = await container.fetchWithReadiness(
        attempt === 1 ? request : new Request(request),
        forceReadinessCheck,
      );
    } catch (error: unknown) {
      if (!canRetry || request.signal.aborted) {
        throw error;
      }
      if (attempt === maxAttempts) {
        return exhaustedResult(attempt);
      }
      forceReadinessCheck = true;
      await sleep(jitteredDelay(retryDelaysMs[attempt - 1], random));
      continue;
    }

    if (!canRetry || request.signal.aborted) {
      return { response, retryOutcome: "none", attempts: attempt };
    }
    const failure = await transientContainerFailure(response);
    if (!failure.retry) {
      return {
        response,
        retryOutcome: attempt === 1 ? "none" : "succeeded",
        attempts: attempt,
      };
    }

    await response.body?.cancel();
    if (attempt === maxAttempts) {
      return exhaustedResult(attempt);
    }
    forceReadinessCheck = failure.forceReadinessCheck;
    await sleep(jitteredDelay(retryDelaysMs[attempt - 1], random));
  }

  return exhaustedResult(maxAttempts);
};

const isReplaySafeRequest = (request: Request): boolean => {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return false;
  }

  // The PCO callback consumes a one-time OAuth code before all application
  // persistence has completed. Replaying it can turn a recoverable storage
  // failure into an authorization error because that code is already spent.
  return !NON_REPLAYABLE_GET_PATHS.has(new URL(request.url).pathname);
};

const transientContainerFailure = async (
  response: Response,
): Promise<{ retry: boolean; forceReadinessCheck: boolean }> => {
  const possibleFailures = TRANSIENT_CONTAINER_FAILURES.filter(
    (failure) => failure.status === response.status,
  );
  if (possibleFailures.length === 0) {
    return { retry: false, forceReadinessCheck: false };
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.split(";", 1)[0].trim().toLowerCase() !== "text/plain") {
    return { retry: false, forceReadinessCheck: false };
  }
  const body = await readBoundedText(
    response.clone(),
    MAX_TRANSIENT_RESPONSE_BYTES,
  );
  const failure =
    body === null
      ? undefined
      : possibleFailures.find(({ prefix }) => body.startsWith(prefix));
  return {
    retry: failure !== undefined,
    forceReadinessCheck: failure?.forceReadinessCheck ?? false,
  };
};

const exhaustedResult = (attempts: number): WebContainerResult => ({
  response: Response.json(
    { error: "web_container_unavailable" },
    {
      status: 503,
      headers: { "Retry-After": "1" },
    },
  ),
  retryOutcome: "exhausted",
  attempts,
});

const jitteredDelay = (baseDelayMs: number, random: () => number): number =>
  Math.round(baseDelayMs * (0.75 + random() * 0.5));

const randomFraction = (): number => {
  const value = new Uint32Array(1);
  crypto.getRandomValues(value);
  return value[0] / 2 ** 32;
};

const wait = async (delayMs: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, delayMs));

const readBoundedText = async (
  response: Response,
  maxBytes: number,
): Promise<string | null> => {
  if (!response.body) {
    return "";
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        return new TextDecoder().decode(joinChunks(chunks, totalBytes));
      }
      if (totalBytes + value.byteLength > maxBytes) {
        // This reader belongs to a cloned response, so cancellation does not
        // settle until the original tee branch is consumed or canceled. The
        // original must remain available to the caller; do not block on the
        // clone's cancellation here.
        void reader.cancel().catch(() => undefined);
        return null;
      }
      chunks.push(value);
      totalBytes += value.byteLength;
    }
  } finally {
    reader.releaseLock();
  }
};

const joinChunks = (chunks: Uint8Array[], totalBytes: number): Uint8Array => {
  const joined = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return joined;
};
