import { test, expect, Page } from "@playwright/test";
import { login, logout, makeModule, deleteModule, makeTagPoint } from "./util";

/* Test suite for Projection Mapper Editor
 * Tests data-testid attributes, source properties, and real-time sync
 */

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForTasks(page: Page) {
  await sleep(10);
   
}

/**
 * Create a projection mapper resource
 */
async function createProjectionMapper(
  page: Page,
  _module: string,
  name: string
) {
  await page.goto("http://localhost:8002/modules/module/TestProjectionMapper");
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-projection_mapper").click();
  await page.getByRole("textbox", { name: "Resource Name" }).click();
  await page.getByRole("textbox", { name: "Resource Name" }).fill(name);
  await page.getByRole("button", { name: "Submit" }).click();
}

/**
 * Open the projection mapper editor
 */
async function openProjectionMapperEditor(
  page: Page,
  module: string,
  mapperName: string
) {
  await page.goto("http://localhost:8002/modules/module/" + module);
  await page
    .getByTestId("pjm-blurb-" + mapperName)
    .getByTestId("edit-pj-map")
    .click();
  // Wait for editor to load
  await sleep(500);
  await waitForTasks(page);
}

/**
 * Create a new source of the given type
 */
async function createSource(
  page: Page,
  sourceType: string,
  sourceName: string
) {
  await page.getByTestId("add-source-btn").click();
  await sleep(100);


  const typeSelect = page.getByTestId('source-type-select');
  await typeSelect.selectOption(sourceType);

  // Dialog should appear
  page.once("dialog", (dialog) => {
    dialog.accept(sourceName).catch(() => {});
  });

  await page.getByRole("button", { name: "Next" }).click();


  await sleep(100);
}

/**
 * Test common source properties: opacity, blend mode, rotation, corners
 */
async function testCommonSourceProperties(page: Page, sourceName: string) {
  // Select the source
  await page.getByTestId(`source-item-${sourceName}`).click();
  await waitForTasks(page);

  // Test opacity
  const opacityInput = page.getByTestId("opacity");
  await opacityInput.fill("0.5");
  await waitForTasks(page);
  await expect(opacityInput).toHaveValue("0.5");

  // Test blend mode
  const blendMode = page.getByTestId("blend-mode");
  await blendMode.selectOption("multiply");
  await waitForTasks(page);
  await expect(blendMode).toHaveValue("multiply");

  // Test rotation
  const rotation = page.getByTestId("rotation");
  await rotation.fill("45");
  await rotation.fill("45"); // Flaky, fill twice
  await waitForTasks(page);
  await expect(rotation).toHaveValue("45");

  // Test corner positions
  const cornerXTl = page.getByTestId("corner-x-tl");
  const cornerYTl = page.getByTestId("corner-y-tl");

  await cornerXTl.fill("100");
  await cornerXTl.fill("100");
  await waitForTasks(page);

  await cornerYTl.fill("150");
  await cornerYTl.fill("150");
  await waitForTasks(page);

  await expect(cornerXTl).toHaveValue("100");
  await expect(cornerYTl).toHaveValue("150");

  // Save
  await page.getByTestId("save-btn").click();
  await sleep(750);
  await waitForTasks(page);

  // Refresh and verify persistence
  await page.reload();
  await sleep(500);
  await waitForTasks(page);

  // Verify after refresh
  await page.getByTestId(`source-item-${sourceName}`).click();
  await waitForTasks(page);

  await expect(page.getByTestId("opacity")).toHaveValue("0.5");
  await expect(page.getByTestId("blend-mode")).toHaveValue("multiply");
  await expect(page.getByTestId("rotation")).toHaveValue("45");
  await expect(page.getByTestId("corner-x-tl")).toHaveValue("100");
  await expect(page.getByTestId("corner-y-tl")).toHaveValue("150");
}

/**
 * Fill iframe source configuration
 */
async function fillIframeConfig(page: Page, url: string) {
  const urlInput = page.getByTestId("iframe-url");
  await urlInput.fill(url);
  await urlInput.fill(url);
  await waitForTasks(page);

  const windowWidth = page.getByTestId("iframe-window-width");
  await windowWidth.fill("1280");
  await windowWidth.fill("1280");
  await waitForTasks(page);

  const windowHeight = page.getByTestId("iframe-window-height");
  await windowHeight.fill("720");
  await windowHeight.fill("720");
  await waitForTasks(page);

  const renderWidth = page.getByTestId("iframe-render-width");
  await renderWidth.fill("1920");
  await renderWidth.fill("1920");
  await waitForTasks(page);

  const renderHeight = page.getByTestId("iframe-render-height");
  await renderHeight.fill("1080");
  await renderHeight.fill("1080");
  await waitForTasks(page);

  const cropX = page.getByTestId("iframe-crop-x");
  await cropX.fill("320");
  await cropX.fill("320");
  await waitForTasks(page);

  const cropY = page.getByTestId("iframe-crop-y");
  await cropY.fill("180");
  await cropY.fill("180");
  await waitForTasks(page);
}

/**
 * Fill clock source configuration
 */
async function fillClockConfig(page: Page) {
  const clockFormat = page.getByTestId("clock-format");
  await clockFormat.fill("%H:%M");
  await waitForTasks(page);

  // Text widget controls
  const textSize = page.getByTestId("text-size");
  await textSize.fill("120");
  await textSize.fill("120");
  await waitForTasks(page);

  const textColor = page.getByTestId("text-color");
  await textColor.fill("#ff0000");
  await waitForTasks(page);

  // Window dimensions are now auto-computed from corner positions
  // No manual input needed for text-window-width and text-window-height
}

/**
 * Fill tag source configuration
 */
async function fillTagConfig(page: Page, tagName: string) {
  const tagInput = page.getByTestId("tag-name");
  await tagInput.fill(tagName);
  await waitForTasks(page);

  const formatString = page.getByTestId("tag-format-string");
  await formatString.fill("%.2f");
  await waitForTasks(page);

  // Text widget controls
  const textSize = page.getByTestId("text-size");
  await textSize.fill("100");
  await textSize.fill("100");
  await waitForTasks(page);

  const textColor = page.getByTestId("text-color");
  await textColor.fill("#00ff00");
  await waitForTasks(page);
}

test.describe("Projection Mapper Editor", () => {
  test.beforeAll(async ({ browser }) => {
    // Create test context and setup
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page);
    await makeModule(page, "TestProjectionMapper");
    await logout(page);
    await context.close();
  });

  test.afterAll(async ({ browser }) => {
    // Cleanup
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page);
    await deleteModule(page, "TestProjectionMapper");
    await logout(page);
    await context.close();
  });

  test("Create mapper and verify editor loads", async ({ page }) => {
    test.setTimeout(30_000);

    await login(page);
    await createProjectionMapper(page, "TestProjectionMapper", "testmapper1");
    await openProjectionMapperEditor(
      page,
      "TestProjectionMapper",
      "testmapper1"
    );

    // Verify save button exists
    await expect(page.getByTestId("save-btn")).toBeVisible();
    await expect(page.getByTestId("add-source-btn")).toBeVisible();

    await logout(page);
  });

  test("Test common source properties with save/refresh", async ({ page }) => {
    test.setTimeout(60_000);

    await login(page);
    await createProjectionMapper(page, "TestProjectionMapper", "testmapper1");
    await openProjectionMapperEditor(
      page,
      "TestProjectionMapper",
      "testmapper1"
    );

    // Create iframe source
    await createSource(page, "iframe", "TestSource");
    await sleep(300);

    // Fill basic config
    await fillIframeConfig(
      page,
      "http://localhost:8002/static/img/16x9/kaithem-tavern.avif"
    );

    // Test common properties
    await testCommonSourceProperties(page, "TestSource");

    await logout(page);
  });

  test("Test iframe source specific properties", async ({ page }) => {
    test.setTimeout(60_000);

    await login(page);
    await createProjectionMapper(page, "TestProjectionMapper", "testmapper1");
    await openProjectionMapperEditor(
      page,
      "TestProjectionMapper",
      "testmapper1"
    );

    // Create iframe source
    await createSource(page, "iframe", "IframeTestSource");
    await sleep(300);

    // Fill iframe config
    await fillIframeConfig(
      page,
      "http://localhost:8002/static/img/16x9/kaithem-tavern.avif/iframe"
    );

    // Select source to show inputs
    await page.getByTestId("source-item-IframeTestSource").click();
    await waitForTasks(page);

    // Verify values are set
    await expect(page.getByTestId("iframe-url")).toHaveValue(
      "http://localhost:8002/static/img/16x9/kaithem-tavern.avif/iframe"
    );
    await expect(page.getByTestId("iframe-window-width")).toHaveValue("1280");
    await expect(page.getByTestId("iframe-window-height")).toHaveValue("720");
    await expect(page.getByTestId("iframe-render-width")).toHaveValue("1920");
    await expect(page.getByTestId("iframe-render-height")).toHaveValue("1080");
    await expect(page.getByTestId("iframe-crop-x")).toHaveValue("320");
    await expect(page.getByTestId("iframe-crop-y")).toHaveValue("180");

    // Save and refresh
    await page.getByTestId("save-btn").click();
    await sleep(500);
    await waitForTasks(page);

    await page.reload();
    await sleep(500);
    await waitForTasks(page);

    // Verify after refresh
    await page.getByTestId("source-item-IframeTestSource").click();
    await waitForTasks(page);

    await expect(page.getByTestId("iframe-url")).toHaveValue(
      "http://localhost:8002/static/img/16x9/kaithem-tavern.avif/iframe"
    );
    await expect(page.getByTestId("iframe-window-width")).toHaveValue("1280");

    await logout(page);
  });

  test("Test clock source properties", async ({ page }) => {
    test.setTimeout(60_000);

    await login(page);
    await createProjectionMapper(page, "TestProjectionMapper", "testmapper1");
    await openProjectionMapperEditor(
      page,
      "TestProjectionMapper",
      "testmapper1"
    );

    // Create clock source
    await createSource(page, "clock", "ClockTestSource");
    await sleep(300);

    // Fill clock config
    await fillClockConfig(page);

    // Select and verify
    await page.getByTestId("source-item-ClockTestSource").click();
    await waitForTasks(page);

    await expect(page.getByTestId("clock-format")).toHaveValue("%H:%M");
    await expect(page.getByTestId("text-size")).toHaveValue("120");

    // Save and refresh
    await page.getByTestId("save-btn").click();
    await sleep(500);
    await waitForTasks(page);

    await page.reload();
    await sleep(500);
    await waitForTasks(page);

    // Verify after refresh
    await page.getByTestId("source-item-ClockTestSource").click();
    await waitForTasks(page);

    await expect(page.getByTestId("clock-format")).toHaveValue("%H:%M");
    await expect(page.getByTestId("text-size")).toHaveValue("120");

    await logout(page);
  });

  test("Test tag source with tag point", async ({ page }) => {
    test.setTimeout(120_000);

    await login(page);

    // Create tag point
    await makeTagPoint(page, "TestProjectionMapper", "test_value");
    await sleep(300);

    await createProjectionMapper(page, "TestProjectionMapper", "testmapper1");
    await openProjectionMapperEditor(
      page,
      "TestProjectionMapper",
      "testmapper1"
    );

    // Create tag source
    await createSource(page, "tag", "TagTestSource");
    await sleep(300);

    // Fill tag config
    await fillTagConfig(page, "/test_value");

    // Select and verify
    await page.getByTestId("source-item-TagTestSource").click();
    await waitForTasks(page);

    await expect(page.getByTestId("tag-name")).toHaveValue("/test_value");
    await expect(page.getByTestId("tag-format-string")).toHaveValue("%.2f");

    // Save and refresh
    await page.getByTestId("save-btn").click();
    await sleep(500);
    await waitForTasks(page);

    await page.reload();
    await sleep(500);
    await waitForTasks(page);

    // Verify after refresh
    await page.getByTestId("source-item-TagTestSource").click();
    await waitForTasks(page);

    await expect(page.getByTestId("tag-name")).toHaveValue("/test_value");
    await expect(page.getByTestId("tag-format-string")).toHaveValue("%.2f");

    await logout(page);
  });

  test("Test real-time sync between two windows on corner position changes", async ({
    browser,
  }) => {
    test.setTimeout(120_000);


    // Create two contexts
    const context1 = await browser.newContext();
    const page1 = await context1.newPage();
    await login(page1);
    await createProjectionMapper(page1, "TestProjectionMapper", "testmapper_sync");


    const context2 = await browser.newContext();
    const page2 = await context2.newPage();

    // await login(page2);

    


    // Open editor in both pages
    const mapperUrl =
      "http://localhost:8002/static/vite/kaithem/src/plugins/CorePluginProjectionMapper/html/editor.html?module=TestProjectionMapper&resource=testmapper_sync&edit=true";

    await page1.goto(mapperUrl);
    await sleep(500);

    await page2.goto(mapperUrl);
    await sleep(500);

    // Create a source in page1
    await createSource(page1, "iframe", "SyncTestSource");
    await sleep(300);
    await fillIframeConfig(
      page1,
      "http://localhost:8002/static/img/16x9/kaithem-tavern.avif"
    );

    await page1.getByTestId("save-btn").click();
    await sleep(500);
    await waitForTasks(page1);
    

    // Select source in both pages
    await page1.getByTestId("source-item-SyncTestSource").click();
    await waitForTasks(page1);

    await page2.getByTestId("source-item-SyncTestSource").click();
    await waitForTasks(page2);

    // Change corner in page1
    const cornerXTl1 = page1.getByTestId("corner-x-tl");
    await cornerXTl1.fill("250");
    await cornerXTl1.fill("250");
    await waitForTasks(page1);

    // Verify sync in page2 with retry for websocket latency
    await expect(async () => {
      const value = await page2.getByTestId("corner-x-tl").inputValue();
      expect(value).toBe("250");
    }).toPass({ intervals: [100, 250, 500], timeout: 5000 });

    // Change another corner
    const cornerYTr1 = page1.getByTestId("corner-y-tr");
    await cornerYTr1.fill("300");
    await cornerYTr1.fill("300");
    await waitForTasks(page1);

    await expect(async () => {
      const value = await page2.getByTestId("corner-y-tr").inputValue();
      expect(value).toBe("300");
    }).toPass({ intervals: [100, 250, 500], timeout: 5000 });

    // Change bottom-left corner
    const cornerXBl1 = page1.getByTestId("corner-x-bl");
    await cornerXBl1.fill("200");
    await cornerXBl1.fill("200");
    await waitForTasks(page1);

    await expect(async () => {
      const value = await page2.getByTestId("corner-x-bl").inputValue();
      expect(value).toBe("200");
    }).toPass({ intervals: [100, 250, 500], timeout: 5000 });

    // Change bottom-right corner
    const cornerYBr1 = page1.getByTestId("corner-y-br");
    await cornerYBr1.fill("400");
    await cornerYBr1.fill("400");
    await waitForTasks(page1);

    await expect(async () => {
      const value = await page2.getByTestId("corner-y-br").inputValue();
      expect(value).toBe("400");
    }).toPass({ intervals: [100, 250, 500], timeout: 5000 });

    await context1.close();
    await context2.close();
  });

  test("Test multiple sources with different types", async ({ page }) => {
    test.setTimeout(120_000);

    await login(page);
    await createProjectionMapper(page, "TestProjectionMapper", "testmapper_sync");

    await openProjectionMapperEditor(
      page,
      "TestProjectionMapper",
      "testmapper_sync"
    );

    // Create multiple sources
    await createSource(page, "iframe", "MultiSource1");
    await sleep(200);
    await fillIframeConfig(page, "http://example1.com");

    await createSource(page, "clock", "MultiSource2");
    await sleep(200);
    await fillClockConfig(page);

    // Verify both appear in source list
    await expect(page.getByTestId("source-item-MultiSource1")).toBeVisible();
    await expect(page.getByTestId("source-item-MultiSource2")).toBeVisible();

    // Select and verify each independently
    await page.getByTestId("source-item-MultiSource1").click();
    await waitForTasks(page);
    await expect(page.getByTestId("iframe-url")).toBeVisible();

    await page.getByTestId("source-item-MultiSource2").click();
    await waitForTasks(page);
    await expect(page.getByTestId("clock-format")).toBeVisible();

    // Save
    await page.getByTestId("save-btn").click();
    await sleep(500);
    await waitForTasks(page);

    // Verify both saved
    await page.reload();
    await sleep(500);
    await waitForTasks(page);

    await expect(page.getByTestId("source-item-MultiSource1")).toBeVisible();
    await expect(page.getByTestId("source-item-MultiSource2")).toBeVisible();

    await logout(page);
  });
});
