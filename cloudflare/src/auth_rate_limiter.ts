import { DurableObject } from "cloudflare:workers";
import {
  consumeRateLimit,
  type RateLimitCounter,
} from "./auth_rate_limit_policy";
import { emitTelemetry } from "./telemetry";
const ROUTE_LIMITS = {
  login: 10,
  signup: 10,
  "password-reset": 5,
} as const;

type LimitedRoute = keyof typeof ROUTE_LIMITS;

export class AuthRateLimiter extends DurableObject<Cloudflare.Env> {
  override async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const route = url.pathname.slice(1) as LimitedRoute;
    if (request.method !== "POST" || !(route in ROUTE_LIMITS)) {
      return Response.json({ error: "not_found" }, { status: 404 });
    }

    const now = Date.now();
    const limit = ROUTE_LIMITS[route];
    const outcome = await this.ctx.storage.transaction(async (transaction) => {
      const stored = await transaction.get<RateLimitCounter>(route);
      const result = consumeRateLimit(stored, now, limit);
      if (result.outcome.success) {
        await transaction.put(route, result.counter);
      }
      return result.outcome;
    });
    emitTelemetry(outcome.success ? "info" : "warn", "auth_rate_limit_checked", {
      route,
      remaining: outcome.remaining,
      limited: !outcome.success,
    });
    return Response.json(outcome);
  }
}
