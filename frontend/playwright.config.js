import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure", screenshot: "only-on-failure" },
  globalSetup: "./e2e/global-setup.js",
  webServer: [
    {
      command: "set E2E_TEST_MODE=1&& python manage.py runserver 127.0.0.1:8001 --noreload",
      cwd: "../backend",
      url: "http://127.0.0.1:8001/api/auth/me/",
      timeout: 30_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173 --mode e2e",
      url: "http://127.0.0.1:5173",
      timeout: 30_000,
      reuseExistingServer: false,
    },
  ],
});
