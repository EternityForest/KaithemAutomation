import { test, expect } from '@playwright/test';
import { login, logout } from './util';

test('test', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: '󰐕 Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('test_presets');
    await page.getByRole('button', { name: 'Submit' }).click();


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

    await page.getByRole('link', { name: '󰢻 Settings' }).click();

    await page.getByRole('button', { name: 'Universes' }).click();
    await page.getByPlaceholder('New Universe Name').click();
    await page.getByPlaceholder('New Universe Name').fill('test');
    await page.getByRole('cell', { name: 'Number' }).dblclick();
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await page.getByRole('button', { name: 'Update Settings' }).click();
    await page.getByRole('button', { name: '󰅖 Close' }).click();


    await page.getByRole('button', { name: 'Fixtures' }).click();
    await page.getByRole('textbox').click();
    await page.getByRole('textbox').fill('test1');
    await page.getByRole('row', { name: 'Universe', exact: true }).getByRole('combobox').click();
    await page.getByRole('row', { name: 'Universe', exact: true }).getByRole('combobox').fill('test');
    await page.getByRole('spinbutton').click();
    await page.getByRole('spinbutton').fill('1');
    await page.getByRole('spinbutton').click();

    await page.locator('select').selectOption('7ch DGBR');

    await page.getByRole('button', { name: 'Add and Update' }).click();


    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'test_presets' }).click();
    await page.getByRole('link', { name: '󰏬 Editor' }).click();


    await page.getByRole('button', { name: 'foo' }).click();

    await page.getByRole('button', { name: '󱭼 Channels' }).click();
    await page.getByRole('cell', { name: '󰐕 Add' }).getByRole('button').click();
    await page.locator('summary').filter({ hasText: 'Channels' }).click();
    await page.getByRole('button', { name: '󰢻 Normal View' }).click();
    await page.locator('div').filter({ hasText: /^blue0\.000$/ }).getByRole('slider').fill('126');
    await page.locator('div').filter({ hasText: /^blue126\.0$/ }).getByRole('slider').fill('255');
    await page.locator('div').filter({ hasText: /^green0\.000$/ }).getByRole('slider').fill('37');
    await page.locator('div').filter({ hasText: /^green37\.00$/ }).getByRole('slider').fill('255');

    page.once('dialog', dialog => {
      console.log(`Dialog message: ${dialog.message()}`);
      dialog.accept("Aqua").catch(() => {});
    });
    await page.locator('details').filter({ hasText: 'Cue Channel ValuesNormal' }).getByRole('combobox').selectOption('');

    await page.locator('div').filter({ hasText: /^blue255\.0$/ }).getByRole('slider').fill('234');
    await page.locator('div').filter({ hasText: /^blue234\.0$/ }).getByRole('slider').fill('0');
    await page.locator('div').filter({ hasText: /^green255\.0$/ }).getByRole('slider').fill('0');
    await page.getByRole('button', { name: 'Presets', exact: true }).click();
    await page.getByRole('button', { name: 'aqua' }).click();
    await expect(page.locator('div').filter({ hasText: /^blue255\.0$/ }).getByRole('slider')).toHaveValue('255');
    await expect(page.locator('div').filter({ hasText: /^green255\.0$/ }).getByRole('slider')).toHaveValue('255');
    await page.getByRole('button', { name: '󰏘 Presets' }).click();
    await page.getByText('Values', { exact: true }).click();
    await page.getByLabel('dim').click();
    await page.getByLabel('dim').fill('50');
    await page.getByText('PresetsCloseHelp A preset is').click();
    await page.getByRole('button', { name: '󰅖 Close' }).click();
    await page.getByRole('button', { name: 'Presets', exact: true }).click();
    await page.getByRole('button', { name: 'aqua' }).nth(1).click();
    await expect(page.locator('div').filter({ hasText: /^dim50\.00$/ }).getByRole('slider')).toHaveValue('50');
    await page.getByRole('link', { name: '󰢻 Settings' }).click();
    await page.getByRole('button', { name: 'Universes' }).click();
    await page.getByRole('row', { name: 'test More than one device' }).getByRole('link').click();
    await expect(page.locator('section')).toContainText('50.0');
    await expect(page.locator('section')).toContainText('255.0');
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: '󰆴 Delete' }).click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('test_presets');
    await page.getByRole('button', { name: 'Submit' }).click();


    await logout(page);
});