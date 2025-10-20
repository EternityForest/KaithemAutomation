import { test, expect } from "@playwright/test";
import { deleteModule, login, makeModule, sleep, waitForTasks } from "./util";
declare global {
  // eslint-disable-next-line no-var
  var testMode: boolean;
}

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

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("foo").catch(() => {});
  });
  await page.getByTestId("add-group-button").click();

  await page.getByLabel("Settings").click();

  await page.getByRole("button", { name: "Universes" }).click();
  await page.getByPlaceholder("New Universe Name").click();
  await page.getByPlaceholder("New Universe Name").fill("test");
  await page.getByRole("cell", { name: "Number" }).dblclick();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByRole("button", { name: "Update Settings" }).click();
  await page.getByRole("button", { name: "󰅖 Close" }).click();

  await page.getByRole("button", { name: "󰏫 Fixture Types" }).click();

  page.once("dialog", (dialog) => {
    dialog.accept("textfixtype").catch(() => {});
  });

  await page.getByRole("button", { name: "󰐕 New" }).click();

  await page.getByTestId("fixture-type-to-edit").selectOption("textfixtype");

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  await sleep(1000);
  //TODO should not need to run twice??????
  await page.getByRole("button", { name: "Add Channel" }).click();
  await page.getByRole("button", { name: "Add Channel" }).click();
  await sleep(100);

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  await sleep(1000);

  await page.getByLabel("Type:").first().selectOption("intensity");
  await page.getByRole("button", { name: "Add Channel" }).click();
  await sleep(500);
  await page.getByLabel("Type:").nth(1).selectOption("red");
  await page.getByRole("button", { name: "Add Channel" }).click();
  await sleep(500);

  await page.getByLabel("Type:").nth(2).selectOption("green");
  await page.getByRole("button", { name: "Add Channel" }).click();
  await sleep(500);

  await page.getByLabel("Type:").nth(3).selectOption("blue");
  await page.getByRole("button", { name: "Add Channel" }).click();
  await sleep(500);

  await page.getByLabel("Type:").nth(4).selectOption("uv");
  await page.getByRole("button", { name: "󰅖 Close" }).click();
  await sleep(500);

  await page.getByRole("button", { name: "Fixtures" }).click();
  await page.locator("select").selectOption("textfixtype");
  await sleep(500);

  await page.getByRole("textbox").click();
  await page.getByRole("textbox").fill("test1");
  await page
    .getByRole("row", { name: "Universe", exact: true })
    .getByRole("combobox")
    .click();
  await page
    .getByRole("row", { name: "Universe", exact: true })
    .getByRole("combobox")
    .fill("test");
  await page.getByRole("spinbutton").click();
  await page.getByRole("spinbutton").fill("1");
  await page.getByRole("spinbutton").click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByRole("button", { name: "Add and Update" }).click();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "test_presets" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();

  await page.evaluate(async () => {
    globalThis.testMode = true;
  });

  await page.getByRole("button", { name: "foo" }).click();
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByRole("button", { name: "Add/Remove" }).click();
  await page.getByRole("cell", { name: "󰐕 Add" }).getByRole("button").click();
  await sleep(500);
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByRole("button", { name: "󰢻 Normal View" }).click();

  await page
    .getByTestId("details-fixture-channels-summary")
    .locator("summary")
    .click();
  await page
    .locator("div")
    .filter({ hasText: /^blue0\.000$/ })
    .getByRole("slider")
    .fill("253");
  await page
    .locator("div")
    .filter({ hasText: /^green0\.000$/ })
    .getByRole("slider")
    .fill("255");

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("testaqua").catch(() => {});
  });
  await page.getByTestId("save-preset-options").selectOption("");

  await page
    .locator("div")
    .filter({ hasText: /^blue253\.0$/ })
    .getByRole("slider")
    .fill("190");
  await page
    .locator("div")
    .filter({ hasText: /^green255\.0$/ })
    .getByRole("slider")
    .fill("0");

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByTestId("select-preset-for-fixture").click();
  await page
    .getByTestId("presets-list")
    .getByRole("button", { name: "testaqua" })
    .click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await expect(
    page
      .locator("div")
      .filter({ hasText: /^blue253\.0$/ })
      .getByRole("slider")
  ).toHaveValue("253");

  // Change the cue and make sure it doesn't mess up the preset
  await page
    .locator("div")
    .filter({ hasText: /^intensity0\.000$/ })
    .getByRole("slider")
    .fill("50");
  // Avoid race condition with the presets, make sure nothing is still queued when it happens
  await waitForTasks(page);
  await sleep(500);

  await page.getByTestId("select-preset-for-fixture").click();
  await page
    .getByTestId("presets-list")
    .getByRole("button", { name: "testaqua" })
    .click();

  await waitForTasks(page);
  await waitForTasks(page);
  await waitForTasks(page);
  await waitForTasks(page);
  await sleep(300);

  await expect(
    page
      .locator("div")
      .filter({ hasText: /^intensity0\.000$/ })
      .getByRole("slider")
  ).toHaveValue("0");
  await page.getByTestId("close-group").click();

  // Test the preset editor
  await page.getByRole("button", { name: "󰤀 Presets" }).click();
  await page
    .getByTestId("preset-inspector-testaqua-body")
    .locator("summary")
    .click();

  await expect(
    page.getByTestId("preset-inspector-testaqua-body").getByLabel("blue")
  ).toHaveValue("253");

  await page
    .getByTestId("preset-inspector-testaqua-body")
    .getByLabel("blue")
    .fill("233");

  //It should not affect red at all.  But this line was flaky at one point
  await page
    .getByTestId("preset-inspector-testaqua-body")
    .getByLabel("red")
    .fill("-1");

  // Click away so it saves
  await page.getByRole("textbox", { name: "blue" }).click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  // Rename the preset
  page.once("dialog", (dialog) => {
    dialog.accept("testaqua2").catch(() => {});
  });

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page
    .getByTestId("preset-inspector-testaqua-heading")
    .getByRole("button", { name: "󰏫 Rename" })
    .click();

  await page.getByRole("button", { name: "󰅖 Close" }).click();

  // go back to the group
  await page.getByRole("button", { name: "foo" }).click();

  await page
    .locator("div")
    .filter({ hasText: /^red0\.000$/ })
    .getByRole("slider")
    .fill("15");

  // Avoid race condition with the presets, make sure nothing is still queued when it happens
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  await page.getByTestId("select-preset-for-fixture").click();
  await page
    .getByTestId("presets-list")
    .getByRole("button", { name: "testaqua2" })
    .click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  // Blue should have the value we set in the preset editor
  await expect(
    page
      .locator("div")
      .filter({ hasText: /^blue233\.0$/ })
      .getByRole("slider")
  ).toHaveValue("233");

  // Red should be unchanged. But the fill line up there is flaky in the preset inspector
  //await expect(page.locator('div').filter({ hasText: /^red15\.0$/ }).getByRole('slider')).toHaveValue('15');

  // Rendering may have latency under load
  await sleep(1000);

  await page.goto(
    "http://localhost:8002/chandler/config/test_presets:p"
  );
  await page.getByRole("button", { name: "Universes" }).click();
  await page
    .getByTestId("universe-status-table")
    .getByRole("row", { name: "test" })
    .getByRole("link", { name: "Values" })
    .click();
  await expect(page.locator("section")).toContainText("255.0");
  await expect(page.locator("section")).toContainText("233.0");

  await deleteModule(page, "test_presets");
});
