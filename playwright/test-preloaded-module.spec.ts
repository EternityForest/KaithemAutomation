import { test, expect } from "@playwright/test";
import { login, logout, waitForTasks } from "./util";
/*This file tests a module that gets loaded in testing_server.py
 */

test("test", async ({ page }) => {
  await login(page);

  // Device conflict between the twi preloaded modules should put an error notice on the main page.
  await expect(
    page.getByText(
      "Error in resource test_preloaded_ext_module,PreloadedDemoDevice: Device with"
    )
  ).toBeVisible();

  await page.getByRole("link", { name: "󰓻 Tags" }).click();

  await page
    .getByRole("link", { name: "/test_preloaded_module", exact: true })
    .scrollIntoViewIfNeeded();

  await expect(
    page.getByRole("link", { name: "/test_preloaded_module", exact: true })
  ).toBeVisible();

  // There should be a chandler board
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "TestingServerModule" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();

  await waitForTasks(page);
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
    .getByRole("link", { name: "NonexistenttypePreloadeddemodevice" })
    .click();
  await expect(
    page.getByText("This device does not have support").first()
  ).toContainText("This device");

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "TestingServerModule" }).click();

  // This is the nonsense resource type
  await expect(page.getByText("Unknown resource type:")).toBeVisible();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();

  // We also have an external module which should be exactly the same
  // But it loads after in the deterministing module name sort order so it should have errors and
  // conflicts
  await expect(
    page.getByRole("link", { name: "test_preloaded_ext_module" })
  ).toBeVisible();

  // Ensure we show the location for the ext module
  await expect(page.getByText("/dev/shm")).toBeVisible();

  await expect(
    page.getByRole("link", { name: "TestingServerModule" })
  ).toBeVisible();

  await page.getByRole("link", { name: "test_preloaded_ext_module" }).click();
  await expect(
    page.getByRole("link", { name: "TestingServerPreloadedBoard" }).first()
  ).toBeVisible();
  await expect(
    page.getByText("nonsense-resource", { exact: true })
  ).toBeVisible();

  await expect(page.getByText("Device with this name already").first()).toBeVisible();

  // Make sure apps from ext module load
  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await expect(
    page
      .getByTestId("app-test_preloaded_ext_module_testingserverpreloadedboard")
      .getByRole("link", { name: "TestingServerPreloadedBoard" })
  ).toBeVisible();

  await logout(page);
});
