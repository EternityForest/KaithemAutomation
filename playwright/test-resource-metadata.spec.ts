import { test, expect } from "@playwright/test";
import { login, makeModule, deleteModule } from "./util";

test("test", async ({ page }) => {
  test.setTimeout(2400000);

  await login(page);

  await makeModule(page, "TestDisableResource");

  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-chandler_board").click();
  await page.getByLabel("Resource Name").click();
  await page.getByLabel("Resource Name").fill("testdisable");
  await page.getByRole("button", { name: "Submit" }).click();

  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await page
    .getByTestId("extras-button-testdisableresource_testdisable")
    .click();
  await page.getByRole("link", { name: "Editor" }).click();

  await page.getByPlaceholder("New group name").click();
  await page.getByPlaceholder("New group name").fill("td1");
  await page.getByTestId("add-group-button").click();
  await expect(page.getByRole("button", { name: "td1" })).toBeVisible();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "TestDisableResource" }).click();

  // Disable the resource but also set a thumbnail
  await page.getByLabel("Resource Metadata").click();
  await page.getByLabel("Enabled").uncheck();
  await page.getByText("Display", { exact: true }).click();
  await page.getByLabel("Label Image URL").click();
  await page
    .getByLabel("Label Image URL")
    .fill("16x9/awesome-yellow-flower.avif");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("img", { name: "thumbnail" })).toBeVisible();
  await expect(page.getByText("(disabled)")).toBeVisible();

  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await expect(
    page.getByRole("link", { name: "testdisable" })
  ).not.toBeVisible();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "TestDisableResource" }).click();
  await page.getByLabel("Resource Metadata").click();
  await page.getByLabel("Enabled").check();
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("img", { name: "thumbnail" })).toBeVisible();

  await page.getByRole("link", { name: "󰏬 Edit" }).click();
  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await expect(page.getByRole("link", { name: "testdisable" })).toBeVisible();
  await page
    .getByTestId("extras-button-testdisableresource_testdisable")
    .click();
  await page.getByRole("link", { name: "Editor" }).click();

  await expect(page.getByRole("button", { name: "td1" })).toBeVisible();

  await deleteModule(page, "TestDisableResource");
});
