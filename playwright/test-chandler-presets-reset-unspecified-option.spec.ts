import { test, expect } from "@playwright/test";
import { deleteModule, login, makeModule, waitForTasks } from "./util";

test("test", async ({ page }) => {
  test.setTimeout(120_000);

  await login(page);

  makeModule(page, "test_presets");

  await page.setDefaultTimeout(15_000);

  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-chandler_board").click();
  await page.getByLabel("Resource Name").click();
  await page.getByLabel("Resource Name").fill("p");
  await page.getByRole("button", { name: "Submit" }).click();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "test_presets" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();

  // Make a fixture that just has a red and UV channel
  await page.getByLabel("Settings").click();
  await page.getByRole("button", { name: "󰏫 Fixture Types" }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("testwithuv").catch(() => {});
  });

  await page.getByRole("button", { name: "󰐕 New" }).click();
  await page.getByTestId("fixture-type-to-edit").selectOption("testwithuv");
  await page.getByRole("button", { name: "Add Channel" }).click();
  await page.getByRole("button", { name: "Add Channel" }).click();
  await page.getByLabel("Type:").nth(1).selectOption("uv");

  await page.getByRole("button", { name: "Fixtures" }).click();
  await page
    .getByRole("row", { name: "Name", exact: true })
    .getByRole("cell")
    .nth(1)
    .click();
  await page
    .getByRole("row", { name: "Name", exact: true })
    .getByRole("textbox")
    .fill("testwuv");
  await page.getByTestId("new-fixture-type-select").selectOption("testwithuv");
  await page
    .getByRole("row", { name: "Universe", exact: true })
    .getByRole("combobox")
    .fill("dmx");
  await page.getByRole("spinbutton").fill("67");
  await page.getByRole("button", { name: "Add and Update" }).click();

  await waitForTasks(page);

  await page.getByRole("link", { name: "󱒕 Modules" }).click();

  // Add fixture to the cue
  await page.getByRole("link", { name: "test_presets" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("testgroup1").catch(() => {});
  });
  await page.getByTestId("add-group-button").click();

  await page.getByRole("button", { name: "testgroup1" }).click();
  await page.getByTestId("add-rm-fixtures-button").click();
  await page.getByRole("cell", { name: "󰐕 Add" }).getByRole("button").click();
  await page
    .getByTestId("details-fixture-channels-summary")
    .locator("summary")
    .click();
  await page.getByRole("button", { name: "󰢻 Normal View" }).click();

  // set to nonsense
  await page
    .locator("div.hfader")
    .filter({ hasText: "red" })
    .getByRole("slider")
    .fill("175");
  await page
    .locator("div.hfader")
    .filter({ hasText: "uv" })
    .getByRole("slider")
    .fill("126");

  await page
    .getByTestId("details-fixture-channels-summary")
    .locator("summary")
    .click();
  await page
    .getByTestId("details-fixture-channels-summary")
    .locator("summary")
    .click();
  await page.getByTestId("select-preset-for-fixture").click();

  // Pure red is a default preset that does not specifify UV, uv still
  // gets reset to 0 because of the reset unspecified option
  // TODO use a less brittle custom preset
  await page.getByRole("button", { name: "Pure Red" }).click();
  await expect(
    page
      .locator("div.hfader")
      .filter({ hasText: "uv"})
      .getByRole("slider")
  ).toHaveValue("0");
  await expect(
    page
      .locator("div.hfader")
      .filter({ hasText: "red" })
      .getByRole("slider")
  ).toHaveValue("255");

  await page
    .locator("div.hfader")
    .filter({ hasText: "red" })
    .getByRole("slider")
    .fill("140");
  await page
    .locator("div.hfader")
    .filter({ hasText: "uv" })
    .getByRole("slider")
    .fill("145");
  await page.getByTestId("close-group").click();

  /// now disable the reset other channels option, watch it not affect the UV channel
  await page.getByRole("button", { name: "󰤀 Presets" }).click();
  await page
    .getByTestId("preset-inspector-Pure Red-body")
    .getByText("Values")
    .click();
  await page
    .getByTestId("preset-inspector-Pure Red-body")
    .getByLabel("Reset colors not specified")
    .uncheck();
  await page.getByRole("main").click();
  await page.getByRole("button", { name: "testgroup1" }).click();
  await page.getByTestId("select-preset-for-fixture").click();
  await page
    .getByTestId("presets-list")
    .getByRole("button", { name: "Pure Red" })
    .click();

  await expect(
    page
      .locator("div.hfader")
      .filter({ hasText: "red" })
      .getByRole("slider")
  ).toHaveValue("255");
  await expect(
    page
      .locator("div.hfader")
      .filter({ hasText: "uv" })
      .getByRole("slider")
  ).toHaveValue("145");

  await deleteModule(page, "test_presets");
});
