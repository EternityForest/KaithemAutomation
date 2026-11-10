import { test } from "@playwright/test";
import { BASE, login, makeModule } from "./util";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test("diagnostic: full flow to editor state", async ({ page }) => {
  test.setTimeout(120_000);
  page.on("console", (m) => console.log("PAGE:", m.type(), m.text()));
  page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
  page.on("response", (r) => {
    if (r.status() >= 500) console.log("HTTP500:", r.url(), r.status());
  });

  await login(page);
  console.log("STEP: logged in");

  await makeModule(page, "test_text_editor_diag");

  // Create a folder resource that holds the file
  await page.goto(`${BASE}/modules/module/test_text_editor_diag`);
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-folder").click();
  await page.getByLabel("Name").fill("files");
  await page.getByRole("button", { name: "Submit" }).click();
  console.log("STEP: folder submitted");

  // Open the editor on the workspace folder
  await page.goto(
    `${BASE}/text-editor-plugin/edit?module=test_text_editor_diag&resource=files`
  );
  console.log("STEP: editor opened, URL:", page.url());
  await sleep(2000);

  // Open the sidebar
  await page.getByTestId("sidebar-toggle").click();
  await sleep(500);

  // Create a file via the sidebar context menu
  await page
    .getByTestId("sidebar")
    .getByTestId("tree-root")
    .click({ button: "right" });
  await page.once("dialog", (dialog) => {
    dialog.accept("nested.txt").catch(() => {});
  });
  await page.getByTestId("ctx-new-file").click();
  await sleep(300);
  console.log("STEP: file created via sidebar");

  // Open it in a tab
  await page.getByTestId("sidebar").getByText("nested.txt").click();
  await sleep(1000);

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
});
