import { Container, ContainerProxy } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

import { handleD1Request } from "./d1_bridge";
import { handleDocumentRequest } from "./document_orchestrator";
import { handleEdgeRoute } from "./edge_routes";
import { handleQueueBatch } from "./queue_consumer";
import { handleQueuePublishRequest } from "./queue_publisher";
import {
  reconcilePasswordResetEmails,
  reconcilePcoRows,
} from "./queue_reconciliation";

export { ContainerProxy };

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
      EMAIL_JOBS_QUEUE: Queue;
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
    }
  }
}

export class WebContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "30m";
  enableInternet = true;
  envVars = {
    SECRET_KEY: env.SECRET_KEY,
    TURNSTILE_ENABLED: "false",
    RATELIMIT_STORAGE_URI: "memory://",
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
    console.log("Web container started", new Date().toISOString());
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    console.log("Web container stopped", { exitCode, reason });
  }
}

WebContainer.outboundByHost = {
  "documents.internal": (request, environment: Cloudflare.Env) =>
    handleDocumentRequest(request, environment),
  "d1.internal": (request, environment: Cloudflare.Env) =>
    handleD1Request(request, environment.APP_DB),
  "queue.internal": (request, environment: Cloudflare.Env) =>
    handleQueuePublishRequest(request, environment),
};

export class DocumentContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "60s";
  enableInternet = false;
  envVars = {
    DOCUMENT_SERVICE_AUTH_TOKEN: env.DOCUMENT_SERVICE_AUTH_TOKEN,
    DOCUMENT_MAX_REQUEST_BYTES: String(5 * 1024 * 1024),
    DOCUMENT_MAX_OUTPUT_BYTES: String(25 * 1024 * 1024),
    DOCUMENT_RENDER_TIMEOUT_SECONDS: "60",
  };

  override onStart() {
    console.log("Document container started", new Date().toISOString());
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    console.log("Document container stopped", { exitCode, reason });
  }
}

export class PcoJobsContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "2m";
  enableInternet = true;
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
}

PcoJobsContainer.outboundByHost = {
  "d1.internal": (request, environment: Cloudflare.Env) =>
    handleD1Request(request, environment.APP_DB),
};

export class EmailJobsContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "30s";
  enableInternet = true;
  envVars = {
    ORDINARIUM_CONTAINER_ROLE: "email-jobs",
    JOB_SERVICE_AUTH_TOKEN: env.EMAIL_JOB_SERVICE_AUTH_TOKEN,
    D1_SERVICE_URL: "http://d1.internal/query",
    DATABASE_GATEWAY_BACKEND: "d1",
    MAILERSEND_API_TOKEN: env.MAILERSEND_API_TOKEN || "",
    MAILERSEND_FROM_EMAIL: env.MAILERSEND_FROM_EMAIL || "",
    MAILERSEND_FROM_NAME: env.MAILERSEND_FROM_NAME || "Ordinarium",
    PASSWORD_RESET_DELIVERY_KEY: env.PASSWORD_RESET_DELIVERY_KEY || "",
    DEPLOYMENT_ENV: env.DEPLOYMENT_ENV,
    APP_ORIGIN: env.APP_ORIGIN || "",
    SIDE_EFFECTS_HOSTNAME: env.SIDE_EFFECTS_HOSTNAME || "",
    EXTERNAL_SIDE_EFFECTS_ENABLED:
      env.EXTERNAL_SIDE_EFFECTS_ENABLED || "false",
  };
}

EmailJobsContainer.outboundByHost = {
  "d1.internal": (request, environment: Cloudflare.Env) =>
    handleD1Request(request, environment.APP_DB),
};

const worker: ExportedHandler<Cloudflare.Env> = {
  fetch: async (request, environment): Promise<Response> => {
    const edgeResponse = await handleEdgeRoute(request, environment);
    if (edgeResponse) {
      return edgeResponse;
    }
    try {
      const webContainer = environment.WEB_CONTAINER.getByName(WEB_INSTANCE_NAME);
      return await webContainer.fetch(request);
    } catch (error: unknown) {
      console.error("Web container request failed", error);
      return Response.json({ error: "web_container_unavailable" }, { status: 503 });
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
      ]).then(() => undefined),
    );
  },
};

export default worker;
