import { test, expect, Page } from "@playwright/test";
import { BASE, login, logout, makeModule, deleteModule } from "./util";

/**
 * Test suite for the text editor plugin.
 *
 * Uses the file resources system to create a plain text file, then
 * opens it in the text editor and exercises the file manager sidebar
 * and the Ace editor.
 */

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function openTextEditor(page: Page, module: string, resource: string) {
  await page.goto(
    `${BASE}/text-editor-plugin/edit?module=` +
      encodeURIComponent(module) +
      "&resource=" +
      encodeURIComponent(resource)
  );
  await sleep(1000);
}

test("text editor opens and edits", async ({ page }) => {
  test.setTimeout(600_000);

  await login(page);
  await makeModule(page, "test_text_editor");

  // Create a folder resource that holds the file
  await page.goto(`${BASE}/modules/module/test_text_editor`);
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-folder").click();
  await page.getByLabel("Name").fill("files");
  await page.getByRole("button", { name: "Submit" }).click();

  // Open the text editor on the workspace folder. The editor page is
  // served from the Vite build.
  await openTextEditor(page, "test_text_editor", "files");

  // Sidebar toggle
  await page.getByTestId("sidebar-toggle").click();
  await expect(page.getByTestId("sidebar")).toBeVisible();

  // New file via the sidebar context menu
  await page
    .getByTestId("sidebar")
    .getByTestId("tree-root")
    .click({ button: "right" });
  await page.once("dialog", (dialog) => {
    dialog.accept("hello.txt").catch(() => {});
  });
  await page.getByTestId("ctx-new-file").click();
  await sleep(300);

  // The file should be in the tree
  await expect(page.getByTestId("sidebar")).toContainText("hello.txt");

  // Open it in the editor
  await page.getByTestId("sidebar").getByText("hello.txt").click();
  await sleep(500);

  // Ace editor should be mounted
  await expect(page.getByTestId("ace-hello.txt")).toBeVisible();

  // Type into the editor
  await page.getByTestId("ace-hello.txt").click();
  await page.keyboard.type("Hello, world");

  // Save
  await page.getByTestId("save-btn").click();
  await sleep(500);

  // Verify the file content on disk via the API
  const resp = await page.request.get(
    `${BASE}/text-editor-plugin/api/read?module=test_text_editor&resource=files/hello.txt`
  );
  const j = await resp.json();
  expect(j.content).toContain("Hello, world");

  // Rename via context menu
  await page.getByTestId("sidebar").getByText("hello.txt").click({ button: "right" });
  await page.once("dialog", (dialog) => {
    dialog.accept("renamed.txt").catch(() => {});
  });
  await page.getByTestId("ctx-rename").click();
  await sleep(300);
  await expect(page.getByTestId("sidebar")).toContainText("renamed.txt");

  // Delete via context menu
  await page
    .getByTestId("sidebar")
    .getByText("renamed.txt")
    .click({ button: "right" });
  await page.once("dialog", (dialog) => {
    dialog.accept().catch(() => {});
  });
  await page.getByTestId("ctx-delete").click();
  await sleep(300);
  await expect(page.getByTestId("sidebar")).not.toContainText("renamed.txt");

  await deleteModule(page, "test_text_editor");
  await logout(page);
});
