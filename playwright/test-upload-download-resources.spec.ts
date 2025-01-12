import { test, expect } from "@playwright/test";
import { sleep, login, makeModule } from "./util";

test("test", async ({ page }) => {
  test.setTimeout(600_000);
  await login(page);
  await makeModule(page, "testuploaddownload");

  await page.getByTestId("add-resource-button").click();

  await page.getByTestId("add-page").click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("testpageroot");
  await page.getByRole("button", { name: "Submit" }).click();
  await page.getByRole("button", { name: "Save and go to page" }).click();
  await expect(
    page.getByRole("heading", { name: "testpageroot" })
  ).toBeVisible();

  // Back to module
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "testuploaddownload" }).click();

  //make folder
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-folder").click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("folder1");
  await page.getByRole("button", { name: "Submit" }).click();

  // into folder
  await page.getByRole("link", { name: "folder1" }).click();

  // another page in folder
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-page").click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("testpagefolder");
  await page.getByRole("button", { name: "Submit" }).click();
  await page.getByRole("button", { name: "Save and go to page" }).click();
  await expect(
    page.getByRole("heading", { name: "testpagefolder" })
  ).toBeVisible();

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "testuploaddownload" }).click();
  await page.getByRole("link", { name: "folder1" }).click();
  // make sure page we put there still there
  await expect(
    page.getByRole("link", { name: "testpagefolder" })
  ).toBeVisible();

  // file in folder
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-file").click();
  await page.locator("#upload").click();
  await page
    .locator("#upload")
    .setInputFiles(
      "kaithem/data/static/img/16x9/pale-green-yellow-flower.avif"
    );
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(
    page.getByRole("img", { name: "folder1/pale-green-yellow-" })
  ).toBeVisible();
  await expect(page.getByText("pale-green-yellow-flower.avif")).toBeVisible();

  await page.getByRole("link", { name: "testuploaddownload" }).click();
  await page.getByTestId("add-resource-button").click();
  await page.getByTestId("add-file").click();
  await page.locator("#upload").click();
  await page
    .locator("#upload")
    .setInputFiles("kaithem/data/static/img/16x9/green-grass.avif");
  await page.getByRole("button", { name: "Upload" }).click();

  // Download one resource
  const downloadPromise = page.waitForEvent("download");
  await page.getByLabel("Download").click();
    const download = await downloadPromise;

    await expect(download.suggestedFilename()).toContain(".yaml");
    await expect(download.suggestedFilename()).toContain("testpageroot");
    await download.saveAs("/dev/shm/downloaded-kaithem-resource.yaml");


  // Download module
  const download1Promise = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Download this module as a zip" })
    .click();
    const download1 = await download1Promise;
    
  await expect(download1.suggestedFilename()).toContain(".zip");
  await expect(download1.suggestedFilename()).toContain("testuploaddown");
    await download1.saveAs("/dev/shm/downloaded-kaithem-module.zip");
    
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByLabel("Delete").click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("testuploaddownload");
  await page.getByRole("button", { name: "Submit" }).click();

  // Place to put the resource
  await page.getByTestId("add-module-button").click();
  await page.getByLabel("Name of New Module").click();
  await page.getByLabel("Name of New Module").fill("testuploadresource");
  await page.getByRole("button", { name: "Submit" }).click();

  // Upload the page resource and check that it works
  await page.getByRole("link", { name: "󱴐 Upload" }).click();
  await page.getByLabel("File", { exact: true }).setInputFiles("/dev/shm/downloaded-kaithem-resource.yaml");
  await page.getByRole("button", { name: "Submit" }).click();
  await page.getByRole("link", { name: "󰐊 Go to page" }).click();
  await expect(
    page.getByRole("heading", { name: "testpageroot" })
  ).toBeVisible();

  // Delete that module
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByLabel("Delete").click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("testuploadresource");
  await page.getByRole("button", { name: "Submit" }).click();

  // Re upload module we downloaded
  await page.getByRole("link", { name: "Upload" }).click();
  await page.getByTestId("modulesfile").setInputFiles("/dev/shm/downloaded-kaithem-module.zip");
  await page.getByRole("button", { name: "Create Module" }).click();

// Make sure everything is there.
  await page
    .locator("summary")
    .filter({ hasText: "testuploaddownload" })
    .click();
  await page.getByRole("link", { name: "testuploaddownload" }).click();
  await expect(page.getByText("green-grass.avif")).toBeVisible();
  await page.getByRole("img", { name: "green-grass.avif" }).click();
  await expect(
    page.getByRole("img", { name: "green-grass.avif" })
  ).toBeVisible();
    
  await expect(page.getByRole("link", { name: "testpageroot" })).toBeVisible();
  await page.getByRole("link", { name: "folder1" }).click();
  await expect(page.getByText("pale-green-yellow-flower.avif")).toBeVisible();
  await expect(
    page.getByRole("img", { name: "folder1/pale-green-yellow-" })
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "testpagefolder" })
  ).toBeVisible();
  await page.getByRole("link", { name: "󰐊 Go to page" }).click();
  await expect(
    page.getByRole("heading", { name: "testpagefolder" })
  ).toBeVisible();
  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByLabel("Delete").click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("testuploaddownload");
  await page.getByRole("button", { name: "Submit" }).click();
});
