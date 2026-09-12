import { expect, test } from "@playwright/test";

const admin = { username: "e2e-admin", password: "E2EPassword123!" };
const student = { username: "e2e-student", password: "E2EPassword123!" };

async function signIn(page, account) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(account.username);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function signOut(page) {
  await page.getByRole("button", { name: /logout/i }).click();
  await expect(page).toHaveURL(/\/login/);
}

test.describe.serial("DSA Tracker browser workflows", () => {
  test("admin and student roles route to their permitted dashboards", async ({ page }) => {
    await signIn(page, admin);
    await expect(page).toHaveURL(/\/admin/);
    await expect(page.getByRole("heading", { name: "Admin Dashboard" })).toBeVisible();
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/admin/);
    await signOut(page);

    await signIn(page, student);
    await expect(page).toHaveURL(/\/dashboard/);
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("student sees public cases but must assign before Monaco actions are enabled", async ({ page }) => {
    await signIn(page, student);
    await page.goto("/dashboard");
    await page.getByText("E2E Echo", { exact: true }).click();
    await expect(page.getByText("secret-e2e-input")).toHaveCount(0);
    await expect(page.getByText("Assign this question to start coding.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Run Code" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Submit Solution" })).toBeDisabled();
  });

  test("student assigns, runs and submits without exposing hidden test data", async ({ page }) => {
    await signIn(page, student);
    await page.goto("/questions/1");
    await page.getByRole("button", { name: /assign question/i }).click();
    await expect(page.getByRole("button", { name: "Run Code" })).toBeEnabled();
    await page.getByRole("button", { name: "Run Code" }).click();
    await expect(page.getByText(/Public tests: 1 \/ 1 passed/)).toBeVisible();
    await page.getByRole("button", { name: "Submit Solution" }).click();
    await expect(page.getByText("🎉 ACCEPTED")).toBeVisible();
    await expect(page.getByText("secret-e2e-input")).toHaveCount(0);
    await signOut(page);
  });

  test("final submission notifies admin, opens exact code and provides a mailto remarks action", async ({ page }) => {
    await signIn(page, admin);
    await page.getByRole("button", { name: "Admin notifications" }).click();
    await expect(page.getByText("NEW CODE SUBMISSION")).toBeVisible();
    await page.getByText("View Submission", { exact: true }).click();
    await expect(page).toHaveURL(/tab=submissions/);
    await expect(page.getByText("Student submitted code")).toBeVisible();
    await expect(page.getByText("E2E Echo", { exact: true })).toBeVisible();
    const remarks = page.getByRole("link", { name: "Remarks" });
    await expect(remarks).toHaveAttribute("href", /mailto:student%40example\.test/);
  });
});
