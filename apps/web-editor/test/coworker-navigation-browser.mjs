/** Use the public navigation controls, including drawers/disclosures. */
export async function navigateWorkspace(page, label) {
  const target = page.getByRole("button", { name: label, exact: true });
  if (!await target.isVisible()) {
    const conversationMenu = page.getByRole("button", { name: "Open navigation", exact: true });
    const sectionMenu = page.getByRole("button", { name: "Open workspace navigation", exact: true });
    if (await conversationMenu.isVisible()) await conversationMenu.click();
    else if (await sectionMenu.isVisible()) await sectionMenu.click();
  }
  if (!await target.isVisible()) {
    const disclosure = page.getByText("More tools", { exact: true });
    await disclosure.click();
  }
  await target.click();
  if (label === "Plugins") {
    const management = page.locator("details.rukh-plugin-management");
    await management.waitFor();
    if (!await management.evaluate(element => element.open)) await management.locator("summary").click();
  }
}
