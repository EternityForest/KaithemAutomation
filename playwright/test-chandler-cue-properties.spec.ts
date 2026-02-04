import { test, expect } from "@playwright/test";
import {
  login,
  logout,
  makeModule,
  deleteModule,
  sleep,
  waitForTasks,
} from "./util";

async function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test("test", async ({ page }) => {
  test.setTimeout(2_400_000);
  await page.setDefaultTimeout(20_000);

  await login(page);

  await makeModule(page, "testcue");

  await page.getByTestId("add-resource-button").click();

  await page.getByTestId("add-chandler_board").click();
  await page.getByLabel("Resource Name").click();
  await page.getByLabel("Resource Name").fill("testcue");
  await page.getByRole("button", { name: "Submit" }).click();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "testcue" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("tst").catch(() => {});
  });
  await page.getByTestId("add-group-button").click();

  await sleep(200);

  await page.getByRole("button", { name: "tst" }).click();
  await page.getByTestId("cue-media-dialog-button").click();

  await waitForTasks(page);

  await page.getByLabel("Sound start s into file.").click();
  await sleep(500);
  await page.getByLabel("Sound start s into file.").fill("1");
  await sleep(500);
  await page.getByLabel("Sound start s into file.").fill("1");
  await page.getByLabel("Sound start s into file.").fill("1");
  await page.getByLabel("Sound start s into file.").fill("1");
  await sleep(500);
  await page.getByLabel("Sound start s into file.").fill("1");

  await page.getByLabel("Media Speed").click();
  await page.getByLabel("Media Speed").fill("1.2");
  await page.getByLabel("Windup").click();
  await page.getByLabel("Windup").fill("0.1");
  await page.getByLabel("Winddown").click();
  await page.getByLabel("Winddown").fill("0.3");
  await page.getByLabel("Device Play media file in web").click();
  await page.getByLabel("Device Play media file in web").fill("groupwebplayer");
  await page.getByLabel("Relative length").click({
    button: "right",
  });
  await expect(page.getByLabel("Relative length")).not.toBeChecked();
  await page.getByLabel("Relative length").check();

  await page.getByLabel("Fade sound after end").click();
  await page.getByLabel("Fade sound after end").fill("0.6");
  await page.getByLabel("Sound fadein:").click();
  await page.getByLabel("Sound fadein:").fill("0.7");
  await page.getByLabel("Cue Volume").click();
  await page.getByLabel("Cue Volume").fill("0.8");
  await page.getByLabel("Loops").click();
  await page.getByLabel("Loops").fill("8");
  // Click away
  await page.getByLabel("Cue Volume").click();

  await waitForTasks(page);
  await sleep(200);

  await page
    .getByTestId("media-browser-container")
    .getByText("<TOP DIRECTORY>")
    .click();
  await page
    .getByTestId("media-browser-container")
    .getByText("Builtin")
    .click();
  await page.getByTestId("media-browser-container").getByText("img/").click();
  await page.getByTestId("media-browser-container").getByText("16x9/").click();

  await page
    .locator("tr")
    .filter({ hasText: "apples-display.avif" })
    .getByRole("button", { name: "Set Label" })
    .click();

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
    .getByText("sounds/")
    .click();

  await page
    .locator("tr")
    .filter({ hasText: "tang.opus" })
    .getByRole("button", { name: "Set(Sound)" })
    .click();

  await page
    .locator("tr")
    .filter({ hasText: "320181__dland__hint.opus" })
    .getByRole("button", { name: "Set(Slide)" })
    .click();

  await waitForTasks(page);

  await page.getByTestId("close-cue-media").click();
  await page.getByTestId("close-group").click();

  await waitForTasks(page);
  await sleep(250);
  // Verify
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "testcue" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();
  await page.getByRole("button", { name: "tst" }).click();
  await page.getByTestId("cue-media-dialog-button").click();
  await waitForTasks(page);
  await expect(page.getByTestId("cue-label-image-control")).toHaveValue(
    "img/16x9/apples-display.avif"
  );

  await expect(page.getByTestId("cue-sound-control")).toHaveValue(
    "sounds/tang.opus"
  );

  await expect(page.getByTestId("cue-slide-control")).toHaveValue(
    "sounds/320181__dland__hint.opus"
  );

  await expect(page.getByLabel("Sound start s into file.")).toHaveValue("1");
  await expect(page.getByLabel("Media Speed")).toHaveValue("1.2");
  await expect(page.getByLabel("Windup")).toHaveValue("0.1");
  await expect(page.getByLabel("Winddown")).toHaveValue("0.3");
  await expect(page.getByLabel("Device Play media file in web")).toHaveValue(
    "groupwebplayer"
  );
  await expect(page.getByLabel("Relative length")).toBeChecked();
  await expect(page.getByLabel("Fade sound after end")).toHaveValue("0.6");
  await expect(page.getByLabel("Sound fadein:")).toHaveValue("0.7");
  await expect(page.getByLabel("Cue Volume")).toHaveValue("0.8");
  await expect(page.getByLabel("Loops")).toHaveValue("8");
  await page.getByTestId("close-cue-media").click();
  await page.getByTestId("close-group").click();

  await delay(100);
  await deleteModule(page, "testcue");
  await logout(page);
});
