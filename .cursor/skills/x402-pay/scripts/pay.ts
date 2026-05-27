/**
 * x402-pay — make a paid (x402 V1) HTTP request from any computer.
 *
 * Pure JavaScript with ZERO npm runtime dependencies: it uses only Node built-ins
 * (fetch, crypto, child_process, fs, Buffer). The only native component is the
 * globally-installed **OWS CLI** (`ows`), which does the signing inside its vault
 * — the private key never leaves `~/.ows/wallets/`.
 *
 * We implement the small x402 V1 "exact" (EIP-3009) client flow directly, so we
 * don't pull in viem / x402-fetch and their heavy native transitive deps
 * (keccak, bufferutil, ...). OWS handles all cryptography.
 *
 * Wallet selection (no .env needed): --wallet <name>, else the "## Crypto wallet"
 * section of the project's CLAUDE.md (wallet name + EVM address), else OWS_WALLET.
 *
 * Usage:
 *   npx tsx pay.ts --url <endpoint> [--method POST] [--body '<json>'] [--params '<json>'] [--wallet <name>]
 *
 * Requires the OWS CLI on PATH:  npm install -g @open-wallet-standard/core
 */
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";

type Args = { url?: string; method: string; body?: string; params?: string; wallet?: string };

/** network name -> EVM chain id (extend as needed). */
const NETWORK_CHAIN_ID: Record<string, number> = {
  "base-sepolia": 84532,
  base: 8453,
  ethereum: 1,
  "ethereum-sepolia": 11155111,
  "avalanche-fuji": 43113,
  "polygon-amoy": 80002,
};

function parseArgs(argv: string[]): Args {
  const out: Args = { method: "POST" };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case "--url": out.url = next(); break;
      case "--method": out.method = (next() ?? "POST").toUpperCase(); break;
      case "--body": out.body = next(); break;
      case "--params": out.params = next(); break;
      case "--wallet": out.wallet = next(); break;
      default: if (!a.startsWith("--") && !out.url) out.url = a;
    }
  }
  return out;
}

function fail(msg: string): never {
  console.error(`\n✗ ${msg}`);
  process.exit(1);
}

/** Run the `ows` CLI, returning trimmed stdout. Fails clearly if it's not installed. */
function ows(args: string[]): string {
  const res = spawnSync("ows", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  if (res.error) {
    if ((res.error as NodeJS.ErrnoException).code === "ENOENT") {
      fail("OWS CLI not found. Install it: npm install -g @open-wallet-standard/core");
    }
    fail(`failed to run ows: ${res.error.message}`);
  }
  if (res.status !== 0) fail(`ows ${args.slice(0, 2).join(" ")} failed: ${(res.stderr || res.stdout || "").trim()}`);
  return (res.stdout || "").trim();
}

/** Resolve a wallet's EVM (eip155) address from `ows wallet list`. */
function evmAddress(wallet: string): string {
  const text = "\n" + ows(["wallet", "list"]);
  for (const block of text.split(/\nID:\s/).slice(1)) {
    if (new RegExp(`\\nName:\\s+${wallet}(\\s|$)`, "m").test("\n" + block)) {
      const m = block.match(/eip155:[^\n]*?(0x[0-9a-fA-F]{40})/);
      if (m) return m[1];
    }
  }
  fail(`No EVM address for OWS wallet "${wallet}". Create it: ows wallet create --name ${wallet}`);
}

/** Walk up from cwd and this file's dir to locate the project's CLAUDE.md. */
function findClaudeMd(): string | undefined {
  for (const base of [process.cwd(), import.meta.dirname]) {
    let dir = base;
    while (dir) {
      const p = join(dir, "CLAUDE.md");
      if (existsSync(p)) return p;
      const parent = dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return undefined;
}

/** Read the wallet name + EVM address from CLAUDE.md's "## Crypto wallet" section. */
function walletFromClaudeMd(): { name?: string; address?: string } {
  const path = findClaudeMd();
  if (!path) return {};
  const text = readFileSync(path, "utf8");
  const section = text.match(/##\s+Crypto wallet[\s\S]*?(?=\n#{1,2}\s|$)/i)?.[0] ?? text;
  // Skip any markdown decoration (**, `, _) between the label and the name.
  const name = section.match(/wallet name:\s*[^A-Za-z0-9]*([A-Za-z0-9._-]+)/i)?.[1];
  const address = section.match(/0x[0-9a-fA-F]{40}/)?.[0];
  return { name, address };
}

/** Sign EIP-712 typed data in the OWS vault, returning a 0x r||s||v signature. */
function owsSignTypedData(wallet: string, chainId: number, typedData: object): string {
  const out = ows([
    "sign", "message", "--json",
    "--wallet", wallet, "--chain", `eip155:${chainId}`,
    "--message", "", "--typed-data", JSON.stringify(typedData),
  ]);
  const parsed = JSON.parse(out) as { signature: string; recovery_id?: number | null };
  let sig = parsed.signature.replace(/^0x/, "");
  if (sig.length === 128 && parsed.recovery_id != null) {
    const v = parsed.recovery_id >= 27 ? parsed.recovery_id : 27 + parsed.recovery_id;
    sig += v.toString(16).padStart(2, "0");
  }
  return "0x" + sig;
}

type Requirements = {
  scheme: string;
  network: string;
  maxAmountRequired: string;
  payTo: string;
  asset: string;
  maxTimeoutSeconds: number;
  extra?: { name?: string; version?: string };
};

/** Build the base64 X-PAYMENT header for the x402 V1 "exact" EVM scheme. */
function buildPaymentHeader(wallet: string, from: string, x402Version: number, req: Requirements): string {
  const chainId = NETWORK_CHAIN_ID[req.network];
  if (!chainId) fail(`Unknown x402 network "${req.network}". Add it to NETWORK_CHAIN_ID.`);
  if (req.scheme !== "exact") fail(`Unsupported x402 scheme "${req.scheme}" (only "exact" is implemented).`);

  const now = Math.floor(Date.now() / 1000);
  const authorization = {
    from,
    to: req.payTo,
    value: req.maxAmountRequired,
    validAfter: String(now - 600),                 // 10 min of clock skew
    validBefore: String(now + req.maxTimeoutSeconds),
    nonce: "0x" + randomBytes(32).toString("hex"),
  };

  // EIP-712 payload. EIP712Domain is defined explicitly (the OWS core requires
  // strict eth_signTypedData_v4 JSON that declares it).
  const typedData = {
    types: {
      EIP712Domain: [
        { name: "name", type: "string" },
        { name: "version", type: "string" },
        { name: "chainId", type: "uint256" },
        { name: "verifyingContract", type: "address" },
      ],
      TransferWithAuthorization: [
        { name: "from", type: "address" },
        { name: "to", type: "address" },
        { name: "value", type: "uint256" },
        { name: "validAfter", type: "uint256" },
        { name: "validBefore", type: "uint256" },
        { name: "nonce", type: "bytes32" },
      ],
    },
    domain: {
      name: req.extra?.name,
      version: req.extra?.version,
      chainId,
      verifyingContract: req.asset,
    },
    primaryType: "TransferWithAuthorization",
    message: authorization,
  };

  const signature = owsSignTypedData(wallet, chainId, typedData);
  const payment = { x402Version, scheme: req.scheme, network: req.network, payload: { signature, authorization } };
  return Buffer.from(JSON.stringify(payment)).toString("base64");
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) fail("Missing --url <x402-protected endpoint>.");

  // Resolve the wallet: --wallet override, else CLAUDE.md, else OWS_WALLET env.
  const fromClaude = walletFromClaudeMd();
  const wallet = args.wallet ?? fromClaude.name ?? process.env.OWS_WALLET;
  if (!wallet) {
    fail(
      "No wallet. Add a '## Crypto wallet' section with 'Wallet name: <name>' to " +
        "CLAUDE.md, or pass --wallet <name>.",
    );
  }
  // Use the saved address from CLAUDE.md when not overriding; otherwise derive it
  // from the vault via the CLI.
  const from = !args.wallet && fromClaude.address ? fromClaude.address : evmAddress(wallet);

  let url = args.url!;
  if (args.params) {
    let parsed: Record<string, string>;
    try { parsed = JSON.parse(args.params); } catch { fail("--params must be a JSON object."); }
    const u = new URL(url);
    for (const [k, v] of Object.entries(parsed!)) u.searchParams.set(k, String(v));
    url = u.toString();
  }

  console.log(`Wallet:  ${wallet}  (${from})`);
  console.log(`Request: ${args.method} ${url}\n`);

  const headers: Record<string, string> = { Accept: "application/json" };
  if (args.body && !["GET", "HEAD"].includes(args.method)) headers["Content-Type"] = "application/json";
  const baseInit: RequestInit = { method: args.method, headers, body: args.body };

  // 1) Initial request — expect a 402 challenge.
  let response = await fetch(url, baseInit);

  if (response.status === 402) {
    const challenge = (await response.clone().json().catch(() => ({}))) as { x402Version?: number; accepts?: Requirements[] };
    const req = challenge.accepts?.[0];
    if (!req) fail("402 response did not include payment requirements (accepts[]).");
    console.log(`Paying:  ${req.maxAmountRequired} (base units) on ${req.network} -> ${req.payTo}`);

    const xPayment = buildPaymentHeader(wallet, from, challenge.x402Version ?? 1, req);

    // 2) Retry with the signed payment header.
    response = await fetch(url, { ...baseInit, headers: { ...headers, "X-PAYMENT": xPayment } });
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  console.log(`\nStatus:  ${response.status} ${response.statusText}`);
  console.log("Body:", typeof payload === "string" ? payload : JSON.stringify(payload, null, 2));

  const settleHeader = response.headers.get("x-payment-response");
  if (settleHeader) {
    const settle = JSON.parse(Buffer.from(settleHeader, "base64").toString("utf8"));
    console.log("\nPayment settled:", JSON.stringify(settle, null, 2));
  }

  if (!response.ok) process.exit(1);
}

main().catch((err) => fail(err?.message ?? String(err)));
