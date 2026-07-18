const D1_HEALTH_PATH = "/ops/d1-health";

type EdgeEnvironment = {
  APP_DB: D1Database;
  OPS_HEALTH_TOKEN?: string;
};

export const handleEdgeRoute = async (
  request: Request,
  environment: EdgeEnvironment,
): Promise<Response | null> => {
  const url = new URL(request.url);
  if (url.pathname === "/health" && ["GET", "HEAD"].includes(request.method)) {
    return Response.json({ status: "ok" });
  }
  if (url.pathname !== D1_HEALTH_PATH) {
    return null;
  }
  if (request.method !== "GET") {
    return Response.json({ error: "method_not_allowed" }, { status: 405 });
  }
  const expectedToken = environment.OPS_HEALTH_TOKEN;
  const suppliedToken = request.headers.get("authorization");
  if (!expectedToken || suppliedToken !== `Bearer ${expectedToken}`) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  try {
    const row = await environment.APP_DB.prepare("select 1 as ok").first<{
      ok: number;
    }>();
    if (row?.ok !== 1) {
      throw new Error("unexpected_d1_health_result");
    }
    return Response.json({ status: "ok", database: "ok" });
  } catch (error: unknown) {
    console.error("D1 operational health check failed", error);
    return Response.json(
      { status: "unavailable", database: "unavailable" },
      { status: 503 },
    );
  }
};
