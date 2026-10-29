import { test, expect, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { login, makeModule } from "./util";

/* Test suite for CorePluginPresentationScreen.
 *
 * Covers resource creation, the admin screen (file list, refresh, config,
 * embedded viewer) and the editor entry point.  The PPTX engine itself is
 * exercised by the editor/viewer manually; here we check the plumbing that
 * ties the pages to the REST API.
 */

const MODULE = "TestPresentationScreen";
const RESOURCE = "screens";
const FIXTURE = path.join(
  process.cwd(),
  "kaithem",
  "src",
  "tests",
  "fixtures",
  "minimal.pptx"
);

const adminUrl =
  `http://localhost:8002/presentation-screen/admin/${MODULE}/${RESOURCE}`;
const apiUrl = `http://localhost:8002/presentation-screen/api`;

async function createScreen(page: Page, name: string) {
  await page.goto(`http://localhost:8002/modules/module/${MODULE}`);
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-presentation_screen").click();
  await page.getByLabel("Resource Name").fill(name);
  await page.getByLabel("Title").fill("Test Screen");
  await page.getByRole("button", { name: "Create" }).click();
}

async function openAdmin(page: Page) {
  await page.goto("http://localhost:8002/index");
  await page.getByRole("link", { name: "Modules" }).click();
  await page.getByRole("link", { name: MODULE }).click();
  await page.getByTestId("edit-presentation-screen").click();
  await expect(page.getByTestId("admin-refresh")).toBeVisible();
}

async function uploadDeck(page: Page, fileName: string) {
  const body = fs.readFileSync(FIXTURE);
  const response = await page.request.post(
    `${apiUrl}/save/${MODULE}/${RESOURCE}/${fileName}`,
    { data: body }
  );
  expect(response.ok()).toBeTruthy();
}

test("presentation screen resource creates an admin page", async ({ page }) => {
  await login(page);
  await makeModule(page, MODULE);
  await createScreen(page, RESOURCE);

  // The Manage button on the module page links to the admin app.
  await page.goto(`http://localhost:8002/modules/module/${MODULE}`);
  await expect(
    page.getByTestId(`presentation-screen-blurb-${RESOURCE}`)
  ).toBeVisible();
  await page.getByTestId("edit-presentation-screen").click();

  await expect(page).toHaveURL(new RegExp(`/presentation-screen/admin/`));
  await expect(page.getByTestId("admin-title")).toBeVisible();
  await expect(page.getByTestId("admin-no-files")).toBeVisible();
  await expect(page.getByTestId("admin-new-presentation")).toBeVisible();
  await expect(page.getByTestId("admin-viewer-frame")).toBeVisible();
});

test("admin file list, editor link, controls and delete", async ({ page }) => {
  await login(page);
  await makeModule(page, MODULE);
  await createScreen(page, RESOURCE);
  await uploadDeck(page, "deck.pptx");
  await openAdmin(page);

  // Refresh pulls the uploaded deck from the REST endpoint.
  await page.getByTestId("admin-refresh").click();
  await expect(page.getByTestId("file-row")).toHaveCount(1);
  await expect(page.getByTestId("file-name")).toHaveText("deck.pptx");

  // The editor is prefilled from the ?file= URL parameter and really fetches
  // that deck instead of falling back to the engine's built-in default.
  const deckRequest = page.waitForRequest(
    (request) =>
      request.url().includes(`/presentation-screen/api/file/${MODULE}/`) &&
      request.url().endsWith("/deck.pptx"),
    { timeout: 10_000 }
  );
  await page.getByTestId("file-edit").click();
  await expect(page.getByTestId("editor-filename")).toHaveValue(
    "deck.pptx"
  );
  await deckRequest;

  // The engine stylesheet must be present, otherwise the chrome renders with
  // undefined --pptx-* theme tokens.
  const popoverToken = await page.evaluate(() =>
    getComputedStyle(document.documentElement)
      .getPropertyValue("--pptx-popover")
      .trim()
  );
  expect(popoverToken).not.toBe("");

  // The editor deliberately does not load the site theme.
  const stylesheetHrefs = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')].map((link) => link.href)
  );
  expect(stylesheetHrefs.some((href) => href.includes("barrel.css"))).toBe(
    false
  );

  // The property inspector is enabled (it used to be disabled, which left
  // its toggle button doing nothing).
  await expect(
    page.locator(".ps-editor__stage .pptxv-inspector").first()
  ).toBeVisible();

  await page.goto(adminUrl);
  await expect(page.getByTestId("admin-refresh")).toBeVisible();

  // Nothing is playing yet, so the state dump says so.
  await expect(page.getByTestId("state-current")).toContainText("none");

  // Starting a presentation is disruptive, so it asks first.
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain("deck.pptx");
    dialog.accept().catch(() => {});
  });
  await page.getByTestId("file-play").click();
  await expect(page.getByTestId("admin-status")).toContainText(
    "Playing",
    { timeout: 10_000 }
  );
  await expect(page.getByTestId("state-current")).toContainText(
    "deck.pptx"
  );

  // Next/prev replace the whole server state.
  await expect(page.getByTestId("control-next")).toBeEnabled();
  await page.getByTestId("control-next").click();
  await expect(page.getByTestId("state-current")).toContainText(
    "slide 1"
  );

  // Storing the current state as the default only writes the resource.
  await page.getByTestId("admin-set-default").click();
  await expect(page.getByTestId("state-default")).toContainText(
    "deck.pptx"
  );

  // Stopping is disruptive too.
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain("Stop");
    dialog.accept().catch(() => {});
  });
  await page.getByTestId("control-stop").click();
  await expect(page.getByTestId("admin-status")).toContainText("stop");

  // Deleting requires confirmation.
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain("deck.pptx");
    dialog.accept().catch(() => {});
  });
  await page.getByTestId("file-delete").click();
  await expect(page.getByTestId("admin-no-files")).toBeVisible();
  await expect(page.getByTestId("file-row")).toHaveCount(0);
});

test("config permission persists and locks viewing", async ({ page }) => {
  await login(page);
  await makeModule(page, MODULE);
  await createScreen(page, RESOURCE);
  await uploadDeck(page, "deck.pptx");
  await openAdmin(page);

  await page.getByTestId("admin-view-permission").fill("system_admin");
  await page.getByTestId("admin-save-settings").click();
  await expect(page.getByTestId("admin-status")).toContainText(
    "saved"
  );

  // Reopening shows the persisted setting.
  await page.reload();
  await expect(page.getByTestId("admin-view-permission")).toHaveValue(
    "system_admin"
  );

  const config = await (
    await page.request.get(`${apiUrl}/config/${MODULE}/${RESOURCE}`)
  ).json();
  expect(config.view_permission).toBe("system_admin");

  // While locked, anonymous clients cannot fetch the file.
  const cookies = await page.context().cookies();
  await page.context().clearCookies();
  const locked = await page.request.get(
    `${apiUrl}/file/${MODULE}/${RESOURCE}/deck.pptx`
  );
  expect([401, 403]).toContain(locked.status());
  await page.context().addCookies(cookies);

  // Clearing the permission restores open viewing.
  await page.reload();
  await page.getByTestId("admin-view-permission").fill("");
  await page.getByTestId("admin-save-settings").click();
  await expect(page.getByTestId("admin-view-permission")).toHaveValue("");

  const open = await page.request.get(
    `${apiUrl}/file/${MODULE}/${RESOURCE}/deck.pptx`
  );
  expect(open.status()).toBe(200);
});

test("bookmarks save, overwrite, goto, shortcut and delete", async ({
  page,
}) => {
  await login(page);
  await makeModule(page, MODULE);
  await createScreen(page, RESOURCE);
  await uploadDeck(page, "deck.pptx");
  await openAdmin(page);
  await page.getByTestId("admin-refresh").click();

  // Start with an empty collection, then bookmark the stopped state.
  await expect(page.getByTestId("admin-no-bookmarks")).toBeVisible();
  await page.getByTestId("bookmark-new-name").fill("opening");
  await page.getByTestId("bookmark-add").click();
  await expect(page.getByTestId("bookmark-row")).toHaveCount(1);
  await expect(page.getByTestId("bookmark-name")).toHaveText("opening");
  await expect(page.getByTestId("bookmark-state")).toContainText("stopped");

  // Play the deck and advance a slide.
  page.once("dialog", (dialog) => {
    dialog.accept().catch(() => {});
  });
  await page.getByTestId("file-play").click();
  await expect(page.getByTestId("state-current")).toContainText("deck.pptx");
  await page.getByTestId("control-next").click();
  await expect(page.getByTestId("state-current")).toContainText("slide 1");

  // The shortcut is stored in the bookmark's meta.
  await page.getByTestId("bookmark-shortcut").fill("123");
  await page.getByTestId("bookmark-shortcut").blur();
  await expect(page.getByTestId("admin-status")).toContainText("Shortcut");

  // Overwriting replaces the state but keeps the meta.
  await page.getByTestId("bookmark-save").click();
  await expect(page.getByTestId("admin-status")).toContainText("meta kept");
  await expect(page.getByTestId("bookmark-state")).toContainText("deck.pptx");

  // Stop the show, then jump back to the bookmarked state with Go.
  page.once("dialog", (dialog) => {
    dialog.accept().catch(() => {});
  });
  await page.getByTestId("control-stop").click();
  await expect(page.getByTestId("state-current")).toContainText("none");
  await page.getByTestId("bookmark-goto").click();
  await expect(page.getByTestId("state-current")).toContainText("slide 1");

  // The shortcut survived the state overwrite.
  await expect(page.getByTestId("bookmark-shortcut")).toHaveValue("123");

  // Deleting a bookmark asks first.
  page.once("dialog", (dialog) => {
    dialog.accept().catch(() => {});
  });
  await page.getByTestId("bookmark-delete").click();
  await expect(page.getByTestId("admin-no-bookmarks")).toBeVisible();
  await expect(page.getByTestId("bookmark-row")).toHaveCount(0);
});
