import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "corepack pnpm exec next start --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: !process.env.CI,
    env: {
      NEXT_PUBLIC_API_URL: "http://127.0.0.1:8787",
      NEXT_PUBLIC_E2E_AUTH_BYPASS: "true",
      NEXT_PUBLIC_ENABLE_DEMO_MERCHANT_SWITCHER: "true",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_test_ZHVtbXkuY2xlcmsuYWNjb3VudHMuZGV2JA",
      CLERK_SECRET_KEY: "sk_test_dummy",
      DRISHTI_E2E_AUTH_BYPASS: "true",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
