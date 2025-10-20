import { test, expect } from "@playwright/test";
import { login } from "./util";

test("test", async ({ page }) => {
    /*
      Logs in, creates a module, creates a page, and creates an event
      Tests basic fuctions, then renames them both and confirms they still work.
      Delete module then log out.
      */
    test.setTimeout(2_400_000);
    await login(page);


    // Test message bus LOGS
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: 'Message Bus Logs' }).click();
    await expect(page.getByRole('heading', { name: '/system/startup' })).toBeVisible();

    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰍹 Processes' }).click();
    await expect(page.getByRole('heading', { name: 'Running Proceses' })).toBeVisible();


    // tEST 
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('button', { name: 'Inspect' }).click();
    await expect(page.getByRole('heading', { name: 'Inspecting modules' })).toBeVisible();
    await page.getByRole('button', { name: 'Crypto', exact: true }).click();
    await page.getByRole('button', { name: 'Hash' }).click();
    await page.getByRole('button', { name: 'CMAC' }).click();
    await expect(page.getByRole('heading', { name: 'Inspecting modules[\'Crypto\'].' })).toBeVisible();
    
    
    
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: 'Environment' }).click();
    await expect(page.getByRole('cell', { name: 'USER', exact: true })).toBeVisible();
});