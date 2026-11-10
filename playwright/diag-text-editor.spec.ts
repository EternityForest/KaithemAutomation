import { test, expect, Page } from "@playwright/test";
import { BASE, login, makeModule, deleteModule } from "./util";

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

test("diagnostic: open editor on nested file directly", async ({ page }) => {
  test.setTimeout(300_000);
  page.on("console", (m) => console.log("PAGE:", m.type(), m.text()));
  page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
  page.on("requestfailed", (r) =>
    console.log("REQFAIL:", r.url(), r.failure()?.errorText)
  );
  page.on("response", (r) => {
    if (r.status() >= 500) console.log("HTTP500:", r.url(), r.status());
  });

  const step = (s: string) => console.log("STEP:", s);

  await login(page);
  step("logged in");
  await makeModule(page, "test_text_editor_diag");
  step("module made");

  await page.goto(`${BASE}/modules/module/test_text_editor_diag`);
  step("on module page");
  await page.getByTestId("add-resource-button").click();
  step("add-resource clicked");
  await page.getByTestId("add-folder").click();
  step("add-folder clicked");
  await page.getByLabel("Name").fill("files");
  step("filled name");
  await page.getByRole("button", { name: "Submit" }).click();
  step("folder submitted");

  await page.goto(`${BASE}/modules/module/test_text_editor_diag/files`);
  step("on files folder page");
  await page.getByTestId("add-resource-button").click();
  step("add-resource clicked 2");
  await page.getByTestId("add-resource").click();
  step("add-resource clicked 3");
  await page.getByLabel("Name").fill("nested.txt");
  step("filled name 2");
  await page.getByRole("button", { name: "Submit" }).click();
  step("file submitted");

  // Open the editor directly on the nested file
  await openTextEditor(page, "test_text_editor_diag", "files/nested.txt");
  step("editor opened");

  await sleep(500);
  const state = await page.evaluate(() => {
    const host = document.querySelector("text-editor-page") as any;
    const root = host?.renderRoot ?? host?.shadowRoot;
    const el = root?.querySelector("#ace-files\\/nested.txt");
    return {
      hostFound: !!host,
      hasShadowRoot: !!host?.shadowRoot,
      tabs: host?.tabs?.map((t: any) => t.path),
      activeTab: host?.activeTab,
      ids: root
        ? Array.from(root.querySelectorAll("div[id]")).map((d: any) => d.id)
        : null,
      elFound: !!el,
    };
  });
  console.log("STATE:", JSON.stringify(state));
  await deleteModule(page, "test_text_editor_diag");
  step("module deleted");
});
