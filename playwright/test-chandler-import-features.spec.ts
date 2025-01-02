import { test, expect } from "@playwright/test";
import {
  login,
  chandlerBoardTemplate,
  sleep,
  waitForTasks
} from "./util";

test("test", async ({ page }) => {
  test.setTimeout(2_400_000);

  await login(page);
  const module = "PlaywrightChandlerTestModule3";

  await chandlerBoardTemplate(page, module);

  // Maake some stuff to ensure it's not overwritten by the upload
  await page.getByTestId("close-group").click();
  await page.getByRole("button", { name: "󰤀 Presets" }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("NotUploaded").catch(() => {});
  });
  await page
    .getByTestId("preset-inspector-Amber-heading")
    .getByRole("button", { name: "Copy" })
    .click();
  await page.getByRole("button", { name: "󰅖 Close" }).click();
  await page.getByLabel("Settings", { exact: true }).click();

  await page.getByRole("button", { name: "󰏫 Fixture Types" }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("NotUploaded").catch(() => {});
  });
  await page.getByRole("button", { name: "󰐕 New" }).click();
  await page.getByTestId("fixture-type-to-edit").selectOption("NotUploaded");
  await page.getByRole("button", { name: "Add Channel" }).click();
  await page.getByLabel("Type:").selectOption("green");
  await page.getByRole("button", { name: "Fixtures" }).click();
  await page
    .getByRole("row", { name: "Name", exact: true })
    .getByRole("textbox")
    .click();
  await page
    .getByRole("row", { name: "Name", exact: true })
    .getByRole("textbox")
    .fill("existingassignment");

  await page.getByRole("cell", { name: "7ch DGBR" }).click();
  await page
    .getByRole("cell", { name: "7ch DGBR" })
    .getByRole("combobox")
    .selectOption("NotUploaded");
  await page
    .getByRole("row", { name: "Universe", exact: true })
    .getByRole("combobox")
    .fill("dummy");
  await page.getByRole("spinbutton").fill("300");
  await page.getByRole("button", { name: "Add and Update" }).click();
  await page.getByRole("button", { name: "Universes" }).click();
  await page.getByPlaceholder("New Universe Name").click();
  await page.getByPlaceholder("New Universe Name").fill("dummy");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page
    .getByRole("combobox", { name: "The type of universe. Usually" })
    .dblclick();
  await page
    .getByRole("combobox", { name: "The type of universe. Usually" })
    .fill("null");
  await page.getByRole("button", { name: "Update Settings" }).click();

  // Import everything except the universes
  await page.getByRole("button", { name: "󰝰 Import/Export" }).click();
  await page.getByLabel("File", { exact: true }).click();
  await page
    .getByLabel("File", { exact: true })
    .setInputFiles("kaithem/data/testing/UploadableChandlerBoard.yaml");
  await page.getByLabel("Import Presets").check();
  await page.getByLabel("Import Fixture Assignments").check();
  await page.getByLabel("Import Fixture Types Library").check();
  await page.getByRole("button", { name: "Import", exact: true }).click();

  // Check that it worked
  await page.getByRole("button", { name: "󰏫 Fixture Types" }).click();
  await page
    .getByTestId("fixture-type-to-edit")
    .selectOption("UploadedFixtureType");
  await expect(page.getByLabel("Type:")).toHaveValue("white");
  await expect(page.getByTestId("fixture-type-to-edit")).toHaveValue(
    "UploadedFixtureType"
  );
  await page.getByTestId("fixture-type-to-edit").selectOption("NotUploaded");
  await expect(page.getByLabel("Type:")).toHaveValue("green");
  await page
    .getByTestId("fixture-type-to-edit")
    .selectOption("UnusedUploadedFixtureType");
  await expect(page.getByLabel("Type:")).toHaveValue("red");

  await page.getByRole("button", { name: "Fixtures" }).click();
  await expect(
    page.getByRole("cell", { name: "UploadedFixture", exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "123" }).getByRole("textbox")
  ).toHaveValue("123");
  await page.getByRole("button", { name: "Universes" }).click();

  await sleep(1000);
  await waitForTasks(page);

  // We did not import the universes so it shouldn't be there
  await expect(
    page.getByRole("cell", { name: "uploadeduniverse" })
  ).toBeHidden();

  // Dummy universe we just made should be there
  await expect(
    page
      .getByTestId("universe-configuration-table")
      .getByRole("cell", { name: "dummy" })
  ).toBeVisible();

  // now lets import the universes
  await page.getByRole("button", { name: "󰝰 Import/Export" }).click();
  await page.getByLabel("File", { exact: true }).click();
  await page
    .getByLabel("File", { exact: true })
    .setInputFiles("kaithem/data/testing/UploadableChandlerBoard.yaml");
  await page.getByLabel("Import Universes").check();
  await page.getByRole("button", { name: "Import", exact: true }).click();

  await page.getByRole("button", { name: "Universes" }).click();
  await expect(
    page.getByRole("cell", { name: "uploadeduniverse" })
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "The type of universe. Usually" }).nth(1)
  ).toHaveValue("null");

  // Back to main editor to check presets
  await page.getByRole("link", { name: "󰀻 Apps" }).click();

  await page.getByTestId("extras-button-playwrightchandlertestmodule3_board1").click();
  await page.getByRole("link", { name: "Editor" }).click();
  await page.getByRole("button", { name: "󰤀 Presets" }).click();
  await page.getByPlaceholder("Filter").fill("upl");
  await page.getByText("UploadablePreset").click();

  await page.getByRole("button", { name: "󰅖 Close" }).click();
  await page.getByText("PlaywrightChandlerTestModule3:").click();
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByLabel("Delete").click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("PlaywrightChandlerTestModule3");
  await page.getByRole("button", { name: "Submit" }).click();
});
