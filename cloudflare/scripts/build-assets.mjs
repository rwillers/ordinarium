import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";


const cloudflareDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(cloudflareDirectory, "..", "ordinarium", "static");
const destinationRoot = resolve(cloudflareDirectory, "dist");
const destination = resolve(destinationRoot, "static");

await rm(destinationRoot, { recursive: true, force: true });
await mkdir(destinationRoot, { recursive: true });
await cp(source, destination, { recursive: true });
