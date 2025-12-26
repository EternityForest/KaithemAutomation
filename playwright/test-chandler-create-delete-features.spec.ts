import { test, expect } from "@playwright/test";
import {
  login,
  logout,
  makeModule,
  deleteModule,
  waitForTasks,
  sleep,
} from "./util";

test("test", async ({ page }) => {
  test.setTimeout(600_000);
  await page.setDefaultTimeout(15_000);

  await page.goto("http://localhost:8002/");
  await login(page);

  await makeModule(page, "foo");

  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-chandler_board").click();
  await page.getByLabel("Resource Name").click();
  await page.getByLabel("Resource Name").fill("xyz");
  await page.getByRole("button", { name: "Submit" }).click();

  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await page.getByLabel("Extras").nth(1).click();
  await page.getByRole("link", { name: "Editor" }).click();

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("test").catch(() => {});
  });
  await page.getByTestId("add-group-button").click();

  await page.getByRole("button", { name: "test" }).click();

  await page.getByPlaceholder("New cue name").click();
  await page.getByPlaceholder("New cue name").fill("foo");

  await page.getByRole("button", { name: "󰐕 Add Cue" }).click();
  await expect(
    page.locator("#cuesbox").getByText("foo", { exact: true })
  ).toBeVisible();

  await page.locator("#cuesbox").getByText("foo", { exact: true }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page.getByRole("button", { name: "󰆴 Delete Current" }).click();

  await expect(
    page.locator("#cuesbox").getByText("foo", { exact: true })
  ).toBeHidden();

  await page.getByTestId("cue-media-dialog-button").click();
  await page
    .getByTestId("media-browser-container")
    .getByText("<TOP DIRECTORY>")
    .click();
  await page
    .getByTestId("media-browser-container")
    .getByText("kaithem/data/static/")
    .click();
  await page
    .getByTestId("media-browser-container")
    .getByText("kaithem/data/static/sounds/")
    .click();
  await page
    .getByRole("row", { name: "220176__gameaudio__confirm-" })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("row", { name: "320181__dland__hint.opus Set(" })
    .getByRole("button")
    .nth(4)
    .click();
  await page.getByTestId("close-cue-media").click();
  await page.locator("#cuesbox").getByText("x220176 gameaudio confirm").click();
  await expect(page.getByText("Sound: sounds/")).toBeVisible();

  await page.locator("#cuesbox").getByText("x320181 dland hint").click();
  await expect(page.getByText("Slide: sounds/")).toBeVisible();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page.getByRole("button", { name: "󰆴 Delete Current" }).click();

  await expect(
    page.locator("#cuesbox").getByText("x320181 dland hint")
  ).toBeHidden();

  await page.locator("#cuesbox").getByText("x220176 gameaudio confirm").click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page.getByRole("button", { name: "󰆴 Delete Current" }).click();

  await waitForTasks(page);
  await sleep(300);

  await expect(
    page.locator("#cuesbox").getByText("x220176 gameaudio confirm")
  ).toBeHidden();

  await page.getByTestId("cue-logic-button").click();
  await page.getByRole("button", { name: "Add Rule" }).click();
  await page.getByRole("button", { name: "Add Action" }).click();
  await page.getByRole("button", { name: "pass" }).click();
  await page.getByRole("button", { name: "Delete Command", exact: true }).click();
  await page
    .locator("#blockInspectorCommand")
    .getByRole("button", { name: "󰅖 Close" })
    .click();

  // "Pass" is the default action when you add a new action
  await expect(page.getByRole("button", { name: "pass" })).toBeHidden();

  await page.getByRole("button", { name: "On cue.enter" }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page
    .getByRole("button", { name: "Remove binding and all actions" })
    .click();

  await waitForTasks(page);
  await sleep(300);
  await expect(page.getByRole("button", { name: "On cue.enter" })).toBeHidden();

  await page.getByTestId("close-logic").click();
  await page.getByTestId("close-group").click();
  await page.getByRole("button", { name: "test" }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page.getByLabel("Delete Group").click();

  await waitForTasks(page);
  // Todo delete group should be synchronous
  await sleep(1200);
  await expect(page.getByRole("button", { name: "test" })).toBeHidden();

  // Ensure we can remake one with same name
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("test").catch(() => {});
  });
  await page.getByTestId("add-group-button").click();


  await sleep(250);

  await page.getByRole("button", { name: "󰤀 Presets" }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page
    .getByTestId("preset-inspector-Cinnamon-heading")
    .getByRole("button", { name: "󰆴 Delete" })
    .click();

  await expect(
    page.getByTestId("preset-inspector-Cinnamon-heading")
  ).toBeHidden();
  await deleteModule(page, "foo");
  await logout(page);
});
