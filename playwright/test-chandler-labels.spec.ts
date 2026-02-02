import { test, expect } from "@playwright/test";
import {
  login,
  chandlerBoardTemplate,
  deleteModule,
  waitForTasks,
  sleep,
} from "./util";

test("test", async ({ page }) => {
  test.setTimeout(2_400_000);

  await login(page);
  const module = "PlaywrightChandlerTestModule6768";

  await chandlerBoardTemplate(page, module);

  await waitForTasks(page);

  // Give the default cue a label image
  await page.getByTestId("cue-media-dialog-button").click();
  await page
    .getByTestId("media-browser-container")
    .getByText("<TOP DIRECTORY>")
    .click();

  await page
    .getByTestId("media-browser-container")
    .getByText("Builtin")
    .click();
  await page
    .getByTestId("media-browser-container")
    .getByText("img/")
    .click();
  await page
    .getByTestId("media-browser-container")
    .getByText("16x9/")
    .click();

  await waitForTasks(page);
  await sleep(1000);

  await page
    .locator("tr")
    .filter({ hasText: "apples-display" })
    .getByRole("button", { name: "Set Label" })
    .click();

  await waitForTasks(page);

  await expect(
    page
      .locator("label")
      .filter({ hasText: "Label Image Preview" })
      .getByRole("img")
  ).toBeVisible();

  await expect(page.getByTestId("cue-label-image-control")).toHaveValue(
    "img/16x9/apples-display.avif"
  );

  await page.getByTestId("close-cue-media").click();
  await page.getByTestId("close-group").click();

  // TODO  also test the tiny preview images

  // Make sure they get used in commander
  await page.getByTestId("commander-link").click();
  await page.getByRole("button", { name: "tst1" }).click();

  await expect(
    page.getByRole("button", { name: "default" }).getByRole("img")
  ).toBeVisible();
  //We didn't set a label on that one, so it shouldn't have an image
  await expect(
    page.getByRole("button", { name: "c2" }).getByRole("img")
  ).toBeHidden();

  // Go to config page
  await page.getByRole("button", { name: "󰅖 Close" }).click();
  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await page
    .getByTestId("extras-button-playwrightchandlertestmodule6768_board1")
    .click();
  await page.getByRole("link", { name: "Config" }).click();
  await page.getByRole("button", { name: "Fixtures" }).click();

  // Create a fixture
  await page.locator("select").selectOption("3ch RGB");
  await page.getByRole("textbox").click();
  await page.getByRole("textbox").fill("test");
  await page
    .getByRole("row", { name: "Universe", exact: true })
    .getByRole("combobox")
    .click();
  await page
    .getByRole("row", { name: "Universe", exact: true })
    .getByRole("combobox")
    .fill("dmx");
  await page.getByTestId("newfixaddr").click();
  await page.getByTestId("newfixaddr").fill("34");
  await page.getByRole("button", { name: "Add and Update" }).click();

  //Give it an label image
  await page.getByRole("button", { name: "󰥶 Image" }).click();
  await page.getByText("<TOP DIRECTORY>").click();
  await page.getByText("Builtin").click();
  await page.getByText("img/").click();
  await page.getByText("16x9/").click();
  await page
    .locator("tr")
    .filter({ hasText: "old-bulb-on.avif Use" })
    .getByRole("button")
    .click();

  await sleep(3000);

  await page.getByRole("button", { name: "󰅖 Close" }).first().click();

  // Make sure we can see it in the chandler board
  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await page
    .getByTestId("extras-button-playwrightchandlertestmodule6768_board1")
    .click();
  await page.getByRole("link", { name: "Editor" }).click();
  await page.getByRole("button", { name: "tst1" }).click();
  await page.getByTestId("add-rm-fixtures-button").click();
  await page.getByTestId("add-fixture-to-cue-button").click();
  await expect(
    page.getByTestId("details-fixture-channels-summary").getByRole("img")
  ).toBeVisible();

  await deleteModule(page, module);
});
