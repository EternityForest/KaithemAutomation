import { test, expect } from '@playwright/test';
import { deleteModule, login, logout, makeModule } from './util';

test('test', async ({ page }) => {
  await login(page);

  makeModule(page, 'test_presets');

  await page.getByTestId('add-resource-button').click();
  await page.getByTestId('add-chandler_board').click();
  await page.getByLabel('Resource Name').click();
  await page.getByLabel('Resource Name').fill('p');
  await page.getByRole('button', { name: 'Submit' }).click();


  await page.getByRole('link', { name: '󱒕 Modules' }).click();
  await page.getByRole('link', { name: 'test_presets' }).click();
  await page.getByRole('link', { name: '󰏬 Editor' }).click();


  await page.getByPlaceholder('New group name').click();
  await page.getByPlaceholder('New group name').fill('foo');
  await page.getByTestId('add-group-button').click();

  await page.getByLabel('Settings').click();

  await page.getByRole('button', { name: 'Universes' }).click();
  await page.getByPlaceholder('New Universe Name').click();
  await page.getByPlaceholder('New Universe Name').fill('test');
  await page.getByRole('cell', { name: 'Number' }).dblclick();
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Update Settings' }).click();
  await page.getByRole('button', { name: '󰅖 Close' }).click();

  await page.getByRole('button', { name: '󰏫 Fixture Types' }).click();

  page.once('dialog', dialog => {
    dialog.accept("textfixtype").catch(() => { })
  });

  await page.getByRole('button', { name: '󰐕 New' }).click()



  await page.getByTestId("fixture-type-to-edit").selectOption('textfixtype');
  //TODO should not need to run twice
  await page.getByRole('button', { name: 'Add Channel' }).click();
  await page.getByRole('button', { name: 'Add Channel' }).click();

  await page.getByLabel('Type:').first().selectOption('intensity');
  await page.getByRole('button', { name: 'Add Channel' }).click();
  await page.getByLabel('Type:').nth(1).selectOption('red');
  await page.getByRole('button', { name: 'Add Channel' }).click();
  await page.getByLabel('Type:').nth(2).selectOption('green');
  await page.getByRole('button', { name: 'Add Channel' }).click();
  await page.getByLabel('Type:').nth(3).selectOption('blue');
  await page.getByRole('button', { name: '󰅖 Close' }).click();


  await page.getByRole('button', { name: 'Fixtures' }).click();
  await page.locator('select').selectOption('textfixtype');
  await page.getByRole('textbox').click();
  await page.getByRole('textbox').fill('test1');
  await page.getByRole('row', { name: 'Universe', exact: true }).getByRole('combobox').click();
  await page.getByRole('row', { name: 'Universe', exact: true }).getByRole('combobox').fill('test');
  await page.getByRole('spinbutton').click();
  await page.getByRole('spinbutton').fill('1');
  await page.getByRole('spinbutton').click();



  await page.getByRole('button', { name: 'Add and Update' }).click();


  await page.getByRole('link', { name: '󱒕 Modules' }).click();
  await page.getByRole('link', { name: 'test_presets' }).click();
  await page.getByRole('link', { name: '󰏬 Editor' }).click();


  await page.getByRole('button', { name: 'foo' }).click();

  await page.getByRole('button', { name: 'Add/Remove' }).click();
  await page.getByRole('cell', { name: '󰐕 Add' }).getByRole('button').click();
  await page.getByRole('button', { name: '󰢻 Normal View' }).click();
  await page.getByTestId('details-fixture-channels-summary').click();
  await page.locator('div').filter({ hasText: /^blue0\.000$/ }).getByRole('slider').fill('126');
  await page.locator('div').filter({ hasText: /^blue126\.0$/ }).getByRole('slider').fill('253');
  await page.locator('div').filter({ hasText: /^green0\.000$/ }).getByRole('slider').fill('37');
  await page.locator('div').filter({ hasText: /^green37\.00$/ }).getByRole('slider').fill('255');

  page.once('dialog', dialog => {
    console.log(`Dialog message: ${dialog.message()}`);
    dialog.accept("aqua").catch(() => { });
  });
  await page.getByTestId("save-preset-options").selectOption('');

  await page.locator('div').filter({ hasText: /^blue253\.0$/ }).getByRole('slider').fill('234');
  await page.locator('div').filter({ hasText: /^blue234\.0$/ }).getByRole('slider').fill('0');
  await page.locator('div').filter({ hasText: /^green255\.0$/ }).getByRole('slider').fill('0');
  await page.getByTestId('close-group').click();

  await page.getByRole('button', { name: 'Presets' }).click();
  await page.getByText('Values', { exact: true }).click();

  await expect(page.getByLabel('blue')).toHaveValue('253');
  await page.getByLabel('intensity').click();
  await page.getByLabel('intensity').fill('50');
    await page.getByRole('button', { name: '󰅖 Close' }).click();

  await page.getByRole('button', { name: 'foo' }).click();
  await page.getByRole('button', { name: 'Presets', exact: true }).click();
  await page.getByRole('button', { name: 'aqua' }).click();


  await expect(page.locator('div').filter({ hasText: /^intensity50\.00$/ }).getByRole('slider')).toHaveValue('50');
  await page.getByTestId('close-group').click();

  await page.goto("http://localhost:8002/chandler/config/test_presets:p");
  await page.getByRole('button', { name: 'Universes' }).click();
  await page.getByRole('row', { name: 'test' }).getByRole('link').click();
  await expect(page.locator('section')).toContainText('50.0');
  await expect(page.locator('section')).toContainText('253.0');

  await deleteModule(page, 'test_presets');
});