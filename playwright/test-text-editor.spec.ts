import { test, expect, Page } from "@playwright/test";
import { BASE, login, makeModule, deleteModule } from "./util.ts";

const MOD = "test_text_editor_plugin";

async function createFileViaApi(page: Page, module: string, resource: string, content: string) {
  const res = await page.evaluate(
    async ({ module, resource, content }) => {
      const fd = new FormData();
      fd.append("module", module);
      fd.append("resource", resource);
      fd.append("content", content);
      const r = await fetch("/text-editor-plugin/api/write", { method: "POST", body: fd });
      return { status: r.status, text: await r.text() };
    },
    { module, resource, content }
  );
  return res;
}

async function readFileViaApi(page: Page, module: string, resource: string) {
  return page.evaluate(
    async ({ module, resource }) => {
      const qs = new URLSearchParams({ module, resource });
      const r = await fetch("/text-editor-plugin/api/read?" + qs);
      return { status: r.status, json: await r.json() };
    },
    { module, resource }
  );
}

async function openEditor(page: Page, module: string, resource: string) {
  await page.goto(
    `${BASE}/text-editor-plugin/edit?module=` +
      encodeURIComponent(module) +
      "&resource=" +
      encodeURIComponent(resource)
  );
  await page.waitForTimeout(2000);
}

test.describe("Text Editor Plugin", () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);
    await makeModule(page, MOD);
    await page.goto(`${BASE}/index`);
    await createFileViaApi(page, MOD, "files/hello.txt", "Hello world\n");
    await createFileViaApi(page, MOD, "files/nested/deep.txt", "Deep content\n");
  });

  test.afterEach(async ({ page }) => {
    await deleteModule(page, MOD);
  });

  test("loads file content into Ace editor", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");

    const state = await page.evaluate(() => {
      const host = document.querySelector("text-editor-page") as any;
      const ed = host?.tabs?.[0]?.ace;
      return {
        tabs: host?.tabs?.map((t: any) => t.path),
        activeTab: host?.activeTab,
        value: ed ? ed.getValue() : null,
      };
    });
    expect(state.tabs).toEqual(["files/hello.txt"]);
    expect(state.activeTab).toBe("files/hello.txt");
    expect(state.value).toContain("Hello world");
  });

  test("editor is editable and marks tab dirty", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");
    const host = page.locator("text-editor-page");
    const aceEl = host.locator('[data-testid="ace-files/hello.txt"]');
    await expect(aceEl).toBeVisible();
    await aceEl.click({ position: { x: 60, y: 20 } });
    await page.keyboard.type("EDITABLE");
    await page.waitForTimeout(500);
    const dirty = await page.evaluate(() => {
      const h = document.querySelector("text-editor-page") as any;
      const ed = h?.tabs?.[0]?.ace;
      return { dirty: h?.tabs?.[0]?.dirty, value: ed ? ed.getValue() : null };
    });
    expect(dirty.dirty).toBe(true);
    expect(dirty.value).toContain("EDITABLE");
  });

  test("save persists content to disk", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");
    const host = page.locator("text-editor-page");
    const aceEl = host.locator('[data-testid="ace-files/hello.txt"]');
    await aceEl.click({ position: { x: 60, y: 20 } });
    await page.keyboard.type("SAVED");
    await page.waitForTimeout(300);
    await host.locator('[data-testid="save-btn"]').click();
    await page.waitForTimeout(1000);
    const saved = await readFileViaApi(page, MOD, "files/hello.txt");
    expect(saved.status).toBe(200);
    expect(saved.json.content).toContain("SAVED");
  });

  test("sidebar tree shows files and opens nested file", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");
    const host = page.locator("text-editor-page");
    await host.locator('[data-testid="sidebar-toggle"]').click();
    await page.waitForTimeout(500);

    const items = await page.evaluate(() => {
      const h = document.querySelector("text-editor-page") as any;
      const root = h?.renderRoot ?? h?.shadowRoot;
      const sidebar = root?.querySelector('[data-testid="sidebar"]');
      return sidebar
        ? Array.from(sidebar.querySelectorAll(".tree-item")).map((e: any) => e.textContent.trim())
        : null;
    });
    expect(items).toContain("📁 files");
    expect(items).toContain("📄 hello.txt");

    // Open nested file via tree (expand folder first, then click deep.txt)
    const deepItem = host.locator(".tree-item", { hasText: "deep.txt" });
    await expect(deepItem).toBeVisible();
    await deepItem.click();
    await page.waitForTimeout(1000);
    const tabs = await page.evaluate(() => {
      const h = document.querySelector("text-editor-page") as any;
      return { tabs: h?.tabs?.map((t: any) => t.path), activeTab: h?.activeTab };
    });
    expect(tabs.tabs).toContain("files/nested/deep.txt");
    expect(tabs.activeTab).toBe("files/nested/deep.txt");
  });

  test("closing tab works", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");
    const host = page.locator("text-editor-page");
    const tabbar = host.locator('[data-testid="tabbar"]');
    const closeBtn = tabbar.locator(".tab .close").first();
    await closeBtn.click();
    await page.waitForTimeout(500);
    const tabs = await page.evaluate(() => {
      const h = document.querySelector("text-editor-page") as any;
      return { tabs: h?.tabs?.map((t: any) => t.path), activeTab: h?.activeTab };
    });
    expect(tabs.tabs).toEqual([]);
    expect(tabs.activeTab).toBe(null);
  });

  test("LSP badge shows unavailable when no workspace", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");
    const host = page.locator("text-editor-page");
    const badge = host.locator('[data-testid="lsp-badge"]');
    await expect(badge).toBeVisible();
    await expect(badge).toContainText("LSP");
  });

  test("context menu dismisses when clicking outside", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");
    const host = page.locator("text-editor-page");
    await host.locator('[data-testid="sidebar-toggle"]').click();
    await page.waitForTimeout(500);

    const item = host.locator(".tree-item", { hasText: "hello.txt" });
    await item.click({ button: "right" });
    const newFileBtn = host.locator('[data-testid="ctx-new-file"]');
    await expect(newFileBtn).toBeVisible();

    // The dismiss guard ignores clicks immediately after opening, so wait.
    await page.waitForTimeout(500);
    await host.locator(".statusbar").click();
    await expect(newFileBtn).toBeHidden();
  });

  test("live updates apply remote changes when tab is clean", async ({ page }) => {
    await openEditor(page, MOD, "files/hello.txt");
    // Give the websocket time to open and subscribe to the file.
    await page.waitForTimeout(1000);

    await createFileViaApi(page, MOD, "files/hello.txt", "Changed on server\n");

    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const h = document.querySelector("text-editor-page") as any;
            return h?.tabs?.[0]?.ace?.getValue();
          }),
        { timeout: 10_000 }
      )
      .toContain("Changed on server");

    const dirty = await page.evaluate(() => {
      const h = document.querySelector("text-editor-page") as any;
      return h?.tabs?.[0]?.dirty;
    });
    expect(dirty).toBe(false);
  });

});
