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
  const taskC = "E2E Task C: Create a concise project document about the third milestone.";
  const steering = "Prioritize the Bangla summary and keep the document concise.";

  await postJson(page, "/enable-v3");
  try {
    // The visible "+" is decorative; aria-label defines the accessible name.
    const newChatButton = page.getByRole("button", { name: "New chat", exact: true });
    await newChatButton.waitFor();
    assert.equal((await newChatButton.innerText()).trim(), "+ New chat");
    await newChatButton.click();
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

    // A third task demonstrates bounded, configurable concurrency rather than
    // accidentally coupling every run to one conversation-wide execution slot.
    await composer.fill(taskC);
    await page.locator(".rukh-design-send").click();
    await page.getByText(taskC, { exact: true }).waitFor();
    await page.getByRole("button", { name: "Start task", exact: true }).click();
    await waitFor(async () => {
      const calls = await getJson(page, "/planner-calls");
      return calls.calls.filter(call => call.goal === taskA || call.goal === taskB || call.goal === taskC).length === 3;
    }, "three independent in-flight Agent runs");
    // Let the conversation activity poll refresh event_sequence before optimistic steering.
    await page.waitForTimeout(5500);
    await waitFor(async () =>
      (await page.getByRole("status").filter({ hasText: /Planning|Working/ }).count()) === 3,
      "three visible active Agent progress states"
    );

    const steerButtons = page.getByRole("button", { name: "Steer Agent task", exact: true });
    await waitFor(async () => (await steerButtons.count()) === 3, "three per-message steering controls");
    await steerButtons.nth(0).click();
    await page.getByLabel("Instruction for Agent", { exact: true }).fill(steering);
    await page.getByRole("button", { name: "Send instruction", exact: true }).click();

    // Cancel only Task B while both model decisions are deliberately held.
    const cancelButtons = page.getByRole("button", { name: "Cancel Agent work", exact: true });
    await waitFor(async () => (await cancelButtons.count()) === 3, "three independent cancellation controls");
    await cancelButtons.nth(1).click();

    runs = await waitFor(async () => {
      const snapshot = await getJson(page, "/runs");
      const a = snapshot.runs.find(run => run.goal === taskA);
      const b = snapshot.runs.find(run => run.goal === taskB);
      const c = snapshot.runs.find(run => run.goal === taskC);
      return a?.steering_revision === 1 && b?.state === "cancelled" && c && c.state !== "cancelled" ? snapshot : null;
    }, "revision-checked steering and individual cancellation");
    assert.equal(runs.runs.find(run => run.goal === taskA).state === "cancelled", false);
    assert.equal(runs.runs.find(run => run.goal === taskC).state === "cancelled", false);

    // Refresh must restore the same conversation, active run and terminal run.
    await page.reload();
    await composer.waitFor();
    await page.getByText(taskA, { exact: true }).waitFor();
    const taskBMessage = page.getByText(taskB, { exact: true });
    await taskBMessage.waitFor();
    await page.getByText(taskC, { exact: true }).waitFor();
    // Completed/cancelled history is intentionally lazy-loaded after refresh.
    await taskBMessage.locator("xpath=ancestor::li")
      .getByRole("button", { name: "Show coworker progress", exact: true }).click();
    await page.getByText("Cancelled", { exact: true }).waitFor();
    await waitFor(async () => (await page.getByRole("button", { name: "Cancel Agent work", exact: true }).count()) === 2,
      "the two uncancelled tasks retaining their cancel controls");

    await postJson(page, "/release-planner");
    runs = await waitFor(async () => {
      const snapshot = await getJson(page, "/runs");
      const a = snapshot.runs.find(run => run.goal === taskA);
      const b = snapshot.runs.find(run => run.goal === taskB);
      const c = snapshot.runs.find(run => run.goal === taskC);
      return a?.state === "completed" && b?.state === "cancelled" && c?.state === "completed" ? snapshot : null;
    }, "Tasks A and C completing without reviving cancelled Task B", 30000);

    const completedA = runs.runs.find(run => run.goal === taskA);
    const cancelledB = runs.runs.find(run => run.goal === taskB);
    const completedC = runs.runs.find(run => run.goal === taskC);
    assert.equal(completedA.decision_count, 2);
    assert.equal(completedA.tool_invocation_count, 1);
    assert.equal(completedA.tool_receipts.length, 1);
    assert.ok(completedA.tool_receipts[0].resource_id);
    assert.equal(cancelledB.decision_count, 0);
    assert.equal(cancelledB.tool_invocation_count, 0);
    assert.equal(cancelledB.tool_receipts.length, 0);
    assert.equal(completedC.decision_count, 2);
    assert.equal(completedC.tool_invocation_count, 1);
    assert.equal(completedC.tool_receipts.length, 1);
    assert.ok(completedC.tool_receipts[0].resource_id);
    assert.equal(completedA.steering_instructions.at(-1).instruction, steering);
    assert.equal(completedC.steering_revision, 0);

    const calls = (await getJson(page, "/planner-calls")).calls;
    const callsA = calls.filter(call => call.goal === taskA);
    const callsB = calls.filter(call => call.goal === taskB);
    const callsC = calls.filter(call => call.goal === taskC);
    assert.ok(callsA.some(call => call.steering_revision === 0));
    assert.ok(callsA.some(call =>
      call.steering_revision === 1
      && call.steering_instructions.some(item => item.instruction === steering)
      && call.objective?.includes("Bangla")
    ), "the new instruction must affect the next planning decision");
    assert.equal(callsB.length, 1, "the cancelled task must not re-enter model planning");
    assert.ok(callsC.some(call => call.observation_count === 1), "Task C must complete from its own verified observation");
  } finally {
    // Always release held fixture inference so a failed assertion cannot strand a worker.
    await postJson(page, "/release-planner").catch(() => undefined);
    await postJson(page, "/disable-v3").catch(() => undefined);
  }
}
