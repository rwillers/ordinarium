import {
  createRequestId,
  emitTelemetry,
  errorCategory,
  REQUEST_ID_HEADER,
} from "./telemetry.ts";

const MAX_REQUEST_BYTES = 1024 * 1024;
const MAX_SQL_BYTES = 64 * 1024;
const MAX_PARAMS = 500;
const MAX_BATCH_STATEMENTS = 50;
const D1_READ_RETRY_DELAYS_MS = [250, 1_000, 2_500] as const;
const RETRYABLE_D1_ERROR_FRAGMENTS = [
  "Network connection lost",
  "caused object to be reset",
  "reset because its code was updated",
  "Cannot resolve D1 DB due to transient issue",
  "Replica disconnected from primary",
] as const;

type D1ReadRetryOptions = {
  sleep?: (milliseconds: number) => Promise<void>;
  random?: () => number;
};

type StatementInput = {
  sql: string;
  params: unknown[];
};

type BridgePayload = {
  operation: string;
  sql?: unknown;
  params?: unknown;
  statements?: unknown;
  sequence?: unknown;
};

type NormalizedMetadata = {
  changes: number;
  last_row_id: number | null;
  rows_read: number | null;
  rows_written: number | null;
  duration_ms: number | null;
};

export const handleD1Request = async (
  request: Request,
  database: D1Database,
  retryOptions: D1ReadRetryOptions = {},
): Promise<Response> => {
  if (request.method !== "POST") {
    return jsonError("method_not_allowed", 405);
  }

  const requestId =
    request.headers.get(REQUEST_ID_HEADER) || createRequestId();
  let databaseOperation = "unknown";
  try {
    const payload = await readPayload(request);
    databaseOperation = normalizedOperation(payload.operation);
    switch (payload.operation) {
      case "fetch_one":
        return await fetchOne(
          database,
          parseStatement(payload),
          requestId,
          retryOptions,
        );
      case "fetch_all":
        return await fetchAll(
          database,
          parseStatement(payload),
          requestId,
          retryOptions,
        );
      case "execute":
        return await execute(database, parseStatement(payload));
      case "batch":
        return await executeBatch(database, parseBatch(payload.statements));
      case "allocate_id":
        return await allocateId(database, parseSequence(payload.sequence));
      default:
        return jsonError("unknown_operation", 400);
    }
  } catch (error: unknown) {
    if (error instanceof BridgeInputError) {
      return jsonError(error.code, error.status);
    }
    emitTelemetry("error", "d1_operation_failure", {
      request_id: requestId,
      container_role: "d1-bridge",
      error_category: errorCategory(error),
      database_operation: databaseOperation,
    });
    return jsonError("database_operation_failed", 503);
  }
};

const fetchOne = async (
  database: D1Database,
  input: StatementInput,
  requestId: string,
  retryOptions: D1ReadRetryOptions,
) => {
  const row = await retryRead(
    () => prepare(database, input).first<Record<string, unknown>>(),
    requestId,
    "fetch_one",
    retryOptions,
  );
  return Response.json({ ok: true, row });
};

const fetchAll = async (
  database: D1Database,
  input: StatementInput,
  requestId: string,
  retryOptions: D1ReadRetryOptions,
) => {
  const result = await retryRead(
    () => prepare(database, input).run<Record<string, unknown>>(),
    requestId,
    "fetch_all",
    retryOptions,
  );
  return Response.json({
    ok: true,
    rows: result.results,
    metadata: normalizeMetadata(result.meta),
  });
};

const execute = async (database: D1Database, input: StatementInput) => {
  const result = await prepare(database, input).run();
  return Response.json({ ok: true, metadata: normalizeMetadata(result.meta) });
};

const executeBatch = async (database: D1Database, inputs: StatementInput[]) => {
  const results = await database.batch(inputs.map((input) => prepare(database, input)));
  return Response.json({
    ok: true,
    results: results.map((result) => ({
      rows: result.results,
      metadata: normalizeMetadata(result.meta),
    })),
  });
};

const allocateId = async (database: D1Database, sequence: string) => {
  const row = await database
    .prepare(
      "update id_sequences set next_value=next_value + 1 where name=? returning next_value - 1 as id",
    )
    .bind(sequence)
    .first<{ id: number }>();
  if (!row) {
    return jsonError("unknown_sequence", 400);
  }
  return Response.json({ ok: true, id: row.id });
};

const prepare = (database: D1Database, input: StatementInput) =>
  database.prepare(input.sql).bind(...input.params);

const retryRead = async <T>(
  operation: () => Promise<T>,
  requestId: string,
  databaseOperation: string,
  options: D1ReadRetryOptions,
): Promise<T> => {
  const sleep = options.sleep ?? wait;
  const random = options.random ?? Math.random;
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation();
    } catch (error: unknown) {
      const delay = D1_READ_RETRY_DELAYS_MS[attempt];
      if (delay === undefined || !isRetryableD1Error(error)) {
        throw error;
      }
      const retryDelayMs = jitteredDelay(delay, random());
      emitTelemetry("warn", "d1_operation_retry", {
        request_id: requestId,
        container_role: "d1-bridge",
        error_category: errorCategory(error),
        database_operation: databaseOperation,
        attempts: attempt + 1,
        retry_delay_ms: retryDelayMs,
      });
      await sleep(retryDelayMs);
    }
  }
};

const isRetryableD1Error = (error: unknown): boolean => {
  const message = error instanceof Error ? error.message : String(error);
  return RETRYABLE_D1_ERROR_FRAGMENTS.some((fragment) =>
    message.includes(fragment),
  );
};

const jitteredDelay = (baseDelayMs: number, randomValue: number): number =>
  Math.round(baseDelayMs * (0.75 + Math.min(1, Math.max(0, randomValue)) * 0.5));

const wait = (milliseconds: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const normalizedOperation = (value: unknown): string =>
  typeof value === "string" &&
  ["fetch_one", "fetch_all", "execute", "batch", "allocate_id"].includes(value)
    ? value
    : "unknown";

const readPayload = async (request: Request): Promise<BridgePayload> => {
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > MAX_REQUEST_BYTES) {
    throw new BridgeInputError("request_too_large", 413);
  }
  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_REQUEST_BYTES) {
    throw new BridgeInputError("request_too_large", 413);
  }
  try {
    const payload: unknown = JSON.parse(new TextDecoder().decode(body));
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new BridgeInputError("invalid_json", 400);
    }
    return payload as BridgePayload;
  } catch (error: unknown) {
    if (error instanceof BridgeInputError) {
      throw error;
    }
    throw new BridgeInputError("invalid_json", 400);
  }
};

const parseStatement = (payload: BridgePayload): StatementInput => {
  if (typeof payload.sql !== "string" || !payload.sql.trim()) {
    throw new BridgeInputError("invalid_statement", 400);
  }
  if (new TextEncoder().encode(payload.sql).byteLength > MAX_SQL_BYTES) {
    throw new BridgeInputError("statement_too_large", 413);
  }
  const params = payload.params ?? [];
  if (!Array.isArray(params) || params.length > MAX_PARAMS || !params.every(isScalar)) {
    throw new BridgeInputError("invalid_params", 400);
  }
  return { sql: payload.sql, params };
};

const parseBatch = (value: unknown): StatementInput[] => {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_BATCH_STATEMENTS) {
    throw new BridgeInputError("invalid_batch", 400);
  }
  return value.map((statement) => {
    if (!statement || typeof statement !== "object" || Array.isArray(statement)) {
      throw new BridgeInputError("invalid_statement", 400);
    }
    return parseStatement(statement as BridgePayload);
  });
};

const parseSequence = (value: unknown): string => {
  if (typeof value !== "string" || !/^[a-z][a-z0-9_]{0,63}$/.test(value)) {
    throw new BridgeInputError("invalid_sequence", 400);
  }
  return value;
};

const isScalar = (value: unknown) =>
  value === null || ["string", "number", "boolean"].includes(typeof value);

const normalizeMetadata = (meta: D1Meta): NormalizedMetadata => ({
  changes: meta.changes ?? 0,
  last_row_id: meta.last_row_id ?? null,
  rows_read: meta.rows_read ?? null,
  rows_written: meta.rows_written ?? null,
  duration_ms: meta.duration ?? null,
});

const jsonError = (error: string, status: number) =>
  Response.json({ ok: false, error }, { status });

class BridgeInputError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.code = code;
    this.status = status;
  }
}
