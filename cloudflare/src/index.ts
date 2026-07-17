import { Container } from "@cloudflare/containers";

const APPLICATION_PORT = 8080;

export class WebContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "30m";
  enableInternet = true;
}

export class DocumentContainer extends Container {
  defaultPort = APPLICATION_PORT;
  sleepAfter = "60s";
  enableInternet = false;
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

const worker: ExportedHandler = {
  fetch: async (request): Promise<Response> => {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({ role: "orchestrator", status: "ok" });
    }

    return Response.json(
      {
        error: "container_routing_not_enabled",
        message: "Application routing is introduced in migration Phase 3.",
      },
      { status: 503 },
    );
  },
};

export default worker;
