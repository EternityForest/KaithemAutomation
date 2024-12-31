import { test, expect } from "@playwright/test";
import { sleep, login, makeModule, deleteModule } from "./util";

test("test", async ({ page }) => {
  test.setTimeout(600_000);

  await login(page);

  await makeModule(page, "mxer");
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-mixing_board").click();
  await page.getByLabel("Resource Name").click();
  await page.getByLabel("Resource Name").fill("mxr");
  await page.getByRole("button", { name: "Submit" }).click();
  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await page.getByRole("link", { name: "mxr" }).click();
  await page.getByTestId("new-channel-name").fill("testchannel");

  await page.getByTestId("add-stereo-channel").click();
  await sleep(3000);

  await expect(
    page.getByTestId("channel-box-testchannel").getByTestId("channel-status")
  ).toContainText("running", { timeout: 15_000 });

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("channel-fader")
    .fill("-14.5");

  // Make new channel, turn it up
  await page.getByTestId("new-channel-name").fill("testchannel2");
  await page.getByTestId("add-stereo-channel").click();
  // Give it extra loading time
  await sleep(3000);

  await expect(
    page.getByTestId("channel-box-testchannel2").getByTestId("channel-status")
  ).toContainText("running", { timeout: 15_000 });

  await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-fader")
    .fill("-8.5");
  await page.getByTestId("channel-box-testchannel2").getByText("Setup").click();

  // Set second channel inut to first channel output
  await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-input")
    .fill("testchannel_in");

  // Ding channel 1, expect there to be sound in the meter for channel 2
  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("ding-button")
    .click();
  await expect(
    page.getByTestId("channel-box-testchannel2").locator("footer")
  ).not.toContainText("-99db");

  // Now expect it to eventually go back to -99db
  await expect(
    page.getByTestId("channel-box-testchannel2").locator("footer")
  ).toContainText("-99db");

  // Set second channel input to nothing
  await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-input")
    .fill("");

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("ding-button")
    .click();

  // expect there to be no sound because we disconnected the input
  await sleep(300);
  let level = await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-level-value")
    .textContent();
  await expect(level).toBe("-99db");

  // Now try it in reverse, set the output of channel 1 to channel 2
  await page.getByTestId("channel-box-testchannel").getByText("Setup").click();

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("channel-output")
    .click();

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("channel-output")
    .fill("testchannel2_in");

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("ding-button")
    .click();

  await expect(
    page.getByTestId("channel-box-testchannel2").locator("footer")
  ).not.toContainText("-99db");

  // Now add a reverb to channel 1
  await page.getByTestId("show-effects-menu").click();
  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("add-effect-plateReverb")
    .click();

  // Give it extra loading time
  await sleep(3000);

  await expect(
    page.getByTestId("channel-box-testchannel").getByTestId("channel-status")
  ).toContainText("running", { timeout: 15_000 });

  // Expand that effect
  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("effect-box-plateReverb")
    .getByText("Plate Reverb")
    .click();

  // Set it to full blend
  await page.getByTestId("param-row-blend").getByRole("slider").fill("1");

  await expect(
    page.getByTestId("param-row-blend").getByTestId("param-value")
  ).toHaveText("1");

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("ding-button")
    .click();

  // With reverb, expect there to still be sound

  await sleep(2800);
  level = await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-level-value")
    .textContent();
  await expect(level).not.toBe("-99db");

  await expect(
    page
      .getByTestId("channel-box-testchannel")
      .getByTestId("effect-box-plateReverb")
      .getByText("Plate Reverb")
  ).toBeVisible();

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("delete-effect-button")
    .click();

  // Give it extra loading time
  await sleep(3000);

  await expect(
    page.getByTestId("channel-box-testchannel").getByTestId("channel-status")
  ).toContainText("running", { timeout: 15_000 });

  await expect(
    page
      .getByTestId("channel-box-testchannel")
      .getByTestId("effect-box-plateReverb")
      .getByText("Plate Reverb")
  ).toBeHidden();

  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("ding-button")
    .click();

  // With no reverb, expect sound to stop sooner
  await sleep(2800);

  level = await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-level-value")
    .textContent();
  await expect(level).toBe("-99db");

  // Delete channel 2
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("delete-button")
    .click();

  await expect(page.getByTestId("channel-box-testchannel2")).toBeHidden();

  // Remake it
  await page.getByTestId("new-channel-name").dblclick();
  await page.getByTestId("new-channel-name").fill("testchannel2");
  await page.getByTestId("add-stereo-channel").click();

  // Give it extra loading time
  await sleep(3000);

  await expect(
    page.getByTestId("channel-box-testchannel2").getByTestId("channel-status")
  ).toContainText("running", { timeout: 15_000 });

  // Ensure it reconnects to channel 1
  await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-fader")
    .fill("-5");
  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("ding-button")
    .click();

  await expect(
    page
      .getByTestId("channel-box-testchannel2")
      .getByTestId("channel-level-value")
  ).not.toContainText("-99db");

  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });

  // Save a preset
  await page.getByRole("button", { name: "Save" }).click();

  await page.getByPlaceholder("Preset name").click();
  await page.getByPlaceholder("Preset name").fill("default2");

  // save another!
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page.getByRole("button", { name: "Save" }).click();

  await page.getByRole("button", { name: "Presets/Defaults" }).click();
  await expect(
    page.getByRole("cell", { name: "default", exact: true })
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "default2" })).toBeVisible();

  // Deletion
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page
    .getByRole("row", { name: "default2" })
    .getByRole("button", { name: "Delete" })
    .click();
  
  await expect(page.getByRole("cell", { name: "default2" })).toBeHidden();

  await page.getByRole("button", { name: "Mixer (mxr)" }).click();

  // Delete channel
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page
    .getByTestId("channel-box-testchannel")
    .getByTestId("delete-button")
    .click();

  await page.getByTestId("channel-box-testchannel2").getByText("Setup").click();
  // Add noise gen
  await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("add-effect-audiotestsrc")
    .click();
  await expect(
    page.getByTestId("channel-box-testchannel2").getByTestId("channel-status")
  ).toContainText("running", { timeout: 15_000 });

  await page.getByTestId("new-channel-name").fill("testchannel3");
  await page.getByTestId("add-stereo-channel").click();
  // Give it extra loading time
  await sleep(3000);
  // There is a bug where if there's no output,
  // the noise gen doesn't show up in the level display

  // wait till running or else what we set may be overwritten by server update
  // ui race condition?
  await expect(
    page.getByTestId("channel-box-testchannel2").getByTestId("channel-status")
  ).toContainText("running", { timeout: 15_000 });

  await page.getByTestId("channel-box-testchannel2").getByText("Setup").click();

  await page
    .getByTestId("channel-box-testchannel2")
    .getByTestId("channel-output")
    .fill("testchannel3_in");

  // Click away so it saves
  await page.getByRole('heading', { name: 'testchannel2(2)' }).click();

  // The noise gen should show up
  await expect(
    page
      .getByTestId("channel-box-testchannel2")
      .getByTestId("channel-level-value")
  ).not.toContainText("-99db");

  await expect(
    page
      .getByTestId("channel-box-testchannel2")
      .getByTestId("effect-box-audiotestsrc")
      .getByText("Noise generator")
  ).toBeVisible();

  // Load preset
  await page.getByRole("button", { name: "Presets/Defaults" }).click();
  page.once("dialog", (dialog) => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept().catch(() => {});
  });
  await page.getByRole("button", { name: "Load" }).first().click();
  await page.getByRole("button", { name: "Mixer (mxr)" }).click();

  // Test channel 1 is back
  await expect(
    page.getByTestId("channel-box-testchannel").locator("header")
  ).toContainText("running", { timeout: 15_000 });
  // Noise gen is gone
  await expect(
    page
      .getByTestId("channel-box-testchannel2")
      .getByTestId("channel-level-value")
  ).toContainText("-99db");

  await page.getByTestId('channel-box-testchannel').getByTestId('ding-button').click();
  await expect(page.getByTestId('channel-box-testchannel2').getByTestId('channel-level-value')).toContainText('-99db');
  await page.getByRole('button', { name: 'Status' }).click();
  await expect(page.getByRole('cell', { name: 'testchannel_in:input_FL' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'testchannel2_in:input_FL' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'testchannel_out:output_FL' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'testchannel2_out:output_FL' })).toBeVisible();

  // Deleted stuff
  await expect(page.getByRole('cell', { name: 'testchannel3_out:output_FL' })).toBeHidden();

  await page.getByRole('link', { name: '󱒕 Modules' }).click();
  await page.getByRole('link', { name: 'mxer' }).click();
  await page.getByTestId('delete-resource-button').click();
  await page.getByRole('button', { name: 'Submit' }).click();

  // TODO: there's a bad file descriptor  in the hashing of the module here
  // but it still works

  await page.goto('http://localhost:8002/');
  await page.getByRole('link', { name: '󱒕 Modules' }).click();
  await page.getByRole('link', { name: 'mxer' }).click();
  await page.getByTestId('add-resource-button').click();
  await page.getByTestId('add-mixing_board').click();
  await page.getByLabel('Resource Name').click();
  await page.getByLabel('Resource Name').fill('mixer2');
  await page.getByRole('button', { name: 'Submit' }).click();

  await page.getByRole('link', { name: '󰀻 Apps' }).click();

  // Old mixer should have disappeared from the apps page
  await expect(page.getByRole('link', { name: 'mxr' })).toBeHidden();

  await page.getByRole('link', { name: 'mixer2' }).click();

  await page.getByRole('button', { name: 'Presets/Defaults' }).click();
  await expect(page.getByRole('heading', { name: 'Presets' })).toBeVisible();

  // Should be no leftovers from the old mixer
  await expect(page.getByRole('cell', { name: 'testchannel_out:output_FL' })).toBeHidden();
  await expect(page.getByRole('cell', { name: 'testchannel2_out:output_FL' })).toBeHidden();
  await expect(page.getByRole('cell', { name: 'testchannel3_out:output_FL' })).toBeHidden();
  await expect(page.getByRole('cell', { name: 'testchannel_in:input_FL' })).toBeHidden();
  await expect(page.getByRole('cell', { name: 'testchannel2_in:input_FL' })).toBeHidden();
  await expect(page.getByRole('cell', { name: 'testchannel2_in:input_FL' })).toBeHidden();

  await deleteModule(page, 'mxer');
});