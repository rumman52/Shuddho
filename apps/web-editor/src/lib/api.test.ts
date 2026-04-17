import assert from "node:assert/strict";
import test from "node:test";

import { deriveApiConfiguration } from "./api";

test("deriveApiConfiguration allows localhost only for local browser origins", () => {
  const localConfig = deriveApiConfiguration({
    browserHostname: "localhost",
    configuredBaseUrl: null,
    storedBaseUrl: null,
  });
  const deployedConfig = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "http://127.0.0.1:8000",
    storedBaseUrl: null,
  });

  assert.equal(localConfig.backendAllowed, true);
  assert.equal(localConfig.apiBaseUrl, "http://127.0.0.1:8000");
  assert.equal(deployedConfig.backendAllowed, false);
  assert.match(deployedConfig.hardWarning ?? "", /VITE_API_BASE_URL/);
});

test("deriveApiConfiguration accepts a public backend URL for deployed origins", () => {
  const config = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "https://api.shuddho.example",
    storedBaseUrl: null,
  });

  assert.equal(config.backendAllowed, true);
  assert.equal(config.apiBaseUrl, "https://api.shuddho.example");
  assert.equal(config.hardWarning, null);
});
