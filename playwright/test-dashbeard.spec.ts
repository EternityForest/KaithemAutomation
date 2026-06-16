import { test, expect } from '@playwright/test';
import { login } from './util';
import { sleep } from './util.ts';

/* Preconditions:
Guest has view status permission and nothing else
*/

test('test', async ({ page }) => {
  test.setTimeout(2_400_000);

  await page.goto('http://localhost:8002/');

  await login(page);

  await page.getByRole('link', { name: '󱒕 Modules' }).click();
  await page.getByRole('link', { name: 'TestingServerModule' }).click();
  await page.getByTestId('add-resource-button').click();
  await page.getByTestId('add-dashboard').click();
  await page.getByRole('textbox', { name: 'Name' }).fill('testboard');
  await page.getByRole('button', { name: 'Submit' }).click();
  await page.getByRole('button', { name: 'Submit' }).click();

  await page.goto('http://localhost:8002/modules/module/TestingServerModule');

  await page
    .getByTestId('dashbeard-blurb-testboard')
    .getByTestId('edit-db-map')
    .click();

  await page.getByTestId('components-pane-accordion-title').click();

  // Select root layout
  await page.getByText('plain-layout').click();

  // Add a tagpoint and link it to a the backend
  await page.getByRole('button', { name: '+ tagpoint' }).click();
  await page.getByRole('combobox', { name: 'Tag' }).click();
  await page
    .getByRole('combobox', { name: 'Tag' })
    .fill('/chandler/groups/testgroup1.alpha');

  await page.getByRole('combobox', { name: 'Tag' }).blur();

  await expect(async () => {
    await expect(
      page.getByRole('textbox', { name: 'Enter value' })
    ).toHaveValue('1');
  }).toPass({
    intervals: [1000, 2000, 10_000],
    timeout: 10_000,
  });

  await page.getByText('plain-layout', { exact: true }).click();

  // Add a slider
  await page.getByRole('button', { name: '+ slider' }).click();

  await page.getByTestId('properties-pane-accordion-title').click();

  await page.getByTestId('bindings-pane-accordion-title').click();

  await page.locator('input[name="upstream"]').click();
  await page.locator('input[name="upstream"]').fill('tagpoint-1.value');
  await page.locator('input[name="downstream"]').click();
  await page.locator('input[name="downstream"]').fill('slider-1.value');
  await page.getByRole('button', { name: 'Create Binding' }).click();

  await expect(page.getByRole('slider')).toHaveValue('1');
  //await expect(page.locator('#slider-1')).toContainText('Value (1)');

  // The visible part of the tagpoint
  await expect(page.locator('.small-dashboard-widget-container')).toBeVisible();

  await page.getByText('T tagpoint-1 tagpoint').click();
  await page.getByTestId('properties-pane-accordion-title').click();

  // Make it not visuble
  await page.getByText('Visible').click();
  await expect(
    page.locator('.small-dashboard-widget-container')
  ).not.toBeVisible();

  await page.getByRole('slider').fill('0.68');
  await page.getByRole('button', { name: 'Save' }).click();

  await page.goto('http://localhost:8002/modules/module/TestingServerModule');

  await page
    .locator('div')
    .filter({ hasText: 'Edit Commander Config' })
    .first()
    .click();

  await expect(page.getByRole('slider')).toHaveValue('0.68');
  await page.getByRole('slider').fill('1');

  await page.goto('http://localhost:8002/modules/module/TestingServerModule');

  await page
    .getByTestId('dashbeard-blurb-testboard')
    .getByTestId('edit-db-map')
    .click();

  await sleep(500);
  await expect(async () => {
    await expect(
      page.getByRole('slider', { name: 'Value (1.00)' })
    ).toHaveValue('1');
  }).toPass({
    intervals: [1000, 2000, 10_000],
    timeout: 10_000,
  });

  await expect(page.locator('#slider-1')).toContainText('Value (1.00)');

  await page.getByRole('slider', { name: 'Value (1.00)' }).fill('0.37');

  await page.goto('http://localhost:8002/modules/module/TestingServerModule');

  await page
    .locator('div')
    .filter({ hasText: 'Edit Commander Config' })
    .first()
    .click();
  await expect(page.getByRole('slider')).toHaveValue('0.37');
});
