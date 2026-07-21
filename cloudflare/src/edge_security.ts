import {
  createRequestId,
  emitTelemetry,
  REQUEST_ID_HEADER,
  sanitizeRoute,
} from "./telemetry.ts";

interface RateLimitStub {
  fetch(request: Request): Promise<Response>;
}

interface RateLimitNamespace {
  getByName(name: string): RateLimitStub;
}

export interface EdgeSecurityEnvironment {
  AUTH_RATE_LIMITER: RateLimitNamespace;
}

type RateLimitedRoute = {
  limiterPath: "/login" | "/signup" | "/password-reset";
};

export const handleEdgeRateLimit = async (
  request: Request,
  environment: EdgeSecurityEnvironment,
  requestId = createRequestId(),
): Promise<Response | null> => {
  const url = new URL(request.url);
  const route = rateLimitedRoute(request.method, url.pathname);
  if (!route) {
    return null;
  }

  const actor =
    request.headers.get("CF-Access-Authenticated-User-Email")?.toLowerCase() ||
    request.headers.get("CF-Connecting-IP") ||
    "unknown";
  try {
    const limiter = environment.AUTH_RATE_LIMITER.getByName(actor);
    const limiterResponse = await limiter.fetch(
      new Request(`http://rate-limit.internal${route.limiterPath}`, {
        method: "POST",
      }),
    );
    if (!limiterResponse.ok) {
      throw new Error("Rate limiter returned an invalid response");
    }
    const outcome = (await limiterResponse.json()) as {
      success?: unknown;
      retry_after_seconds?: unknown;
    };
    if (typeof outcome.success !== "boolean") {
      throw new Error("Rate limiter returned an invalid result");
    }
    if (outcome.success) {
      return null;
    }
    emitTelemetry("warn", "edge_rate_limited", {
      request_id: requestId,
      route: sanitizeRoute(url.pathname),
      status: 429,
      error_category: "rate_limit",
    });
    return rateLimitResponse(
      requestId,
      429,
      "rate_limited",
      normalizeRetryAfter(outcome.retry_after_seconds),
    );
  } catch {
    emitTelemetry("error", "edge_rate_limit_failure", {
      request_id: requestId,
      route: sanitizeRoute(url.pathname),
      status: 503,
      error_category: "rate_limit_unavailable",
    });
    return rateLimitResponse(requestId, 503, "rate_limit_unavailable");
  }
};

export const rateLimitedRoute = (
  method: string,
  pathname: string,
): RateLimitedRoute | null => {
  if (method !== "POST") {
    return null;
  }
  if (pathname === "/login") {
    return { limiterPath: "/login" };
  }
  if (pathname === "/signup") {
    return { limiterPath: "/signup" };
  }
  if (
    pathname === "/reset-password" ||
    /^\/reset-password\/[^/]+\/?$/.test(pathname)
  ) {
    return {
      limiterPath: "/password-reset",
    };
  }
  return null;
};

const rateLimitResponse = (
  requestId: string,
  status: number,
  error: string,
  retryAfter = 60,
): Response =>
  Response.json(
    { error },
    {
      status,
      headers: {
        "Retry-After": String(retryAfter),
        [REQUEST_ID_HEADER]: requestId,
      },
    },
  );

const normalizeRetryAfter = (value: unknown): number =>
  typeof value === "number" && Number.isFinite(value) && value >= 1
    ? Math.min(60, Math.floor(value))
    : 60;
