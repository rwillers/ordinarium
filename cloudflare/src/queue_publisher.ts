const MAX_QUEUE_REQUEST_BYTES = 1024;

interface QueueProducer<T> {
  send(message: T): Promise<unknown>;
}

export interface QueuePublisherEnvironment {
  PCO_JOBS_QUEUE: QueueProducer<PcoRowMessage>;
  EMAIL_JOBS_QUEUE: QueueProducer<EmailMessage>;
}

export interface PcoRowMessage {
  job_id: string;
  row_id: string;
  user_id: number;
}

export interface EmailMessage {
  reset_id: string;
}

export const handleQueuePublishRequest = async (
  request: Request,
  environment: QueuePublisherEnvironment,
): Promise<Response> => {
  const path = new URL(request.url).pathname;
  if ((path !== "/pco" && path !== "/email") || request.method !== "POST") {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  if (!isJsonContentType(request.headers.get("content-type"))) {
    return Response.json({ error: "invalid_content_type" }, { status: 400 });
  }

  const declaredLength = parseContentLength(request.headers.get("content-length"));
  if (declaredLength !== null && declaredLength > MAX_QUEUE_REQUEST_BYTES) {
    return Response.json({ error: "request_too_large" }, { status: 413 });
  }

  const payload = await readJsonBody(request);
  if (payload.error) {
    return payload.error;
  }
  const message =
    path === "/pco"
      ? parsePcoRowMessage(payload.value)
      : parseEmailMessage(payload.value);
  if (!message) {
    return Response.json({ error: "invalid_payload" }, { status: 400 });
  }

  try {
    // The validated object is reconstructed by the parser so request headers and
    // unrecognized fields can never cross the queue boundary.
    if (path === "/pco") {
      await environment.PCO_JOBS_QUEUE.send(message as PcoRowMessage);
    } else {
      await environment.EMAIL_JOBS_QUEUE.send(message as EmailMessage);
    }
  } catch (error: unknown) {
    console.error("Queue publication failed", error);
    return Response.json({ error: "queue_unavailable" }, { status: 503 });
  }
  return Response.json({ status: "queued" }, { status: 202 });
};

export const parsePcoRowMessage = (value: unknown): PcoRowMessage | null => {
  if (!hasExactKeys(value, ["job_id", "row_id", "user_id"])) {
    return null;
  }
  if (!isIdentifier(value.job_id) || !isIdentifier(value.row_id)) {
    return null;
  }
  if (
    typeof value.user_id !== "number" ||
    !Number.isSafeInteger(value.user_id) ||
    value.user_id <= 0
  ) {
    return null;
  }
  return {
    job_id: value.job_id,
    row_id: value.row_id,
    user_id: value.user_id,
  };
};

export const parseEmailMessage = (value: unknown): EmailMessage | null => {
  if (!hasExactKeys(value, ["reset_id"]) || !isIdentifier(value.reset_id)) {
    return null;
  }
  return { reset_id: value.reset_id };
};

const readJsonBody = async (
  request: Request,
): Promise<{ value?: unknown; error?: Response }> => {
  let body: ArrayBuffer;
  try {
    body = await request.arrayBuffer();
  } catch {
    return { error: Response.json({ error: "invalid_request" }, { status: 400 }) };
  }
  if (body.byteLength > MAX_QUEUE_REQUEST_BYTES) {
    return { error: Response.json({ error: "request_too_large" }, { status: 413 }) };
  }
  try {
    return { value: JSON.parse(new TextDecoder().decode(body)) as unknown };
  } catch {
    return { error: Response.json({ error: "invalid_json" }, { status: 400 }) };
  }
};

const hasExactKeys = <K extends string>(
  value: unknown,
  expectedKeys: readonly K[],
): value is Record<K, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const actualKeys = Object.keys(value);
  return (
    actualKeys.length === expectedKeys.length &&
    expectedKeys.every((key) => Object.hasOwn(value, key))
  );
};

const isIdentifier = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= 128;

const isJsonContentType = (value: string | null): boolean =>
  value?.split(";", 1)[0].trim().toLowerCase() === "application/json";

const parseContentLength = (value: string | null): number | null => {
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
};
