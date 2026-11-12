/** Navigate through real public controls on both desktop and mobile. */
export async function navigateWorkspace(page, label) {
  const buttonTarget = page.getByRole("button", { name: label, exact: true }).first();
  const linkTarget = page.getByRole("link", { name: label, exact: true }).first();
  const findVisibleTarget = async () => {
    if (await buttonTarget.isVisible()) return buttonTarget;
    if (await linkTarget.isVisible()) return linkTarget;
    return null;
  };

  // A reload can finish before the authenticated React workspace and its
  // navigation are mounted. Never mistake that transient state for a missing
  // route, or skip the actual menu/disclosure navigation assertion.
  await page.locator("#rukh-conversation-list, #rukh-cw-sidebar").first()
    .waitFor({ state: "attached", timeout: 15000 });

  if (!await findVisibleTarget()) {
    const conversationMenu = page.getByRole("button", { name: "Open navigation", exact: true });
    const sectionMenu = page.getByRole("button", { name: "Open workspace navigation", exact: true });
    if (await conversationMenu.isVisible()) {
      await conversationMenu.click();
      await page.locator("#rukh-conversation-list.rukh-mobile-panel-open")
        .waitFor({ state: "visible" });
    } else if (await sectionMenu.isVisible()) {
      await sectionMenu.click();
      await page.locator("#rukh-cw-sidebar.rukh-cw-sidebar-open")
        .waitFor({ state: "visible" });
    }
  }

  let target = await findVisibleTarget();
  if (!target) {
    // "Files & drafts" and several other workspaces are intentionally inside
    // a native details disclosure. Wait for the responsive drawer to become
    // visible before asking the user-visible summary to expand it.
    const disclosure = page.locator("details.rukh-design-more-tools:visible").first();
    await disclosure.locator("summary").waitFor({ state: "visible" });
    if (!await disclosure.evaluate(element => element.open)) {
      await disclosure.locator("summary").click();
    }
    await disclosure.locator("nav").waitFor({ state: "visible" });
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
