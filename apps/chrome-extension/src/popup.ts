const statusElement = document.getElementById("status");

async function checkBackend(): Promise<void> {
  if (!statusElement) {
    return;
  }

  try {
    const response = await fetch("http://127.0.0.1:8000/health");
    if (!response.ok) {
      throw new Error(String(response.status));
    }
    statusElement.textContent = "Backend reachable at http://127.0.0.1:8000";
  } catch {
    statusElement.textContent = "Backend not reachable. Start the FastAPI server first.";
  }
}

void checkBackend();

