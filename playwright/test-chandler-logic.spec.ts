import { test, expect } from "@playwright/test";
import {
  sleep,
  login,
  chandlerBoardTemplate,
  deleteModule,
  waitForTasks,

} from "./util";

/*/
Create a module, make a chandler board, test very simple logic,
make sure tag output features work.
*/
test("test", async ({ page }) => {
  test.setTimeout(2_400_000);

  await login(page);
  const module = "PlaywrightChandlerLogicTestModule";

  await chandlerBoardTemplate(page, module);
  await waitForTasks(page);
  await sleep(200);

  await page.getByTestId('cue-logic-button').click();
  await page.getByLabel('Inherit rules from Inherited').click();
  await page.getByLabel('Inherit rules from Inherited').fill('c2');
  await page.getByText('default LogicClose Automation').click();
  await page.getByRole('button', { name: 'Add Rule' }).click();
  await page.getByTestId('rule-trigger').click();
  await page.getByLabel('Run on(type to search)').dblclick();
  await page.getByLabel('Run on(type to search)').press('ControlOrMeta+a');
  await page.getByLabel('Run on(type to search)').fill('rule1');
  await page.locator('#blockInspectorEvent').getByRole('button', { name: '󰅖 Close' }).click();
  await page.getByRole('button', { name: 'Add Action' }).click();
  await page.getByRole('button', { name: 'pass' }).click();
  await page.locator('#blockInspectorCommand').getByRole('button', { name: '󰅖 Close' }).click();
  await page.getByRole('button', { name: 'Add Rule' }).click();
  await page.getByRole('button', { name: 'On cue.enter' }).click();
  await page.locator('#blockInspectorEvent div').filter({ hasText: 'Run when script loadsWhen' }).click();
  await page.getByLabel('Run on(type to search)').press('ControlOrMeta+a');
  await page.getByLabel('Run on(type to search)').fill('rule2');
  await page.getByText('Event Trigger. Runs the').click();
  await page.locator('#blockInspectorEvent').getByRole('button', { name: '󰅖 Close' }).click();
  
  
  await page.getByRole('button', { name: 'goto' }).nth(1).click();
  await page.getByRole('button', { name: 'Add Action' }).nth(1).click();
  await page.getByRole('button', { name: 'pass' }).nth(1).click();
  await page.locator('#blockInspectorCommand').getByRole('combobox').click();
  await page.locator('#blockInspectorCommand').getByRole('combobox').fill('set');

  await waitForTasks(page);
  await page.locator('div').filter({ hasText: /^Output of the previous action$/ }).getByRole('combobox').fill('foo');
  await page.locator('div').filter({ hasText: /^Output of the previous action$/ }).getByRole('combobox').blur();

  await waitForTasks(page);
  await page.locator('#blockInspectorCommand').getByRole('combobox').nth(2).fill('45');
  await page.locator('#blockInspectorCommand').getByRole('combobox').nth(2).blur();

  await waitForTasks(page);
  await page.locator('#blockInspectorCommand').getByRole('button', { name: '󰅖 Close' }).click();


  await waitForTasks(page);
  await sleep(200);
  
  await page.getByRole('button', { name: 'goto' }).nth(1).click();
  await page.getByRole('button', { name: 'Move Forward' }).click();
  await page.locator('#blockInspectorCommand').getByRole('button', { name: '󰅖 Close' }).click();

  await waitForTasks(page);
  await sleep(200);


  await page.getByRole('button', { name: 'Move down' }).first().click();
 
 
   // We reversed rule2 and rule1
  await expect(page.getByTestId("rule-box-row").last().getByTestId("rule-trigger")).toContainText("rule1");
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-trigger")).toContainText("rule2");

// The first rule is named rule2 and has set foo 45 then a blank goto
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").first()).toContainText("set");
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").first()).toContainText("foo");
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").first()).toContainText("45");

  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").last()).toContainText("goto");

  // Second has goto then the default pass rule
  await expect(page.getByTestId("rule-box-row").last().getByTestId("rule-command").first()).toContainText("goto");
  await expect(page.getByTestId("rule-box-row").last().getByTestId("rule-command").last()).toContainText("pass");


  await waitForTasks(page);
  await sleep(200);


  await page.getByTestId('close-logic').click();
  await page.getByTestId('close-group').click();

  await waitForTasks(page);
  await sleep(800);


  await page.getByRole('link', { name: '󰀻 Apps' }).click();
  await page.getByTestId('extras-button-playwrightchandlerlogictestmodule_board1').click();
  await page.getByRole('link', { name: 'Editor' }).click();
  await page.getByRole('button', { name: 'tst1' }).click();
  await page.getByTestId('cue-logic-button').click();


  // We reversed rule2 and rule1
  await expect(page.getByTestId("rule-box-row").last().getByTestId("rule-trigger")).toContainText("rule1");
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-trigger")).toContainText("rule2");

// The first rule is named rule2 and has set foo 45 then a blank goto
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").first()).toContainText("set");
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").first()).toContainText("foo");
  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").first()).toContainText("45");

  await expect(page.getByTestId("rule-box-row").first().getByTestId("rule-command").last()).toContainText("goto");

  // Second has goto then the default pass rule
  await expect(page.getByTestId("rule-box-row").last().getByTestId("rule-command").first()).toContainText("goto");
  await expect(page.getByTestId("rule-box-row").last().getByTestId("rule-command").last()).toContainText("pass");


  await deleteModule(page, module);
});
