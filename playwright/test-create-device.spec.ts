import { test, expect } from "@playwright/test";
import { login, makeModule, deleteModule, sleep } from "./util";

test("test", async ({ page }) => {
  test.setTimeout(2_400_000);

  await login(page);
  // Make a module to put the device in

  await makeModule(page, "devmodule");

  // Make a device
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-device").click();
  await page.getByLabel("Target Resource Name:").click();
  await page.getByLabel("Target Resource Name:").fill("testdevice");
  await page.getByText("Target Module: Target").click();
  await page.getByPlaceholder("Click for dropdown").click();
  await page.getByPlaceholder("Click for dropdown").selectOption("DemoDevice");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByRole("button", { name: "Submit" }).click();

  // Should be on devices page now, make sure it exists and works
  await expect(page.locator("section")).toContainText("Testdevice");
  await expect(page.locator("section")).toContainText("random");

  // Go to the page for that specific device
  await page.getByRole("link", { name: "Testdevice", exact: true }).click();

  await page.locator("b").filter({ hasText: "Settings" }).locator("i").click();
  await sleep(1000);
  await page
    .getByRole("textbox", { name: "Fixed Number Multiplier" })
    .fill("2");
  await sleep(1000);
  await page.getByRole("button", { name: "Save settings" }).click();

  // Back on index page

  await page
    .locator("article")
    .filter({ hasText: "Testdevice do_nothing trigger" })
    .getByLabel("useless_toggle")
    .check();

  await page.getByRole("button", { name: "Confirm" }).click();

  await page.getByRole("link", { name: "Testdevice", exact: true }).click();
  await page.getByText("Settings", { exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Fixed Number Multiplier" })
  ).toHaveValue("2");

  await expect(
    page.getByRole("link", { name: "random", exact: true })
  ).toBeVisible();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("12.0").catch(() => {});
  });
  await page.getByTestId("set-val-button-random").click();

  await expect(page.getByTestId("val-span-useless_toggle")).toContainText(
    "1.0"
  );
  await expect(page.getByTestId("val-span-random")).toContainText("12.0");

  await deleteModule(page, "devmodule");
});
