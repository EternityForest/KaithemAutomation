import { test, expect } from "@playwright/test";

import { login, logout } from "./util";

test("test", async ({ page }) => {
  await login(page);
  // Must be this exact tile, it's a fake tile we put there so we don't need web access for tests
  // TODO: this only tests local cached tiles not web fetching
  await page.goto("http://localhost:8002/maptiles/tile/0/0/0.png");
  await expect(page.getByRole("img")).toBeVisible();
  await logout(page);
});
