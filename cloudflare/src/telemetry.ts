export type TelemetryLevel = "info" | "warn" | "error";

type TelemetryFields = Record<
  string,
  string | number | boolean | null | undefined
>;

const IDENTIFIER_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;

export const REQUEST_ID_HEADER = "X-Ordinarium-Request-Id";

export const emitTelemetry = (
  level: TelemetryLevel,
  event: string,
  fields: TelemetryFields = {},
): void => {
  const record = Object.fromEntries(
    Object.entries({ event, ...fields }).filter(([, value]) => value !== undefined),
  );
  console[level](record);
};

export const createRequestId = (): string => crypto.randomUUID();

export const sanitizeIdentifier = (
  value: unknown,
  fallback = "unknown",
): string =>
  typeof value === "string" && IDENTIFIER_PATTERN.test(value)
    ? value
    : fallback;

export const sanitizeRoute = (pathname: string): string => {
  if (/^\/reset-password\/[^/]+\/?$/.test(pathname)) {
    return "/reset-password/:token";
  }
  if (/^\/share\/[^/]+\/?$/.test(pathname)) {
    return "/share/:token";
  }
  const segments = pathname.split("/").map((segment) => {
    if (!segment) {
      return segment;
    }
    if (/^\d+$/.test(segment)) {
      return ":id";
    }
    if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(segment)) {
      return ":id";
    }
    if (segment.length > 64) {
      return ":value";
    }
    return segment;
  });
  return segments.join("/") || "/";
};

export const errorCategory = (error: unknown): string => {
  const name = error instanceof Error ? error.name.toLowerCase() : "";
  if (name.includes("timeout") || name.includes("abort")) {
    return "timeout";
  }
  if (name.includes("network") || name.includes("fetch")) {
    return "network";
  }
  return "internal";
};
