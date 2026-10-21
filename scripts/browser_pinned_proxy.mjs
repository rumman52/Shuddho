// The worker's real localhost HTTPS CONNECT boundary. The only injected
// dependencies are trusted worker-owned network authorization and TCP dialing;
// production never accepts these values from browser content or user input.
import http from "node:http";
import net, { isIP } from "node:net";
import { performance } from "node:perf_hooks";

// A broker-validated DNS response is not a substitute for worker-side network
// isolation. The proxy must reject reserved/private addresses before dialing,
// even if a stale or malformed network-check response accidentally returned one.
// Keep this denylist conservative: a false negative blocks browsing; allowing
// private-network egress would violate CW-09's security boundary.
const reservedIPv4 = new net.BlockList();
for (const [network, prefix] of [
  ["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10],
  ["127.0.0.0", 8], ["169.254.0.0", 16], ["172.16.0.0", 12],
  ["192.0.0.0", 24], ["192.0.2.0", 24], ["192.88.99.0", 24],
  ["192.168.0.0", 16], ["198.18.0.0", 15],
  ["198.51.100.0", 24], ["203.0.113.0", 24],
  ["224.0.0.0", 4], ["240.0.0.0", 4],
]) reservedIPv4.addSubnet(network, prefix, "ipv4");

const globalIPv6 = new net.BlockList();
globalIPv6.addSubnet("2000::", 3, "ipv6");
const reservedIPv6 = new net.BlockList();
for (const [network, prefix] of [
  ["2001::", 32],       // Teredo (may tunnel to private IPv4)
  ["2001:2::", 48],     // benchmarking
  ["2001:10::", 28],    // ORCHID
  ["2001:db8::", 32],   // documentation
  ["2002::", 16],       // 6to4 (may tunnel to private IPv4)
  ["3fff::", 20],       // documentation
]) reservedIPv6.addSubnet(network, prefix, "ipv6");

function isPublicPinnedIp(address) {
  const family = isIP(address);
  if (family === 4) return !reservedIPv4.check(address, "ipv4");
  if (family === 6) {
    // Excludes IPv4-mapped IPv6, loopback, link-local, ULA, multicast,
    // IPv4 translation prefixes and other non-global IPv6 addresses.
    return globalIPv6.check(address, "ipv6")
      && !reservedIPv6.check(address, "ipv6");
  }
  return false;
}

import { browserProxyClaimValid, parseConnectAuthority } from "./browser_worker_policy.mjs";


function networkCheckMatchesTarget(target, checked) {
  const normalizeHost = (value) => {
    if (typeof value !== "string") return "";
    const host = value.toLowerCase();
    return host.endsWith(".") ? host.slice(0, -1) : host;
  };
  const addresses = checked?.resolved_ips;
  return (
    normalizeHost(checked?.hostname) === normalizeHost(target?.host)
    && Array.isArray(addresses)
    && addresses.length > 0
    && addresses.length <= 16
    && addresses.every((address) => typeof address === "string" && isPublicPinnedIp(address))
  );
}

export async function createPinnedProxy(state, { validateHost, dial = net.connect, navigationTimeoutMs } = {}) {
  if (typeof validateHost !== "function" || typeof dial !== "function" || !Number.isFinite(navigationTimeoutMs) || navigationTimeoutMs <= 0) {
    throw new Error("invalid_proxy_dependencies");
  }
  const sockets = new Set();
  const server = http.createServer((_req, res) => {
    res.writeHead(403, { "Content-Type": "text/plain", "Connection": "close" });
    res.end("HTTPS CONNECT only");
  });

  server.on("connect", async (req, clientSocket, head) => {
    // Register pending CONNECT sockets before the awaited DNS/broker check.
    // pause()/destroy() must terminate even sockets which have not yet
    // authorized an upstream connection; otherwise they escape cleanup.
    sockets.add(clientSocket);
    let upstream;
    // Socket inactivity timeouts start only after authorization. Bound the
    // entire handshake, including DNS/broker wait, with one independent timer.
    // Destroying the client also makes a late authorization fail the claim check.
    const handshakeExpiresAt = performance.now() + navigationTimeoutMs;
    const handshakeDeadline = setTimeout(() => {
      clientSocket.destroy();
      upstream?.destroy();
    }, navigationTimeoutMs);
    clientSocket.once("close", () => {
      clearTimeout(handshakeDeadline);
      sockets.delete(clientSocket);
      upstream?.destroy();
    });
    let target;
    try {
      const claim = {
        commandId: state.commandId,
        epoch: state.proxyClaimEpoch,
        evidence: state.evidence,
      };
      if (!browserProxyClaimValid(state, claim)) throw new Error("browser_command_not_active");
      target = parseConnectAuthority(req.url || "");
      // Never let an old async DNS result authorize a CONNECT after a
      // cancel/pause/claim replacement. Bind the request to the captured ID.
      const checked = await validateHost(claim.commandId, target.host);
      // A malformed or mismatched broker result must never pass undefined or
      // non-IP input to net.connect (whose default host can be localhost).
      if (!networkCheckMatchesTarget(target, checked)) {
        throw new Error("browser_network_check_invalid");
      }
      // The client may disconnect while DNS/API authorization is suspended.
      // Refuse any outbound TCP dial after that disconnect.
      if (!browserProxyClaimValid(state, claim) || clientSocket.destroyed || performance.now() >= handshakeExpiresAt) {
        throw new Error("browser_claim_expired");
      }
      state.evidence[checked.hostname] = checked.resolved_ips;
      const pinnedIp = checked.resolved_ips[0];
      upstream = dial({ host: pinnedIp, port: 443 });
      sockets.add(upstream);
      upstream.setTimeout(navigationTimeoutMs);

      upstream.once("connect", () => {
        // Revocation can also occur while the TCP connection is pending.
        // Never acknowledge the CONNECT or attach pipes for stale claims.
        if (!browserProxyClaimValid(state, claim) || clientSocket.destroyed || performance.now() >= handshakeExpiresAt) {
          upstream.destroy();
          clientSocket.destroy();
          return;
        }
        clearTimeout(handshakeDeadline);
        clientSocket.write("HTTP/1.1 200 Connection Established\r\nProxy-Agent: shuddho-browser-worker\r\n\r\n");
        if (head?.length) upstream.write(head);
        clientSocket.pipe(upstream);
        upstream.pipe(clientSocket);
      });
      upstream.once("timeout", () => upstream.destroy(new Error("upstream_timeout")));
      upstream.once("close", () => sockets.delete(upstream));
      upstream.once("error", () => clientSocket.destroy());
      clientSocket.once("error", () => upstream.destroy());
    } catch {
      clearTimeout(handshakeDeadline);
      if (!clientSocket.destroyed) {
        clientSocket.write("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
      }
      clientSocket.destroy();
    }
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("proxy_bind_failed");
  function closeSockets() {
    for (const socket of sockets) socket.destroy();
    sockets.clear();
  }
  return {
    server,
    url: `http://127.0.0.1:${address.port}`,
    setCommand(commandId, evidence) {
      state.proxyClaimEpoch += 1;
      state.commandId = commandId;
      state.evidence = evidence;
    },
    pause() {
      state.proxyClaimEpoch += 1;
      state.commandId = null;
      state.evidence = null;
      closeSockets();
    },
    destroy() {
      state.proxyClaimEpoch += 1;
      state.commandId = null;
      state.evidence = null;
      closeSockets();
    },
  };
}

