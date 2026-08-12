const TRANSIENT_CONTAINER_FAILURE_PREFIXES = [
  "Failed to start container:",
  "Container suddenly disconnected, try again",
  "Error proxying request to container:",
] as const;
const MAX_TRANSIENT_RESPONSE_BYTES = 512;
const TRANSIENT_RETRY_DELAYS_MS = [250, 750] as const;

type Delay = (milliseconds: number) => Promise<void>;

interface WebContainerStub {
  fetch(request: Request): Promise<Response>;
}

export type WebContainerResult = {
  response: Response;
  retryOutcome: "none" | "succeeded" | "exhausted";
};

export const fetchWebContainer = async (
  container: WebContainerStub,
  request: Request,
  delay: Delay = wait,
): Promise<WebContainerResult> => {
  const retryRequests = isRetryableMethod(request.method)
    ? TRANSIENT_RETRY_DELAYS_MS.map(() => new Request(request))
    : [];
  let response = await container.fetch(request);
  if (retryRequests.length === 0) {
    return { response, retryOutcome: "none" };
  }
  if (!(await isTransientContainerFailure(response))) {
    return { response, retryOutcome: "none" };
  }

  for (const [index, retryRequest] of retryRequests.entries()) {
    await response.body?.cancel();
    await delay(TRANSIENT_RETRY_DELAYS_MS[index]);
    response = await container.fetch(retryRequest);
    if (!(await isTransientContainerFailure(response))) {
      return { response, retryOutcome: "succeeded" };
    }
  }

  await response.body?.cancel();
  return {
    response: Response.json(
      { error: "web_container_unavailable" },
      {
        status: 503,
        headers: { "Retry-After": "1" },
      },
    ),
    retryOutcome: "exhausted",
  };
};

const wait: Delay = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const isRetryableMethod = (method: string): boolean =>
  method === "GET" || method === "HEAD";

const isTransientContainerFailure = async (
  response: Response,
): Promise<boolean> => {
  if (response.status !== 500) {
    return false;
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.toLowerCase() !== "text/plain;charset=utf-8") {
    return false;
  }
  const body = await readBoundedText(
    response.clone(),
    MAX_TRANSIENT_RESPONSE_BYTES,
  );
  return (
    body !== null &&
    TRANSIENT_CONTAINER_FAILURE_PREFIXES.some((prefix) => body.startsWith(prefix))
  );
};

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
