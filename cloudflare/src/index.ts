import { Container, ContainerProxy } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

import { handleD1Request } from "./d1_bridge";

export { ContainerProxy };

const APPLICATION_PORT = 8080;
const WEB_INSTANCE_NAME = "staging-web";
const DOCUMENT_INSTANCE_NAME = "staging-documents";

declare global {
  namespace Cloudflare {
    interface Env {
      WEB_CONTAINER: DurableObjectNamespace;
      DOCUMENT_CONTAINER: DurableObjectNamespace;
      PCO_JOBS_CONTAINER: DurableObjectNamespace;
      EMAIL_JOBS_CONTAINER: DurableObjectNamespace;
      APP_DB: D1Database;
      SECRET_KEY: string;
      DEPLOYMENT_ENV: string;
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
    D1_SERVICE_URL: "http://d1.internal/query",
  };

  override onStart() {
    console.log("Web container started", new Date().toISOString());
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    console.log("Web container stopped", { exitCode, reason });
  }
}

WebContainer.outboundByHost = {
  "documents.internal": (request, environment: Cloudflare.Env) => {
    const documentContainer = environment.DOCUMENT_CONTAINER.getByName(
      DOCUMENT_INSTANCE_NAME,
    );
    return documentContainer.fetch(request);
  },
  "d1.internal": (request, environment: Cloudflare.Env) =>
    handleD1Request(request, environment.APP_DB),
};

export class DocumentContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "60s";
  enableInternet = false;

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
}

export class EmailJobsContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "30s";
  enableInternet = true;
}

const worker: ExportedHandler<Cloudflare.Env> = {
  fetch: async (request, environment): Promise<Response> => {
    try {
      const webContainer = environment.WEB_CONTAINER.getByName(WEB_INSTANCE_NAME);
      return await webContainer.fetch(request);
    } catch (error: unknown) {
      console.error("Web container request failed", error);
      return Response.json({ error: "web_container_unavailable" }, { status: 503 });
    }
  },
};

export default worker;
