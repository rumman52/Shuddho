import assert from "node:assert/strict";
import { join } from "node:path";

export async function verifyAgentProposals(page, folder) {
  await page.getByRole("button", { name: "Email & calendar", exact: true }).click();
  const actions = page.getByRole("region", { name: "Email and calendar actions", exact: true });
  if (await actions.getByRole("button", { name: "Connect Gmail", exact: true }).count()) {
    await actions.getByRole("button", { name: "Connect Gmail", exact: true }).click();
    await actions.getByRole("button", { name: "Disconnect Gmail", exact: true }).waitFor();
  }

  const before = await (await page.request.get("http://127.0.0.1:8000/fixture/actions/counts")).json();
  await page.getByRole("button", { name: "Agent", exact: true }).click();
  const agent = page.getByRole("region", { name: "Agent workspace", exact: true });
  await agent.getByLabel("Goal").fill(
    "Draft a project update and suggest an email to recipient@example.org with subject Agent project update and body The project is ready for review."
  );
  await agent.getByRole("button", { name: "Start bounded Agent run", exact: true }).click();
  await agent.getByRole("region", { name: "Agent action proposals", exact: true }).waitFor({ timeout: 30000 });
  await agent.getByText("Nothing here is executable yet.", { exact: true }).waitFor();
  await agent.getByText("Agent project update", { exact: true }).waitFor();
  assert.deepEqual(
    await (await page.request.get("http://127.0.0.1:8000/fixture/actions/counts")).json(),
    before,
  );

  await page.screenshot({ path: join(folder, "screenshots/agent-inert-proposal.png"), fullPage: true });
  const account = agent.getByLabel("Account for Agent project update", { exact: true });
  assert.equal(await account.inputValue(), "");
  assert.equal(await agent.getByRole("button", { name: "Promote exact proposal", exact: true }).isDisabled(), true);
  await account.selectOption({ index: 1 });
  await agent.getByRole("button", { name: "Promote exact proposal", exact: true }).click();

  const review = page.getByRole("region", { name: "Action review", exact: true });
  await review.getByRole("heading", { name: "Needs your approval", exact: true }).waitFor();
  assert.equal(await review.getByRole("button", { name: "Approve & send email", exact: true }).isDisabled(), true);
  assert.deepEqual(
    await (await page.request.get("http://127.0.0.1:8000/fixture/actions/counts")).json(),
    before,
  );
  await page.screenshot({ path: join(folder, "screenshots/agent-promoted-preview.png"), fullPage: true });

  await page.getByRole("region", { name: "Email and calendar actions", exact: true })
    .getByRole("button", { name: "Cancel action", exact: true }).click();
  assert.deepEqual(
    await (await page.request.get("http://127.0.0.1:8000/fixture/actions/counts")).json(),
    before,
  );
}
