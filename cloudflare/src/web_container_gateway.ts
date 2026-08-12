const TRANSIENT_CONTAINER_FAILURE_PREFIXES = [
  "Failed to start container:",
  "Container suddenly disconnected, try again",
  "Error proxying request to container:",
  "There is no Container instance available at this time.",
] as const;
const TRANSIENT_CONTAINER_STATUSES = new Set([429, 502, 503, 504]);
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
  const canRetry = isRetryableMethod(request.method);
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

const isRetryableMethod = (method: string): boolean =>
  method === "GET" || method === "HEAD";

const transientContainerFailure = async (
  response: Response,
): Promise<{ retry: boolean; forceReadinessCheck: boolean }> => {
  const retryStatus = TRANSIENT_CONTAINER_STATUSES.has(response.status);
  if (response.status !== 500 && response.status !== 503) {
    return { retry: retryStatus, forceReadinessCheck: false };
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.split(";", 1)[0].trim().toLowerCase() !== "text/plain") {
    return { retry: retryStatus, forceReadinessCheck: false };
  }
  const body = await readBoundedText(
    response.clone(),
    MAX_TRANSIENT_RESPONSE_BYTES,
  );
  const forceReadinessCheck =
    body !== null &&
    TRANSIENT_CONTAINER_FAILURE_PREFIXES.some((prefix) => body.startsWith(prefix));
  return {
    retry: retryStatus || forceReadinessCheck,
    forceReadinessCheck,
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
