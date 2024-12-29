import { test, expect } from "@playwright/test";
import {
  sleep,
  login,
  logout,
  chandlerBoardTemplate,
  deleteModule,
} from "./util";

/*/
Create a module, make a chandler board, test very simple logic,
make sure tag output features work.
*/
test("test", async ({ page }) => {
  test.setTimeout(2_400_000);

  await login(page);
  const module = "PlaywrightChandlerTestModule2";

  await chandlerBoardTemplate(page, module);

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page
    .getByRole("row", { name: "c2" })
    .getByTitle("Cue Length")
    .fill("5");

  await page.getByPlaceholder("New cue name").click();
  await page.getByPlaceholder("New cue name").fill("c3");
  await page.getByRole("button", { name: "󰐕 Add Cue" }).click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  // Reassign the number to be the last cue.  It will be six because we inserted it
  // just after five
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("15").catch(() => {});
  });
  await page.getByText("6", { exact: true }).dblclick();

  await sleep(150);

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  // Give it a 5 second fade.  Numeric inputs are flaky
  await page.getByRole("row", { name: "c3" }).getByRole("spinbutton").fill("5");
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  await page.getByRole("row", { name: "c3" }).getByRole("spinbutton").fill("5");
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  // go to c3
  await page.getByRole("cell", { name: "c3" }).click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByTestId("add-rm-fixtures-button").click();
  await page.getByLabel("Tag", { exact: true }).click();
  await page.getByLabel("Tag", { exact: true }).fill("/testfadetag");
  await page.getByTestId("add-tag-to-cue-button").click();
  await page.getByTestId("details-fixture-channels-summary").click();
  await page.locator("#selectedGroupWindow").getByRole("slider").fill("255");

  await page.getByRole("button", { name: "󰢻 Normal View" }).click();
  await page.getByTestId("close-group").click();
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText(
    "default"
  );
  await page.getByRole("button", { name: "Next 󰒭" }).click();
  await sleep(5000);
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText("c2");
  await sleep(4000);
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText("c3");

  // Ensure the tag point is actually fading in slowly
  await page.getByRole("link", { name: "󰓻 Tags" }).click();

  const value1 = await page
    .getByRole("row", { name: "/testfadetag" })
    .getByRole("cell")
    .nth(1)
    .textContent();
  expect(Number.parseFloat(value1)).toBeGreaterThan(0);
  expect(Number.parseFloat(value1)).toBeLessThan(255);

  await page.getByRole("link", { name: "󰓻 Tags" }).click();

  const value2 = await page
    .getByRole("row", { name: "/testfadetag" })
    .getByRole("cell")
    .nth(1)
    .textContent();
  expect(Number.parseFloat(value2)).toBeGreaterThan(0);
  expect(Number.parseFloat(value2)).toBeLessThan(255);
  expect(Number.parseFloat(value2)).toBeGreaterThan(Number.parseFloat(value1));

  await sleep(5000);

  await page.getByRole("link", { name: "󰓻 Tags" }).click();

  const value3 = await page
    .getByRole("row", { name: "/testfadetag" })
    .getByRole("cell")
    .nth(1)
    .textContent();
  expect(Number.parseFloat(value3)).toBe(255);

  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await page
    .getByTestId("extras-button-playwrightchandlertestmodule2_board1")
    .click();
  await page.getByRole("link", { name: "Editor" }).click();

  await page.getByRole("button", { name: "tst1" }).click();
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  // Set c3 to end in 0.25s
  await page
    .getByRole("row", { name: "c3" })
    .getByRole("combobox", { name: "Cue Length" })
    .fill("0.25");

  // Go on c3 again
  await page
    .getByRole("row", { name: "c3" })
    .getByRole("button", { name: "Go", exact: true })
    .click();
  await page.getByTestId("close-group").click();
  await sleep(1000);
  // We should still be in c because it's the last cue and there's nowhere to go
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText("c3");

  // Now we make c3 point to default as the next cue
  await page.getByRole("button", { name: "tst1" }).click();
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page
    .getByRole("row", { name: "c3" })
    .locator("select")
    .selectOption("default");
  await page.getByTestId("close-group").click();

  // It immediately goes to default
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText(
    "default"
  );

  // Now make a new cue which must be after c3 to be the last cue
  await page.getByRole("button", { name: "tst1" }).click();
  await page.getByRole("cell", { name: "c3 " }).click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByPlaceholder("New cue name").fill("c4");
  await page.getByRole("button", { name: "󰐕 Add Cue" }).click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  //Set c2 back to zero length
  await page
    .getByRole("row", { name: "c2" })
    .getByTitle("Cue Length")
    .fill("0");

  // Set a global default, EVERY cue's "Next" points to c2 now if not explicitly set
  // Per cue
  await page.getByTestId("group-properties-button").click();
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  await page.getByPlaceholder("Next cue in list").click();
  await page.getByPlaceholder("Next cue in list").fill("c2");
  await page.getByTestId("close-group-settings").click();

  await sleep(50);
  // Go on c4
  page
    .getByRole("row", { name: "c4" })
    .getByRole("button", { name: "Go", exact: true })
    .click();
  await sleep(50);

  await page.getByTestId("close-group").click();

  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText("c4");

  // Next from c4 is c2 because of the global default
  await page.getByRole("button", { name: "Next 󰒭" }).click();
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText("c2");
  await page.getByRole("button", { name: "󰒮 Prev" }).click();
  await expect(page.getByTestId("sidebar-active-cue-name")).toContainText("c4");

  await deleteModule(page, module);
  await logout(page);
});
