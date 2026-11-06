/** Use the public navigation controls, including drawers/disclosures. */
export async function navigateWorkspace(page, label) {
  const buttonTarget = page.getByRole("button", { name: label, exact: true }).first();
  const linkTarget = page.getByRole("link", { name: label, exact: true }).first();
  const findVisibleTarget = async () => {
    if (await buttonTarget.isVisible()) return buttonTarget;
    if (await linkTarget.isVisible()) return linkTarget;
    return null;
  };

  if (!await findVisibleTarget()) {
    const conversationMenu = page.getByRole("button", { name: "Open navigation", exact: true });
    const sectionMenu = page.getByRole("button", { name: "Open workspace navigation", exact: true });
    if (await conversationMenu.isVisible()) await conversationMenu.click();
    else if (await sectionMenu.isVisible()) await sectionMenu.click();
  }

  let target = await findVisibleTarget();
  if (!target) {
    const disclosure = page.getByText("More tools", { exact: true });
    if (await disclosure.isVisible()) await disclosure.click();
    target = await findVisibleTarget();
  }
  if (!target) throw new Error(`Workspace navigation target "${label}" is not visible.`);

  await target.click();
  if (label === "Plugins") {
    const management = page.locator("details.rukh-plugin-management");
    await management.waitFor();
    if (!await management.evaluate(element => element.open)) await management.locator("summary").click();
  }
}
