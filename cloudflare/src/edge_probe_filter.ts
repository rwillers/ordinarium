import {
  emitTelemetry,
  REQUEST_ID_HEADER,
  sanitizeRoute,
} from "./telemetry.ts";

const FOREIGN_SERVER_EXTENSION =
  /(?:^|\/)[^/]*\.(?:asp|aspx|cgi|jsp|phar|php\d*|phtml)(?:\/|$)/i;
const SENSITIVE_DOT_PATH = /(?:^|\/)\.(?:env|git|hg|svn)(?:\/|$)/i;
const FOREIGN_PLATFORM_PATHS = [
  /^\/wp-(?:admin|content|includes)(?:\/|$)/i,
  /^\/phpmyadmin(?:\/|$)/i,
  /^\/vendor\/phpunit(?:\/|$)/i,
] as const;

type ProbeCategory =
  | "foreign_server_extension"
  | "sensitive_dot_path"
  | "foreign_platform_path"
  | "malformed_path";

export const handleObviousProbe = (
  request: Request,
  requestId: string,
): Response | null => {
  const url = new URL(request.url);
  const category = probeCategory(url.pathname);
  if (!category) {
    return null;
  }

  emitTelemetry("info", "edge_probe_rejected", {
    request_id: requestId,
    route: sanitizeRoute(url.pathname),
    status: 404,
    error_category: category,
  });
  return new Response(null, {
    status: 404,
    headers: {
      "Cache-Control": "private, no-store",
      [REQUEST_ID_HEADER]: requestId,
    },
  });
};

export const probeCategory = (pathname: string): ProbeCategory | null => {
  let normalizedPath: string;
  try {
    normalizedPath = decodeURIComponent(pathname).replace(/\/{2,}/g, "/");
  } catch {
    return "malformed_path";
  }

  if (FOREIGN_SERVER_EXTENSION.test(normalizedPath)) {
    return "foreign_server_extension";
  }
  if (SENSITIVE_DOT_PATH.test(normalizedPath)) {
    return "sensitive_dot_path";
  }
  if (FOREIGN_PLATFORM_PATHS.some((pattern) => pattern.test(normalizedPath))) {
    return "foreign_platform_path";
  }
  return null;
};
