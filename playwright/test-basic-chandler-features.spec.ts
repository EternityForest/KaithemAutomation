import { test, expect } from "@playwright/test";
import {
  sleep,
  login,
  logout,
  chandlerBoardTemplate,
  deleteModule,
  makeTagPoint,
  waitForTasks,
} from "./util";

/*
Create a module, make a chandler board, test very simple logic,
make sure tag output features work.
*/
test("test", async ({ page }) => {
  test.setTimeout(2_400_000);
  page.setDefaultTimeout(15_000);

  await login(page);
  const module = "PlaywrightChandlerTestModule";

  await chandlerBoardTemplate(page, module);

  // Cue logic
  await page.getByTestId("cue-logic-button").click();

  // Add rule and edit the default example action
  await page.getByRole("button", { name: "Add Rule" }).click();
  await page.getByRole("button", { name: "goto" }).click();

  // Action params editor has a cue field
  // When we go into default cue it should redirect to c2
  await page.getByTestId("command-arg-cue").fill("c2");
  //Dismiss popup selecter by clicking outside
  await page.getByRole("heading", { name: "Automation Logic" }).click();

  await page.getByTestId("close-logic").click();

  // Go on default cue
  await page.getByRole("button", { name: "Go", exact: true }).first().click();

  // Check that worked
  await expect(page.getByRole("article")).toContainText("c2");

  // make cue c3, navigate to it
  await page.getByPlaceholder("New cue name").click();
  await page.getByPlaceholder("New cue name").fill("c3");
  await page.getByRole("button", { name: "Add Cue" }).click();
  await page.getByRole("cell", { name: "c3" }).click();

  // Go in c3, check we're there
  await page
    .getByRole("row", { name: "c3" })
    .getByRole("button", { name: "Go", exact: true })
    .click();
  await expect(page.getByRole("article")).toContainText("c3");

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.dismiss().catch(() => {});
  });
  
  // Delete c3
  await page.getByRole("button", { name: "Delete Current" }).click();
  // Go to c2
  await page.getByRole("button", { name: "Go", exact: true }).first().click();
  await expect(page.getByRole("article")).toContainText("c2");

  // Also some cue text
  await page.getByTestId("cue-text-dialog-button").click();
  await page.getByTestId("cuetext").fill("cuetext");
  await page.getByTestId("close-cue-text").click();

  // Make a new cue from the alert sound
  await page.getByTestId("cue-media-dialog-button").click();
  await page.getByRole("list").getByText("Refresh").click();

  await page
    .getByTestId("media-browser-container")
    .getByText("Builtin", { exact: true })
    .click();
  await page
    .getByTestId("media-browser-container")
    .getByText("sounds/", { exact: true })
    .click();
  
  await page
    .getByRole("row", { name: "72125" })
    .getByRole("button", {name: "New(sound)"})
    .click();
  

  await expect(page.locator("#cuesbox")).toContainText(
    "sweetalertsound1"
  );

  await page.getByTestId("close-cue-media").click();

  // Set the cue length to 0 so it doesn't end too soon
  await page
    .getByRole("cell", { name: "0.01" })
    .getByRole("combobox")
    .dblclick();
  await page
    .getByRole("cell", { name: "0.01" })
    .getByRole("combobox")
    .fill("0");
  await page.getByPlaceholder("New cue name").click();
  await page
    .getByRole("row", { name: "x72125" })
    .getByRole("button", { name: "Go", exact: true })
    .click();

  //Select the group box in the sidebar that tells us what the cue is
  await expect(page.getByTestId("sidebar-active-cue-name")).toHaveText(
    /.*x72125 *kizilsungur *sweetalertsound1.*/
  );
  // Channel adding tab
  await page.getByTestId("add-rm-fixtures-button").click();
  // Add raw dmx channek;
  await page.getByLabel("Universe").fill("dmx");

  // Click elsewhere to make dropdown suggestions box go
  await page.getByTestId("add-rm-fixtures-button").click();

  await page.getByLabel("Channel").fill("25");
  // Click elsewhere to make dropdown suggestions box go
  await page.getByTestId("add-rm-fixtures-button").click();

  await page.getByTestId("add-channel-to-cue-button").click();
  await expect(page.getByRole("main")).toContainText("dmx");

  await expect(page.getByRole("main")).toContainText("25");

  // Click elsewhere to make dropdown suggestions box go
  await page.getByTestId("add-rm-fixtures-button").click();

  await page.getByRole("button", { name: "Normal View" }).click();

  await page.locator("summary").filter({ hasText: "Channels" }).click();
  await page
    .locator("article")
    .filter({ hasText: "dmx" })
    .getByRole("slider")
    .fill("130");
  await expect(page.getByRole("main")).toContainText("130.0");

  // Make a tag point
  await makeTagPoint(page, module, "test_chandler_tag");

  // Go back to the light board and add the tag point
  // to the cue
  await page.getByRole("link", { name: "Modules" }).click();
  await page.getByRole("link", { name: module }).click();
  await page.getByRole("link", { name: "Edit" }).click();

  await page.evaluate(async () => {
    globalThis.testMode = true;
  });

  await page.getByRole("button", { name: "tst1" }).click();
  await page.getByTestId("add-rm-fixtures-button").click();
  await page.getByLabel("Tag", { exact: true }).click();
  await page.getByLabel("Tag", { exact: true }).fill("/test_chandler_tag");
  // Click elsewhere to make dropdown suggestions box go
  await page.getByTestId("add-rm-fixtures-button").click();

  await page.getByTestId("add-tag-to-cue-button").click();
  await page.locator("summary").filter({ hasText: "Channels" }).click();
  await page
    .locator("article")
    .filter({ hasText: "/" })
    .getByRole("slider")
    .fill("130");

  await page.getByRole("button", { name: "Go", exact: true }).first().click();

  await waitForTasks(page);
  await sleep(500);

  // Go back and make sure it actually worked
  await page.goto("http://localhost:8002/tagpoints");

  // Do this twice to give it time to render
  await sleep(300);
  await page.goto("http://localhost:8002/tagpoints");

  await expect(
    page.getByRole("row", { name: "/test_chandler_tag" })
  ).toContainText("130");

  await page.goto(
    "http://localhost:8002/chandler/editor/PlaywrightChandlerTestModule:board1"
  );

  await page.evaluate(async () => {
    globalThis.testMode = true;
  });

  await page.getByRole("button", { name: "tst1" }).click();
  await page.getByTestId("add-rm-fixtures-button").click();
  await page.getByText("Channels").click();

  await expect(
    page.getByRole("heading", { name: "/test_chandler_tag" })
  ).toHaveCount(1);

  await page.getByRole("button", { name: "󰆴 Remove" }).click();

  await waitForTasks(page);
  await sleep(500);

  await page.goto(
    "http://localhost:8002/chandler/editor/PlaywrightChandlerTestModule:board1"
  );
  await page.getByRole("button", { name: "tst1" }).click();
  await waitForTasks(page);
  await sleep(500);

  await expect(
    page.getByRole("heading", { name: "/test_chandler_tag" })
  ).toHaveCount(0);

  await page.getByTestId("close-group").click();

  //Test stopping and restarting a group

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page.getByRole("button", { name: "󰙧 Stop" }).click();

  await expect(page.getByTestId("sidebar-active-cue-name")).toBeHidden({
    timeout: 10_000,
  });

  await page.getByRole("button", { name: "󰐊 Go!" }).click();
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText("c2");

  // Test commander
  await page.getByTestId("commander-link").click();
  await expect(page.getByRole("button", { name: "tst1" })).toBeVisible(
    { timeout: 10_000 },
  );
  await expect(page.getByRole("article")).toContainText("c2");
  await page.getByRole("button", { name: "tst1" }).click();
  await page.getByRole("button", { name: "c3 󰤔" }).click();
  await page.getByRole("button", { name: "󰅖 Close" }).click();
  await expect(page.getByRole("article")).toContainText("c3");
  await expect(page.getByRole("link", { name: "(slideshow)" })).toBeVisible();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });

  // Stop Cue
  await page.getByRole("button", { name: "󰙧" }).click();
  await expect(page.getByTestId("active-cue-name")).toBeHidden();
  await page.getByRole("button", { name: "󰐊" }).click();
  await expect(page.getByTestId("active-cue-name")).toContainText("c2");

  await deleteModule(page, module);
  await logout(page);
});
