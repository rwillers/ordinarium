import { DurableObject } from "cloudflare:workers";

import {
  claimAlert,
  commitAlert,
  releaseAlert,
  type AlertDedupeState,
} from "./alert_dedupe_policy.ts";
import {
  handleTailEvents,
  type AlertTailEnvironment,
} from "./alert_dispatch.ts";

export type { AlertTailEnvironment } from "./alert_dispatch.ts";

export class AlertDeduplicator extends DurableObject<AlertTailEnvironment> {
  override async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") {
      return Response.json({ error: "not_found" }, { status: 404 });
    }
    const operation = new URL(request.url).pathname.slice(1);
    const payload = await readOperation(request);
    if (!payload) {
      return Response.json({ error: "invalid_payload" }, { status: 400 });
    }
    if (operation === "claim") {
      return this.claim(payload);
    }
    if (operation === "commit" || operation === "release") {
      return this.finish(operation, payload);
    }
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  private async claim(payload: DedupeOperation): Promise<Response> {
    const result = await this.ctx.storage.transaction(async (transaction) => {
      const stored = await transaction.get<AlertDedupeState>("state");
      const claim = claimAlert(stored, payload.now, payload.window_ms, payload.token);
      if (claim.allowed) {
        await transaction.put("state", claim.state);
      }
      return claim;
    });
    return Response.json({ allowed: result.allowed, token: result.token });
  }

  private async finish(
    operation: "commit" | "release",
    payload: DedupeOperation,
  ): Promise<Response> {
    const updated = await this.ctx.storage.transaction(async (transaction) => {
      const stored = await transaction.get<AlertDedupeState>("state");
      const next =
        operation === "commit"
          ? commitAlert(stored, payload.token, payload.now)
          : releaseAlert(stored, payload.token);
      if (next) {
        await transaction.put("state", next);
      }
      return next;
    });
    return Response.json({ updated: updated !== null });
  }
}

const alertTail: ExportedHandler<AlertTailEnvironment> = {
  tail: async (traces, environment): Promise<void> => {
    await handleTailEvents(traces, environment);
  },
};

export default alertTail;

interface DedupeOperation {
  token: string;
  now: number;
  window_ms: number;
}

const readOperation = async (request: Request): Promise<DedupeOperation | null> => {
  try {
    const value = (await request.json()) as Partial<DedupeOperation>;
    if (
      typeof value.token !== "string" ||
      value.token.length > 128 ||
      typeof value.now !== "number" ||
      !Number.isFinite(value.now) ||
      typeof value.window_ms !== "number" ||
      !Number.isFinite(value.window_ms) ||
      value.window_ms < 1
    ) {
      return null;
    }
    return value as DedupeOperation;
  } catch {
    return null;
  }
};
