import { test, expect } from "@playwright/test";
import { deleteModule, login, logout, makeModule } from "./util";

test("test", async ({ page }) => {
  /*
    Logs in, creates a module, creates a page, and creates an event
    Tests basic fuctions, then renames them both and confirms they still work.
    Delete module then log out.
    */
  test.setTimeout(2400000);
  await login(page);

  // Create a module
  await makeModule(page, "PlaywrightBasicModuleFeatures");

  // Create a page
  await page.getByTestId("add-resource-button").click();

  await page.getByRole("link", { name: "Page" }).click();
  await page.getByLabel("Name").click();
  await page.getByLabel("Name").fill("p1");
  await page.getByRole("button", { name: "Submit" }).click();
  await page.locator(".ace_content").first().fill('foo = "123"\n\n');

  await page.getByLabel('Setup Code').fill('setup = "234"\n\n');

  await page
    .locator("div")
    .filter({ hasText: '{% extends "pagetemplate.j2.' })
    .nth(2)
    .click();
  await page
    .locator("div")
    .filter({ hasText: '{% extends "pagetemplate.j2.' })
    .nth(2)
    .fill("    {{foo}}{{setup}}567\n\n");
  await page.getByRole("button", { name: "Save and go to page" }).click();

  // TODO is modules link supposed to be visible here?
  await expect(page.getByText("123234567")).toBeVisible();
  // Ace code makes complex stuff hard to type in automatically it seems?
  // await expect(page.getByRole('heading')).toContainText('p1');

  await page.goto("http://localhost:8002/modules");
  await page
    .getByRole("link", { name: "PlaywrightBasicModuleFeatures" })
    .click();

  // Make sure it's in the list
  await expect(page.getByRole("link", { name: "p1" })).toContainText("p1");

  // Give that page a label
  await page.getByLabel("Resource Metadata").click();
  await page.getByText("Display", { exact: true }).click();
  await page.getByLabel("Label Image URL").click();
  await page
    .getByLabel("Label Image URL")
    .fill("16x9/japanese-forest-grass.avif");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("img", { name: "thumbnail" })).toBeVisible();

  // Create an event
  await page.getByTestId('add-resource-button').click();
  await page.getByRole('link', { name: 'Event' }).click();
  await page.getByLabel('Name').click();
  await page.getByLabel('Name').fill('e1');
  await page.getByRole('button', { name: 'Submit' }).click();
  await expect(page.getByRole('paragraph')).toContainText('This event has not ran since it loaded.');

  await page.locator('#triggerbox').fill('True');
  await page.getByRole('button', { name: 'Save Changes' }).click();

  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures")
  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures")

  await expect(page.getByText('Trigger: True Last Ran:')).toContainText('ago');
  await page.getByRole('link', { name: 'e1' }).click();

  // Waste some time
  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures")
  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures")

  // Check for the "this last ran X seconds ago"
  await expect(page.getByText('Trigger: True')).toContainText('ago');
  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures#resources");

  // Rename the page
  await page.getByRole('link', { name: 'Move' }).nth(1).click();
  await page.getByLabel('New Name').click();
  await page.getByLabel('New Name').fill('p1_new');
  await page.getByRole('button', { name: 'Submit' }).click();
  await page.getByRole('link', { name: 'Go to page' }).click();
  await page.locator('html').click();
  await expect(page.getByText('123234567')).toBeVisible()

  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures#resources");

  //Check page works at new location
  await page.getByRole('link', { name: 'p1_new' }).click();
  await expect(page.getByRole('heading')).toContainText('PlaywrightBasicModuleFeatures: p1_new');
  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures#resources");

  // Move the event
  await page.getByRole('link', { name: 'Move' }).first().click();
  await page.getByLabel('New Name').click();
  await page.getByLabel('New Name').fill('e1_new');
  await page.getByRole('button', { name: 'Submit' }).click();
  //Waste time
  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures")
  await page.goto("http://localhost:8002/modules/module/PlaywrightBasicModuleFeatures")

  await expect(page.getByText('Trigger: True Last Ran:')).toContainText('ago');

  await page.getByRole('link', { name: 'e1_new' }).click();
  await expect(page.locator('h2')).toContainText('e1_new');

  await deleteModule(page, 'PlaywrightBasicModuleFeatures');

  await expect(page.getByRole('heading')).toContainText('Modules');
  await logout(page);
});
