import {
  createRequestId,
  emitTelemetry,
  errorCategory,
  REQUEST_ID_HEADER,
} from "./telemetry.ts";

const DOCUMENT_AUTH_HEADER = "X-Ordinarium-Document-Auth";
const DOCUMENT_MAX_REQUEST_BYTES = 5 * 1024 * 1024;
const DOCUMENT_MAX_OUTPUT_BYTES = 25 * 1024 * 1024;
const DOCUMENT_REQUEST_TIMEOUT_MS = 115_000;
const DOCUMENT_INSTANCE_NAMES = [
  "staging-documents-0",
  "staging-documents-1",
] as const;

interface DocumentContainerStub {
  fetch(request: Request): Promise<Response>;
}

interface DocumentContainerNamespace {
  getByName(name: string): DocumentContainerStub;
}

interface DocumentEnvironment {
  DOCUMENT_CONTAINER: DocumentContainerNamespace;
  DOCUMENT_SERVICE_AUTH_TOKEN?: string;
}

let nextDocumentInstance = 0;

export const handleDocumentRequest = async (
  request: Request,
  environment: DocumentEnvironment,
): Promise<Response> => {
  const url = new URL(request.url);
  const requestId = request.headers.get(REQUEST_ID_HEADER) || createRequestId();
  if (request.method !== "POST" || url.pathname !== "/render") {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  if (!environment.DOCUMENT_SERVICE_AUTH_TOKEN) {
    emitExportFailure(requestId, "configuration");
    return unavailableResponse();
  }
  if (request.headers.get("content-type") !== "application/json") {
    return Response.json({ error: "invalid_content_type" }, { status: 400 });
  }

  const declaredLength = parseContentLength(request.headers.get("content-length"));
  if (declaredLength !== null && declaredLength > DOCUMENT_MAX_REQUEST_BYTES) {
    return Response.json({ error: "request_too_large" }, { status: 413 });
  }

  let body: ArrayBuffer;
  try {
    body = await request.arrayBuffer();
  } catch (error: unknown) {
    emitExportFailure(requestId, errorCategory(error));
    return Response.json({ error: "invalid_request" }, { status: 400 });
  }
  if (body.byteLength > DOCUMENT_MAX_REQUEST_BYTES) {
    return Response.json({ error: "request_too_large" }, { status: 413 });
  }

  const container = environment.DOCUMENT_CONTAINER.getByName(
    selectDocumentInstanceName(),
  );
  const headers = new Headers({
    "content-type": "application/json",
    [DOCUMENT_AUTH_HEADER]: environment.DOCUMENT_SERVICE_AUTH_TOKEN,
    [REQUEST_ID_HEADER]: requestId,
  });
  const forwardedRequest = new Request(request.url, {
    method: "POST",
    body,
    headers,
    signal: AbortSignal.timeout(DOCUMENT_REQUEST_TIMEOUT_MS),
  });

  try {
    const response = await container.fetch(forwardedRequest);
    const responseLength = parseContentLength(
      response.headers.get("content-length"),
    );
    if (responseLength !== null && responseLength > DOCUMENT_MAX_OUTPUT_BYTES) {
      emitExportFailure(requestId, "output_limit");
      return unavailableResponse();
    }
    if (!response.ok) {
      emitExportFailure(requestId, "document_response");
    }
    return response;
  } catch (error: unknown) {
    emitExportFailure(requestId, errorCategory(error));
    return unavailableResponse();
  }
};

export const selectDocumentInstanceName = (): string => {
  const instanceName = DOCUMENT_INSTANCE_NAMES[nextDocumentInstance];
  nextDocumentInstance =
    (nextDocumentInstance + 1) % DOCUMENT_INSTANCE_NAMES.length;
  return instanceName;
};

const parseContentLength = (value: string | null): number | null => {
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
};

const unavailableResponse = (): Response =>
  Response.json({ error: "document_service_unavailable" }, { status: 503 });

const emitExportFailure = (requestId: string, category: string): void => {
  emitTelemetry("error", "export_failure", {
    request_id: requestId,
    container_role: "documents",
    error_category: category,
  });
};
