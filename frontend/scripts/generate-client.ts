/**
 * Generate TypeScript types from the backend OpenAPI spec.
 * Requires the backend to be running (default http://localhost:8000).
 *
 *   npm run generate-client
 */
import { execSync } from "node:child_process";

const SPEC = process.env.API_SPEC ?? "http://localhost:8000/openapi.json";
const OUT = "src/lib/openapi.d.ts";

execSync(
  `npx openapi-typescript ${SPEC} -o ${OUT}`,
  { stdio: "inherit" }
);
console.log(`Generated ${OUT} from ${SPEC}`);
