import assert from "node:assert/strict";

const fixture = "http://127.0.0.1:8000/fixture/agent";

async function getJson(page, path) {
  const response = await page.request.get(fixture + path);
  assert.equal(response.ok(), true, `Fixture GET ${path} failed: ${response.status()}`);
  return response.json();
}

async function postJson(page, path) {
  const response = await page.request.post(fixture + path);
  assert.equal(response.ok(), true, `Fixture POST ${path} failed: ${response.status()}`);
  return response.json();
}

async function waitFor(check, description, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastValue;
  while (Date.now() < deadline) {
    lastValue = await check();
    if (lastValue) return lastValue;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for ${description}. Last value: ${JSON.stringify(lastValue)}`);
}

export async function verifyConversationAgentContinuity(page) {
  const taskA = "E2E Task A: Create a concise project document about the first milestone.";
  const taskB = "E2E Task B: Create a concise project document about the second milestone.";
  const steering = "Prioritize the Bangla summary and keep the document concise.";

  await postJson(page, "/enable-v3");
  try {
    await page.getByRole("button", { name: "+ New chat", exact: true }).click();
    const composer = page.locator("#cw-conversation-message");
    await composer.waitFor();
    await composer.fill(taskA);
    await page.locator(".rukh-design-send").click();
    await page.getByText(taskA, { exact: true }).waitFor();
    await page.getByRole("button", { name: "Start task", exact: true }).waitFor();

    // Saving an ordinary message is not authorization to launch Agent work.
    let runs = await getJson(page, "/runs");
    assert.equal(runs.runs.filter(run => run.goal === taskA).length, 0);

    await page.getByRole("button", { name: "Start task", exact: true }).click();
    await page.getByRole("button", { name: "Steer Agent task", exact: true }).first().waitFor();
    await waitFor(async () => {
      const calls = await getJson(page, "/planner-calls");
      return calls.calls.some(call => call.goal === taskA);
    }, "the first real Temporal-backed planner call");

    // A second task can be admitted while the first task remains in flight.
    await composer.fill(taskB);
    await page.locator(".rukh-design-send").click();
    await page.getByText(taskB, { exact: true }).waitFor();
    await page.getByRole("button", { name: "Start task", exact: true }).click();
    await waitFor(async () => {
      const calls = await getJson(page, "/planner-calls");
      return calls.calls.filter(call => call.goal === taskA || call.goal === taskB).length === 2;
    }, "two independent in-flight Agent runs");

    const steerButtons = page.getByRole("button", { name: "Steer Agent task", exact: true });
    await waitFor(async () => (await steerButtons.count()) === 2, "two per-message steering controls");
    await steerButtons.nth(0).click();
    await page.getByLabel("Instruction for Agent", { exact: true }).fill(steering);
    await page.getByRole("button", { name: "Send instruction", exact: true }).click();

    // Cancel only Task B while both model decisions are deliberately held.
    const cancelButtons = page.getByRole("button", { name: "Cancel Agent work", exact: true });
    await waitFor(async () => (await cancelButtons.count()) === 2, "two independent cancellation controls");
    await cancelButtons.nth(1).click();

    runs = await waitFor(async () => {
      const snapshot = await getJson(page, "/runs");
      const a = snapshot.runs.find(run => run.goal === taskA);
      const b = snapshot.runs.find(run => run.goal === taskB);
      return a?.steering_revision === 1 && b?.state === "cancelled" ? snapshot : null;
    }, "revision-checked steering and individual cancellation");
    assert.equal(runs.runs.find(run => run.goal === taskA).state === "cancelled", false);

    // Refresh must restore the same conversation, active run and terminal run.
    await page.reload();
    await composer.waitFor();
    await page.getByText(taskA, { exact: true }).waitFor();
    await page.getByText(taskB, { exact: true }).waitFor();
    await page.getByText("Cancelled", { exact: true }).waitFor();
    await waitFor(async () => (await page.getByRole("button", { name: "Cancel Agent work", exact: true }).count()) === 1,
      "only the uncancelled task retaining its cancel control");

    await postJson(page, "/release-planner");
    runs = await waitFor(async () => {
      const snapshot = await getJson(page, "/runs");
      const a = snapshot.runs.find(run => run.goal === taskA);
      const b = snapshot.runs.find(run => run.goal === taskB);
      return a?.state === "completed" && b?.state === "cancelled" ? snapshot : null;
    }, "Task A completing without reviving cancelled Task B", 30000);

    const completedA = runs.runs.find(run => run.goal === taskA);
    const cancelledB = runs.runs.find(run => run.goal === taskB);
    assert.equal(completedA.tool_invocation_count, 1);
    assert.equal(cancelledB.tool_invocation_count, 0);
    assert.equal(completedA.steering_instructions.at(-1).instruction, steering);

    const calls = (await getJson(page, "/planner-calls")).calls;
    const callsA = calls.filter(call => call.goal === taskA);
    const callsB = calls.filter(call => call.goal === taskB);
    assert.ok(callsA.some(call => call.steering_revision === 0));
    assert.ok(callsA.some(call =>
      call.steering_revision === 1
      && call.steering_instructions.some(item => item.instruction === steering)
    ));
    assert.equal(callsB.length, 1, "the cancelled task must not re-enter model planning");
  } finally {
    // Always release held fixture inference so a failed assertion cannot strand a worker.
    await postJson(page, "/release-planner").catch(() => undefined);
    await postJson(page, "/disable-v3").catch(() => undefined);
  }
}
