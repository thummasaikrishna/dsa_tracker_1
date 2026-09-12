import { execFileSync } from "node:child_process";
import { rmSync } from "node:fs";
import { resolve } from "node:path";

export default function globalSetup() {
  const backend = resolve(import.meta.dirname, "../../backend");
  const db = resolve(backend, "e2e.sqlite3");
  // Exact, dedicated path only; this is never the normal development database.
  rmSync(db, { force: true });
  const env = { ...process.env, E2E_TEST_MODE: "1" };
  execFileSync("python", ["manage.py", "migrate", "--noinput"], { cwd: backend, env, stdio: "inherit" });
  execFileSync("python", ["manage.py", "seed_e2e"], { cwd: backend, env, stdio: "inherit" });
}
