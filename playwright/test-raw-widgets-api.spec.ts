import { test, expect } from "@playwright/test";
import { login, sleep } from "./util";


/*This uses a special page in the preloaded module that just 
sends a message after 3 seconds, to get some coverage of the raw widget data api
at widgets/wsraw
*/
test("test", async ({ page }) => {
  await login(page);

  await page.getByRole("link", { name: "󱒕 Modules" }).click();
  await page.getByRole("link", { name: "TestingServerModule" }).click();
  await page.getByRole("link", { name: "󰐊 Go to page" }).click();
  await sleep(1000);
  await expect(page.getByText("Got response!")).not.toBeVisible();
  await sleep(2000);
  await expect(page.getByText("Got response!")).toBeVisible();
});
