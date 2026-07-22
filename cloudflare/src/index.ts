import { Container, ContainerProxy } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

import { handleD1Request } from "./d1_bridge";
import { handleDocumentRequest } from "./document_orchestrator";
import { handleEdgeRateLimit } from "./edge_security";
import { handleEdgeRoute } from "./edge_routes";
import { handleQueueBatch } from "./queue_consumer";
import { emitQueueMetrics } from "./queue_observability";
import { handleQueuePublishRequest } from "./queue_publisher";
import {
  reconcilePasswordResetEmails,
  reconcilePcoRows,
} from "./queue_reconciliation";
import {
  createRequestId,
  emitTelemetry,
  errorCategory,
  REQUEST_ID_HEADER,
  sanitizeRoute,
} from "./telemetry";
import { handleTurnstileRequest } from "./turnstile_gateway";

export { ContainerProxy };
export { AuthRateLimiter } from "./auth_rate_limiter";

const APPLICATION_PORT = 8080;
const WEB_INSTANCE_NAME = "staging-web";
declare global {
  namespace Cloudflare {
    interface Env {
      WEB_CONTAINER: DurableObjectNamespace;
      DOCUMENT_CONTAINER: DurableObjectNamespace;
      PCO_JOBS_CONTAINER: DurableObjectNamespace;
      EMAIL_JOBS_CONTAINER: DurableObjectNamespace;
      APP_DB: D1Database;
      PCO_JOBS_QUEUE: Queue;
      PCO_JOBS_DLQ: Queue;
      EMAIL_JOBS_QUEUE: Queue;
      EMAIL_JOBS_DLQ: Queue;
      AUTH_RATE_LIMITER: DurableObjectNamespace;
      SECRET_KEY: string;
      DEPLOYMENT_ENV: string;
      OPS_HEALTH_TOKEN?: string;
      PCO_TOKEN_ENCRYPTION_KEYS: string;
      PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION?: string;
      DOCUMENT_SERVICE_AUTH_TOKEN: string;
      PCO_JOB_SERVICE_AUTH_TOKEN: string;
      EMAIL_JOB_SERVICE_AUTH_TOKEN: string;
      PCO_CLIENT_ID?: string;
      PCO_CLIENT_SECRET?: string;
      PCO_API_BASE?: string;
      PCO_OAUTH_TOKEN_URL?: string;
      MAILERSEND_API_TOKEN?: string;
      MAILERSEND_FROM_EMAIL?: string;
      MAILERSEND_FROM_NAME?: string;
      PASSWORD_RESET_DELIVERY_KEY?: string;
      APP_ORIGIN?: string;
      SIDE_EFFECTS_HOSTNAME?: string;
      EXTERNAL_SIDE_EFFECTS_ENABLED?: string;
      TURNSTILE_SITE_KEY?: string;
      TURNSTILE_SECRET_KEY?: string;
      TURNSTILE_EXPECTED_HOSTNAME?: string;
      ALERT_EMAIL_TO?: string;
    }
  }
}

export class WebContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "30m";
  enableInternet = false;
  interceptHttps = true;
  allowedHosts = [
    "d1.internal",
    "documents.internal",
    "queue.internal",
    "challenges.cloudflare.com",
    "api.planningcenteronline.com",
  ];
  envVars = {
    ORDINARIUM_CONTAINER_ROLE: "web",
    SECRET_KEY: env.SECRET_KEY,
    TURNSTILE_ENABLED: env.DEPLOYMENT_ENV === "staging" ? "true" : "false",
    TURNSTILE_SITE_KEY: env.TURNSTILE_SITE_KEY || "",
    TURNSTILE_SECRET_KEY: env.TURNSTILE_SECRET_KEY ? "worker-managed" : "",
    TURNSTILE_EXPECTED_HOSTNAME: env.TURNSTILE_EXPECTED_HOSTNAME || "",
    SSL_CERT_FILE: "/etc/cloudflare/certs/cloudflare-containers-ca.crt",
    REQUESTS_CA_BUNDLE: "/etc/cloudflare/certs/cloudflare-containers-ca.crt",
    RATELIMIT_ENABLED: "false",
    SESSION_COOKIE_SECURE: env.DEPLOYMENT_ENV === "local" ? "false" : "true",
    ORDINARIUM_DISPOSABLE_SQLITE: "true",
    DOCUMENT_SERVICE_URL: "http://documents.internal/render",
    DOCUMENT_SERVICE_TIMEOUT_SECONDS: "120",
    DOCUMENT_SERVICE_MAX_REQUEST_BYTES: String(5 * 1024 * 1024),
    DOCUMENT_SERVICE_MAX_BYTES: String(25 * 1024 * 1024),
    QUEUE_SERVICE_URL: "http://queue.internal",
    D1_SERVICE_URL: "http://d1.internal/query",
    DATABASE_GATEWAY_BACKEND: "d1",
    PCO_TOKEN_ENCRYPTION_KEYS: env.PCO_TOKEN_ENCRYPTION_KEYS,
    PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION:
      env.PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION || "v1",
    PCO_CLIENT_ID: env.PCO_CLIENT_ID || "",
    PCO_CLIENT_SECRET: env.PCO_CLIENT_SECRET || "",
    PASSWORD_RESET_DELIVERY_KEY: env.PASSWORD_RESET_DELIVERY_KEY || "",
  };

  override onStart() {
    emitTelemetry("info", "container_started", { container_role: "web" });
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    emitTelemetry(exitCode === 0 ? "info" : "error", "container_stopped", {
      container_role: "web",
      exit_code: exitCode,
      error_category: exitCode === 0 ? undefined : "container_failure",
      stop_reason: reason,
    });
  }
}

WebContainer.outboundByHost = {
  "documents.internal": (request, environment: Cloudflare.Env) =>
    handleDocumentRequest(request, environment),
  "d1.internal": (request, environment: Cloudflare.Env) =>
    handleD1Request(request, environment.APP_DB),
  "queue.internal": (request, environment: Cloudflare.Env) =>
    handleQueuePublishRequest(request, environment),
  "challenges.cloudflare.com": (request, environment: Cloudflare.Env) =>
    handleTurnstileRequest(request, environment),
  "api.planningcenteronline.com": (request) => fetch(request),
};

export class DocumentContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "60s";
  enableInternet = false;
  envVars = {
    ORDINARIUM_CONTAINER_ROLE: "documents",
    DOCUMENT_SERVICE_AUTH_TOKEN: env.DOCUMENT_SERVICE_AUTH_TOKEN,
    DOCUMENT_MAX_REQUEST_BYTES: String(5 * 1024 * 1024),
    DOCUMENT_MAX_OUTPUT_BYTES: String(25 * 1024 * 1024),
    DOCUMENT_RENDER_TIMEOUT_SECONDS: "60",
  };

  override onStart() {
    emitTelemetry("info", "container_started", { container_role: "documents" });
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    emitTelemetry(exitCode === 0 ? "info" : "error", "container_stopped", {
      container_role: "documents",
      exit_code: exitCode,
      error_category: exitCode === 0 ? undefined : "container_failure",
      stop_reason: reason,
    });
  }
}

export class PcoJobsContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "2m";
  enableInternet = false;
  allowedHosts = ["d1.internal", "api.planningcenteronline.com"];
  envVars = {
    ORDINARIUM_CONTAINER_ROLE: "pco-jobs",
    JOB_SERVICE_AUTH_TOKEN: env.PCO_JOB_SERVICE_AUTH_TOKEN,
    D1_SERVICE_URL: "http://d1.internal/query",
    DATABASE_GATEWAY_BACKEND: "d1",
    PCO_TOKEN_ENCRYPTION_KEYS: env.PCO_TOKEN_ENCRYPTION_KEYS,
    PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION:
      env.PCO_TOKEN_ENCRYPTION_PRIMARY_VERSION || "v1",
    PCO_CLIENT_ID: env.PCO_CLIENT_ID || "",
    PCO_CLIENT_SECRET: env.PCO_CLIENT_SECRET || "",
    PCO_API_BASE:
      env.PCO_API_BASE || "https://api.planningcenteronline.com",
    PCO_OAUTH_TOKEN_URL:
      env.PCO_OAUTH_TOKEN_URL ||
      "https://api.planningcenteronline.com/oauth/token",
  };

  override onStart() {
    emitTelemetry("info", "container_started", { container_role: "pco-jobs" });
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    emitTelemetry(exitCode === 0 ? "info" : "error", "container_stopped", {
      container_role: "pco-jobs",
      exit_code: exitCode,
      error_category: exitCode === 0 ? undefined : "container_failure",
      stop_reason: reason,
    });
  }
}

PcoJobsContainer.outboundByHost = {
  "d1.internal": (request, environment: Cloudflare.Env) =>
    handleD1Request(request, environment.APP_DB),
};

export class EmailJobsContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "30s";
  enableInternet = false;
  interceptHttps = true;
  allowedHosts = ["d1.internal", "api.mailersend.com"];
  envVars = {
    ORDINARIUM_CONTAINER_ROLE: "email-jobs",
    JOB_SERVICE_AUTH_TOKEN: env.EMAIL_JOB_SERVICE_AUTH_TOKEN,
    D1_SERVICE_URL: "http://d1.internal/query",
    DATABASE_GATEWAY_BACKEND: "d1",
    MAILERSEND_API_TOKEN: env.MAILERSEND_API_TOKEN || "",
    MAILERSEND_FROM_EMAIL: env.MAILERSEND_FROM_EMAIL || "",
    MAILERSEND_FROM_NAME: env.MAILERSEND_FROM_NAME || "Ordinarium",
    PASSWORD_RESET_DELIVERY_KEY: env.PASSWORD_RESET_DELIVERY_KEY || "",
    ALERT_EMAIL_TO: env.ALERT_EMAIL_TO || "",
    DEPLOYMENT_ENV: env.DEPLOYMENT_ENV,
    APP_ORIGIN: env.APP_ORIGIN || "",
    SIDE_EFFECTS_HOSTNAME: env.SIDE_EFFECTS_HOSTNAME || "",
    EXTERNAL_SIDE_EFFECTS_ENABLED:
      env.EXTERNAL_SIDE_EFFECTS_ENABLED || "false",
    REQUESTS_CA_BUNDLE: "/etc/cloudflare/certs/cloudflare-containers-ca.crt",
  };

  override onStart() {
    emitTelemetry("info", "container_started", { container_role: "email-jobs" });
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    emitTelemetry(exitCode === 0 ? "info" : "error", "container_stopped", {
      container_role: "email-jobs",
      exit_code: exitCode,
      error_category: exitCode === 0 ? undefined : "container_failure",
      stop_reason: reason,
    });
  }
}

EmailJobsContainer.outboundByHost = {
  "d1.internal": (request, environment: Cloudflare.Env) =>
    handleD1Request(request, environment.APP_DB),
  "api.mailersend.com": (request) => fetch(request),
};

const worker: ExportedHandler<Cloudflare.Env> = {
  fetch: async (request, environment): Promise<Response> => {
    const requestId = createRequestId();
    const startedAt = performance.now();
    const route = sanitizeRoute(new URL(request.url).pathname);
    let containerRole = "edge";
    let response: Response | undefined;
    try {
      const rateLimitResponse = await handleEdgeRateLimit(
        request,
        environment,
        requestId,
      );
      if (rateLimitResponse) {
        response = rateLimitResponse;
        return responseWithRequestId(response, requestId);
      }
      const edgeResponse = await handleEdgeRoute(request, environment);
      if (edgeResponse) {
        response = edgeResponse;
        return responseWithRequestId(response, requestId);
      }
      containerRole = "web";
      const webContainer = environment.WEB_CONTAINER.getByName(WEB_INSTANCE_NAME);
      const headers = new Headers(request.headers);
      headers.set(REQUEST_ID_HEADER, requestId);
      response = await webContainer.fetch(new Request(request, { headers }));
      return responseWithRequestId(response, requestId);
    } catch (error: unknown) {
      emitTelemetry("error", "worker_request_failure", {
        request_id: requestId,
        route,
        container_role: containerRole,
        error_category: errorCategory(error),
      });
      response = Response.json(
        { error: "web_container_unavailable" },
        { status: 503 },
      );
      return responseWithRequestId(response, requestId);
    } finally {
      emitTelemetry("info", "request_completed", {
        request_id: requestId,
        route,
        status: response?.status ?? 500,
        duration_ms: Math.round((performance.now() - startedAt) * 100) / 100,
        container_role: containerRole,
        error_category:
          response !== undefined && response.status >= 500
            ? "request_failure"
            : undefined,
      });
    }
  },
  queue: async (batch, environment): Promise<void> => {
    await handleQueueBatch(batch, environment);
  },
  scheduled: async (_controller, environment, context): Promise<void> => {
    context.waitUntil(
      Promise.all([
        reconcilePcoRows(environment),
        reconcilePasswordResetEmails(environment),
        emitQueueMetrics(environment),
      ]).then(() => undefined),
    );
  },
};

const responseWithRequestId = (response: Response, requestId: string): Response => {
  const headers = new Headers(response.headers);
  headers.set(REQUEST_ID_HEADER, requestId);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
};

export default worker;
