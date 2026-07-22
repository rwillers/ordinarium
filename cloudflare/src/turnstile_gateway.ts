import { emitTelemetry, sanitizeIdentifier } from "./telemetry.ts";

const TURNSTILE_HOSTNAME = "challenges.cloudflare.com";
const SITEVERIFY_PATH = "/turnstile/v0/siteverify";
const SITEVERIFY_URL = `https://${TURNSTILE_HOSTNAME}${SITEVERIFY_PATH}`;
const MAX_SITEVERIFY_REQUEST_BYTES = 4096;

type TurnstileFetcher = (request: Request) => Promise<Response>;

export interface TurnstileGatewayEnvironment {
  TURNSTILE_SECRET_KEY?: string;
}

export const handleTurnstileRequest = async (
  request: Request,
  environment: TurnstileGatewayEnvironment,
  fetcher: TurnstileFetcher = fetch,
): Promise<Response> => {
  const url = new URL(request.url);
  if (
    request.method !== "POST" ||
    url.protocol !== "https:" ||
    url.hostname !== TURNSTILE_HOSTNAME ||
    url.pathname !== SITEVERIFY_PATH ||
    url.search
  ) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  if (!isFormContentType(request.headers.get("content-type"))) {
    return Response.json({ error: "invalid_content_type" }, { status: 400 });
  }

  const declaredLength = parseContentLength(request.headers.get("content-length"));
  if (declaredLength !== null && declaredLength > MAX_SITEVERIFY_REQUEST_BYTES) {
    return Response.json({ error: "request_too_large" }, { status: 413 });
  }

  let body: ArrayBuffer;
  try {
    body = await request.arrayBuffer();
  } catch {
    return Response.json({ error: "invalid_request" }, { status: 400 });
  }
  if (body.byteLength > MAX_SITEVERIFY_REQUEST_BYTES) {
    return Response.json({ error: "request_too_large" }, { status: 413 });
  }

  if (!environment.TURNSTILE_SECRET_KEY) {
    emitTelemetry("error", "turnstile_siteverify_failure", {
      error_category: "configuration",
    });
    return Response.json(
      { success: false, "error-codes": ["internal-error"] },
      { status: 503 },
    );
  }

  const inboundForm = new URLSearchParams(new TextDecoder().decode(body));
  const token = inboundForm.get("response");
  if (!token) {
    return Response.json({ error: "missing_response" }, { status: 400 });
  }
  const upstreamForm = new URLSearchParams({
    secret: environment.TURNSTILE_SECRET_KEY,
    response: token,
  });
  const remoteIp = inboundForm.get("remoteip");
  if (remoteIp) {
    upstreamForm.set("remoteip", remoteIp);
  }

  const upstreamRequest = new Request(SITEVERIFY_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: upstreamForm.toString(),
  });

  const startedAt = performance.now();
  try {
    const response = await fetcher(upstreamRequest);
    const durationMs = Math.round(performance.now() - startedAt);
    if (!response.ok) {
      const errorCode = await siteverifyErrorCode(response);
      emitTelemetry("error", "turnstile_siteverify_failure", {
        status: response.status,
        duration_ms: durationMs,
        error_category: errorCode,
      });
      return response;
    }
    emitTelemetry("info", "turnstile_siteverify_completed", {
      status: response.status,
      duration_ms: durationMs,
    });
    return response;
  } catch {
    emitTelemetry("error", "turnstile_siteverify_failure", {
      error_category: "network",
      duration_ms: Math.round(performance.now() - startedAt),
    });
    return Response.json(
      { success: false, "error-codes": ["internal-error"] },
      { status: 502 },
    );
  }
};

const isFormContentType = (value: string | null): boolean =>
  value?.split(";", 1)[0].trim().toLowerCase() ===
  "application/x-www-form-urlencoded";

const parseContentLength = (value: string | null): number | null => {
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
};

const siteverifyErrorCode = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.clone().json()) as { "error-codes"?: unknown };
    const codes = payload["error-codes"];
    if (Array.isArray(codes) && typeof codes[0] === "string") {
      return sanitizeIdentifier(codes[0], "upstream_response");
    }
  } catch {
    // The upstream status remains sufficient when Cloudflare returns a non-JSON body.
  }
  return "upstream_response";
};
