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

/*More flaky crap fixes*/
async function check_box(_page, box) {
  if (await box.isChecked()) {
    return;
  }
  await box.click();
}

async function uncheck_box(_page, box) {
  if (!(await box.isChecked())) {
    return;
  }
  await box.click();
}

test("test", async ({ page }) => {
  test.setTimeout(4_800_000);

  await login(page);

  makeModule(page, "testchandlerproperties");

  await page.getByTestId("add-resource-button").click();

  await page.getByTestId("add-chandler_board").click();
  await page.getByLabel("Resource Name").click();
  await page.getByLabel("Resource Name").fill("b1");

  await page.getByRole("button", { name: "Submit" }).click();
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "testchandlerproperties" }).click();
  await page.getByRole("link", { name: "󰏬 Edit" }).click();

  // Now on the editor
  await page.getByPlaceholder("New group name").dblclick();
  await page.getByPlaceholder("New group name").fill("ts1");
  await page.getByTestId("add-group-button").click();
  await page.getByRole("button", { name: "ts1" }).click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByTestId("group-properties-button").click();
  await page.getByLabel("Slideshow Overlay").click();
  await page.getByLabel("Slideshow Overlay").fill("overlay");
  await page.getByLabel("MIDI Source").click();
  await page.getByLabel("MIDI Source").fill("midisrc");
  await page.getByPlaceholder("Next cue in list").click();
  await page.getByPlaceholder("Next cue in list").fill("foo");
  await page.getByRole("main").click();

  await page.getByLabel("Priority").fill("42");
  await page.getByLabel("Default Alpha").click();
  await page.getByLabel("Default Alpha").fill("0.22");

  // This one line is flaky.
  const inputvalue = await page.getByLabel("Default Alpha").inputValue();
  if (!(inputvalue == "0.22")) {
    await delay(2500);
    await page.getByLabel("Default Alpha").click();
    await page.getByLabel("Default Alpha").fill("0.22");
  }
  await delay(200);
  expect(await page.getByLabel("Default Alpha").inputValue()).toBe("0.22");

  await page.getByRole("heading", { name: "Sound" }).click();

  // This doesn't seem to work the first time despite working in manual
  await page.getByLabel("Alpha", { exact: true }).fill("0.25");
  await page.getByRole("heading", { name: "Sound" }).click();
  await page.getByLabel("Alpha", { exact: true }).fill("0.25");
  await page.getByRole("heading", { name: "Sound" }).click();
  await page.getByLabel("Require Confirmation for Cue").click();
  await page.getByLabel("Sound Output").click();
  await page.getByLabel("Sound Output").fill("defaultout");
  await page.getByLabel("Crossfade Media").click();
  await page.getByLabel("Crossfade Media").fill("0.56");
  await page.getByLabel("MQTT Server").click();
  await page.getByLabel("MQTT Server").fill("ppp");
  await page.getByLabel("Sync Group Name").click();
  await page.getByLabel("Sync Group Name").fill("grp");


  // Click away
  await page.getByLabel("Sync Group Name").click();

  await waitForTasks(page);

  // Check that the stuff is there
  await page.goto(
    "http://localhost:8002/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/testchandlerproperties:b1"
  );
  await expect(page.getByRole("main")).toContainText("STATUS: MQTT");
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();

  await expect(page.getByLabel("Priority")).toHaveValue("42");

  await expect(page.getByLabel("Alpha", { exact: true })).toHaveValue("0.25");
  await expect(page.getByLabel("Default Alpha")).toHaveValue("0.22");
  await expect(page.getByLabel("Slideshow Overlay")).toHaveValue("overlay");
  await expect(page.getByLabel("MIDI Source")).toHaveValue("midisrc");

  await expect(page.getByPlaceholder("Next cue in list")).toHaveValue("foo");
  await expect(page.getByLabel("Sound Output")).toHaveValue("defaultout");
  await expect(page.getByLabel("Crossfade Media")).toHaveValue("0.56");
  await expect(page.getByLabel("MQTT Server")).toHaveValue("ppp");
  await expect(page.getByLabel("Sync Group Name")).toHaveValue("grp");

  await page.getByTestId("close-group-settings").click();
  await page.getByTestId("close-group").click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  // More settings
  await page.goto(
    "http://localhost:8002/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/testchandlerproperties:b1"
  );
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();
  await waitForTasks(page);
  await sleep(1000);


  await page.getByTestId("group_blend_mode").selectOption("HTP");
  await expect(page.getByLabel("Alpha", { exact: true })).toHaveValue("0.25");
  await page.getByLabel("Default Alpha").click();

  await page.getByLabel("Sidebar info URL").click();
  await page.getByLabel("Sidebar info URL").fill("foourl");

  await page.getByLabel("Enable Timing").setChecked(false);

  await check_box(page, page.getByLabel("Utility Group(No controls)"));
  //await page.getByLabel('Utility Group(No controls)').check();

  await check_box(page, page.getByLabel("Hide in Runtime Mode"));
  //await page.getByLabel('Hide in Runtime Mode').check();

  await page.getByTestId("close-group-settings").click();
  await page.getByTestId("close-group").click();
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  // More checking
  await page.goto(
    "http://localhost:8002/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/testchandlerproperties:b1"
  );
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();

  // We disabled timing so it should give the user a warning
  // otherwise they'll spend al day wondering why it doesn't work
  await expect(page.getByText("Timing Disabled")).toHaveClass("warning");


  await expect(page.getByLabel("Utility Group(No controls)")).toBeChecked();
  await expect(page.getByLabel("Hide in Runtime Mode")).toBeChecked();
  await expect(page.getByLabel("Sidebar info URL")).toHaveValue("foourl");

  await expect(page.getByLabel("Enable Timing")).not.toBeChecked();

  await expect(page.getByTestId("group_blend_mode")).toHaveValue("HTP");

  // Now lets do the display tags and action buttons
  await page.getByRole("button", { name: "Add Button" }).click();

  await page.getByTestId("event_button_label").click();
  await page.getByTestId("event_button_label").fill("btn1");
  await page.getByTestId("event_button_event").click();
  await page.getByTestId("event_button_event").fill("evt1");

  await page.getByRole("button", { name: "Add Tag" }).click();
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByTestId("display_tag_label").fill("tg1");

  // This one display tag width line is always flaky.
  await waitForTasks(page);
  await sleep(1000);

  // This line is flaky, if you get a fail just manually pause a bit.
  await page.getByTestId("display_tag_width").fill("5");
  await page.getByTestId("display_tag_width").click();
  await sleep(300);
  await page.getByTestId("display_tag_width").fill("5");
  await waitForTasks(page);
  await sleep(1000);
  await page.getByTestId("display_tag_tag").fill("=4");

  await sleep(300);
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.getByTestId("display_tag_type").selectOption("Meter");

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  // Waste some time to let it send
    
    //TODO why is this flaky??? it shou;dn't need retry!!
    await page.getByTestId("display_tag_type").selectOption("Meter");
    
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await sleep(600);

  await page.getByTestId("close-group-settings").click();

  // More time waste
  await page.getByTestId("close-group").click();

  await sleep(300);
  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.goto(
    "http://localhost:8002/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/testchandlerproperties:b1"
  );
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();

  await sleep(300);
  await expect(page.getByTestId("event_button_label")).toHaveValue("btn1");
  await expect(page.getByTestId("event_button_event")).toHaveValue("evt1");

  await expect(page.getByTestId("display_tag_label")).toHaveValue("tg1");
  await expect(page.getByTestId("display_tag_width")).toHaveValue("5");
  await expect(page.getByTestId("display_tag_tag")).toHaveValue("=4");
  await expect(page.getByTestId("display_tag_type")).toHaveValue("meter");

  await page.getByTestId("event_button_delete").click();
  await page.getByTestId("display_tag_delete").click();

  await check_box(page, page.getByLabel("Require Confirmation for Cue"));
  //await page.getByLabel('Require Confirmation for Cue').check();

  // Click elsewhere, do other stuff, let it save

  await page.getByTestId("close-group-settings").click();
  await page.getByTestId("close-group").click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.goto(
    "http://localhost:8002/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/testchandlerproperties:b1"
  );
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();

  await expect(page.getByLabel("Require Confirmation for Cue")).toBeChecked();

  // Now lets set stuff back to defaults

  await page.getByLabel("Sound Output").click();
  await page.getByLabel("Sound Output").fill("");
  await page.getByLabel("Crossfade Media").click();
  await page.getByLabel("Crossfade Media").click();
  await page.getByLabel("Crossfade Media").dblclick();
  await page.getByLabel("Crossfade Media").fill("");
  await page.getByLabel("Default Alpha").click();
  await page.getByLabel("Crossfade Media").click();
  await page.getByLabel("Crossfade Media").fill("0");
  await page.getByRole("heading", { name: "Sound" }).click();
  await page.getByLabel("MQTT Server").dblclick();
  await page.getByLabel("MQTT Server").fill("");
  await page.getByLabel("Sync Group Name").dblclick();
  await page.getByLabel("Sync Group Name").fill("");
  await page.getByLabel("Slideshow Overlay").click({
    clickCount: 3,
  });
  await page.getByLabel("Slideshow Overlay").fill("");
  await page.getByLabel("MIDI Source").dblclick();

  await page.getByLabel("MIDI Source").click({
    clickCount: 3,
  });
  await page.getByLabel("MIDI Source").fill("");


  await page.getByPlaceholder("Next cue in list").dblclick();
  await page.getByPlaceholder("Next cue in list").fill("");

  await uncheck_box(page, page.getByLabel("Utility Group(No controls)"));
  await uncheck_box(page, page.getByLabel("Hide in Runtime Mode"));
  await uncheck_box(page, page.getByLabel("Backtrack"));
  await uncheck_box(page, page.getByLabel("Active By Default"));
  await uncheck_box(page, page.getByLabel("Require Confirmation for Cue"));

  // await page.getByLabel('Utility Group(No controls)').uncheck();
  // await page.getByLabel('Hide in Runtime Mode').uncheck();
  // await page.getByLabel('Backtrack').uncheck();
  // await page.getByLabel('Active By Default').uncheck();
  // await page.getByLabel('Require Confirmation for Cue').uncheck();

  await page.getByTestId("close-group-settings").click();
  await page.getByTestId("close-group").click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });
  // Check that it worked
  await page.goto(
    "http://localhost:8002/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/testchandlerproperties:b1"
  );
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();

  await expect(page.getByLabel("MQTT Server")).toBeEmpty();
  await expect(page.getByLabel("Sync Group Name")).toBeEmpty();
  await expect(page.getByLabel("Slideshow Overlay")).toBeEmpty();
  await expect(page.getByLabel("MIDI Source")).toBeEmpty();

  await expect(page.getByPlaceholder("Next cue in list")).toBeEmpty();
  await expect(page.getByLabel("Crossfade Media")).toHaveValue("0");
  await expect(page.getByLabel("Sound Output")).toBeEmpty();
  await expect(page.getByLabel("Utility Group(No controls)")).not.toBeChecked();
  await expect(page.getByLabel("Hide in Runtime Mode")).not.toBeChecked();
  await expect(
    page.getByLabel("Require Confirmation for Cue")
  ).not.toBeChecked();
  await expect(page.getByLabel("Active By Default")).not.toBeChecked();
  await expect(page.getByLabel("Backtrack")).not.toBeChecked();

  await expect(page.getByPlaceholder("Next cue in list")).toBeEmpty();

  await page.getByText("Custom layout for slideshow").click();
  await page.getByTestId("slideshow_layout").click();
  await page.getByTestId("slideshow_layout").fill("LayoutPlaceholder");

  await page.getByTestId("close-group-settings").click();
  await page.getByTestId("close-group").click();

  await page.evaluate(async () => {
    await globalThis.doSerialized();
  });

  await page.goto(
    "http://localhost:8002/chandler/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/editor/testchandlerproperties:b1"
  );
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();
  await page.getByText("Custom layout for slideshow").click();
  await expect(page.getByTestId("slideshow_layout")).toHaveValue(
    "LayoutPlaceholder"
  );

  // Test flicker blend mode props and slideshow transform

  await page.getByLabel("Perspective Distance cm").fill("500");
  await page.getByLabel("Translate X %").fill("84");

  await page.getByTestId("group_blend_mode").selectOption("flicker");

  await waitForTasks(page);

  // Retry because number inputs can be flaky
  await page.getByLabel("agility:").fill("0.04");
  await waitForTasks(page);
  await page.getByLabel("agility:").fill("0.04");

  await page.getByLabel("gustiness:").fill("0.19");
  await waitForTasks(page);
  await page.getByLabel("gustiness:").fill("0.19");
  await waitForTasks(page);

  await page.getByTestId("close-group-settings").click();
    await page.getByTestId("close-group").click();
    
  await page.getByRole("link", { name: "󰀻 Apps" }).click();
  await page.getByTestId("extras-button-testchandlerproperties_b1").click();
  await page.getByRole("link", { name: "Editor" }).click();
  await page.getByRole("button", { name: "ts1" }).click();
  await page.getByTestId("group-properties-button").click();

  await expect(page.getByLabel("Perspective Distance")).toHaveValue("500");
  await expect(page.getByLabel("Translate X")).toHaveValue("84");
  await expect(page.getByTestId("group_blend_mode")).toHaveValue("flicker");
  await expect(page.getByLabel("agility:")).toHaveValue("0.04");
  await expect(page.getByLabel("gustiness:")).toHaveValue("0.19");

  await page.getByTestId("close-group-settings").click();
  await page.getByTestId("close-group").click();

  await deleteModule(page, "testchandlerproperties");
  await logout(page);
});
