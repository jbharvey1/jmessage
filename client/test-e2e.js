/**
 * JMessage End-to-End Protocol Test
 * Tests WebSocket relay from a remote machine (sandbox VM).
 */

const WebSocket = require("ws");

const fs = require("fs");
const path = require("path");
const config = JSON.parse(fs.readFileSync(path.join(__dirname, "config.json"), "utf-8"));
const WS_URL = config.relay_url;
const AUTH_TOKEN = config.auth_token;

// mTLS certs
const certsDir = path.join(__dirname, "certs");
const tlsOptions = {};
if (fs.existsSync(path.join(certsDir, "client.pem"))) {
  tlsOptions.cert = fs.readFileSync(path.join(certsDir, "client.pem"));
  tlsOptions.key = fs.readFileSync(path.join(certsDir, "client.key"));
  tlsOptions.ca = fs.readFileSync(path.join(certsDir, "ca.pem"));
  tlsOptions.rejectUnauthorized = false;
}

let passed = 0;
let failed = 0;

function assert(condition, name) {
  if (condition) {
    console.log(`  PASS: ${name}`);
    passed++;
  } else {
    console.log(`  FAIL: ${name}`);
    failed++;
  }
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function runTests() {
  console.log("\n=== JMessage E2E Protocol Tests ===\n");

  // Test 1: Connection and Auth
  console.log("[1] Connection & Authentication");
  const ws = new WebSocket(WS_URL, { ...tlsOptions });

  await new Promise((resolve, reject) => {
    ws.on("open", resolve);
    ws.on("error", reject);
    setTimeout(() => reject(new Error("Connection timeout")), 5000);
  });
  assert(ws.readyState === WebSocket.OPEN, "WebSocket connects to relay");

  // Send auth
  ws.send(JSON.stringify({ type: "auth", token: AUTH_TOKEN }));

  // Should receive conversations
  const authResp = await new Promise((resolve) => {
    ws.on("message", (data) => resolve(JSON.parse(data.toString())));
    setTimeout(() => resolve(null), 5000);
  });
  assert(authResp !== null, "Receives response after auth");
  assert(authResp.type === "conversations", "First response is conversations list");
  assert(Array.isArray(authResp.data), "Conversations data is array");
  assert(authResp.data.length > 0, "Has at least one conversation");
  console.log(`  (${authResp.data.length} conversations loaded)\n`);

  // Test 2: Conversation structure
  console.log("[2] Conversation Data Structure");
  const convo = authResp.data[0];
  assert(typeof convo.chat_id === "string", "chat_id is string");
  assert("display_name" in convo, "has display_name field");
  assert("service" in convo, "has service field");
  assert("last_message" in convo, "has last_message field");
  assert("last_date" in convo, "has last_date field");
  console.log(`  (first chat: ${convo.chat_id})\n`);

  // Test 3: Fetch chat history
  console.log("[3] Chat History");
  const historyPromise = new Promise((resolve) => {
    const handler = (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.type === "history") {
        ws.removeListener("message", handler);
        resolve(msg);
      }
    };
    ws.on("message", handler);
    setTimeout(() => resolve(null), 10000);
  });
  ws.send(
    JSON.stringify({
      type: "get_history",
      data: { chat_id: convo.chat_id, limit: 20 },
    })
  );
  const histResp = await historyPromise;
  assert(histResp !== null, "Receives history response");
  assert(histResp.type === "history", "Response type is history");
  assert(histResp.data.chat_id === convo.chat_id, "History is for requested chat");
  assert(Array.isArray(histResp.data.messages), "Messages is array");

  const msgs = histResp.data.messages;
  console.log(`  (${msgs.length} messages in history)\n`);

  // Test 4: Message structure
  console.log("[4] Message Data Structure");
  if (msgs.length > 0) {
    const msg = msgs[msgs.length - 1]; // most recent
    assert(typeof msg.id === "number", "id is number");
    assert(typeof msg.is_from_me === "boolean", "is_from_me is boolean");
    assert(typeof msg.service === "string", "service is string");
    assert(typeof msg.date === "string", "date is ISO string");
    assert(
      msg.service === "iMessage" || msg.service === "SMS",
      `service is iMessage or SMS (got: ${msg.service})`
    );
    // Verify no blank messages (tapbacks filtered)
    const blanks = msgs.filter((m) => !m.text && !m.has_attachments);
    assert(blanks.length === 0, `No blank messages in history (found ${blanks.length})`);
    console.log(`  (latest msg: "${(msg.text || "").substring(0, 40)}")\n`);
  } else {
    console.log("  SKIP: No messages to test structure\n");
  }

  // Test 5: Refresh conversations
  console.log("[5] Refresh Conversations");
  const refreshPromise = new Promise((resolve) => {
    const handler = (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.type === "conversations") {
        ws.removeListener("message", handler);
        resolve(msg);
      }
    };
    ws.on("message", handler);
    setTimeout(() => resolve(null), 5000);
  });
  ws.send(JSON.stringify({ type: "get_conversations" }));
  const refreshResp = await refreshPromise;
  assert(refreshResp !== null, "Can refresh conversations");
  assert(refreshResp.data.length === authResp.data.length, "Same conversation count on refresh");
  console.log("");

  // Test 6: Bad auth rejection
  console.log("[6] Bad Auth Rejection");
  const badWs = new WebSocket(WS_URL, { ...tlsOptions });
  await new Promise((resolve) => {
    badWs.on("open", resolve);
    setTimeout(resolve, 3000);
  });
  badWs.send(JSON.stringify({ type: "auth", token: "wrong-token" }));
  const badResp = await new Promise((resolve) => {
    badWs.on("message", (data) => resolve(JSON.parse(data.toString())));
    setTimeout(() => resolve(null), 3000);
  });
  assert(badResp !== null && badResp.type === "error", "Rejects bad auth token");
  await new Promise((resolve) => {
    badWs.on("close", resolve);
    setTimeout(resolve, 2000);
  });
  assert(
    badWs.readyState === WebSocket.CLOSED || badWs.readyState === WebSocket.CLOSING,
    "Closes connection after bad auth"
  );
  console.log("");

  // Test 7: Multiple chats history
  console.log("[7] Multiple Chat Histories");
  const chatIds = authResp.data.slice(0, 3).map((c) => c.chat_id);
  for (const cid of chatIds) {
    const hp = new Promise((resolve) => {
      const handler = (data) => {
        const msg = JSON.parse(data.toString());
        if (msg.type === "history" && msg.data.chat_id === cid) {
          ws.removeListener("message", handler);
          resolve(msg);
        }
      };
      ws.on("message", handler);
      setTimeout(() => resolve(null), 5000);
    });
    ws.send(
      JSON.stringify({ type: "get_history", data: { chat_id: cid, limit: 10 } })
    );
    const hr = await hp;
    assert(hr !== null, `History loads for ${cid.substring(0, 15)}`);
  }
  console.log("");

  // Cleanup
  ws.close();

  // Summary
  console.log("=== Results ===");
  console.log(`  Passed: ${passed}`);
  console.log(`  Failed: ${failed}`);
  console.log(`  Total:  ${passed + failed}`);
  console.log(failed === 0 ? "\n  ALL TESTS PASSED\n" : "\n  SOME TESTS FAILED\n");

  process.exit(failed > 0 ? 1 : 0);
}

runTests().catch((err) => {
  console.error("Test error:", err.message);
  process.exit(1);
});
