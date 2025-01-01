import { test, expect } from "@playwright/test";
import { login, logout } from "./util";
/*This file tests a module that gets loaded in testing_server.py
 */

test("test", async ({ page }) => {
  await login(page);

  await page.getByRole("link", { name: "󰓻 Tags" }).click();
  await expect(
    page.getByRole("link", { name: "/test_preloaded_module" })
  ).toBeVisible();

  // There should be a chandler board
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "TestingServerModule" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText(
    "cue2"
  );

  // Make sure the permission got loaded
  await page.getByRole("link", { name: "󰢻 Tools" }).click();
  await page.getByRole("link", { name: "󰡉 Users and Groups" }).click();
  await page.locator("li").filter({ hasText: "Administrators" }).click();
  await page.getByRole("link", { name: "Administrators" }).click();
  await expect(
    page.getByRole("heading", { name: "testpermission1234" })
  ).toBeVisible();

  await page.getByRole("link", { name: "󰘚 Devices" }).click();
  await page.getByRole("link", { name: "󰘚 Devices" }).click();

  await expect(
    page.getByRole("link", { name: "PreloadedDemoDevice", exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "PreloadedDemoDevice/subdevice" })
  ).toBeVisible();

  // Ensure it displays the fact it's not supported
  await page
    .getByRole("link", { name: "NonexistentTypePreloadedDemoDevice" })
    .click();
  await expect(page.getByText("This device type has no").first()).toBeVisible();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "TestingServerModule" }).click();

  // This is the nonsense resource type
  await expect(page.getByText("Unknown resource type:")).toBeVisible();

  await logout(page);
});
