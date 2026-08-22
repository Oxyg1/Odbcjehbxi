/**
 * initData verification regression tests.
 *
 * These fixtures were produced by @telegram-apps/init-data-node — an
 * independent implementation — and confirmed accepted by its own validator
 * before being frozen here. That independence is the point: the previous tests
 * signed payloads with the same helper they then verified, so a shared
 * misreading of the spec passed cleanly.
 *
 * It hid a real one. `signature` (the Ed25519 field added in Bot API 7.10)
 * participates in the HMAC data-check-string like any other field — only
 * `hash` is excluded. Verification excluded `signature` too, which is a no-op
 * on payloads that lack the field, so every self-signed test passed while
 * every genuine launch failed BAD_SIGNATURE in production.
 *
 * Run: npm run test:initdata
 */
import { InitDataError, verifyInitData } from '../src/telegram/init-data.js';

const TOKEN = '8992496257:AAF-fake-token-for-cross-validation-xyz';
/** Fixtures are frozen at this instant; age checks are evaluated against it. */
const SIGNED_AT_MS = 1787391771000;
const now = (): number => SIGNED_AT_MS;

interface Case {
  label: string;
  initData: string;
}

/** Genuine payloads. Every one must verify. */
const VALID: Case[] = [
  {
    label: "non-empty signature",
    initData:
      "user=%7B%22id%22%3A777000999%2C%22first_name%22%3A%22Probe%22%2C%22username%22%3A%22probe%22%7D&auth_date=1787391771&query_id=AAF_x&signature=3A9r_kZbQfXmT0pLcVdEwHnGyJsBu2N4iOaR6PzXqYt8MlKfC1SvDgWhE5UbA7&hash=2cffe54257f4fec3151606655fb49e5f21c8254cbff0c254922431eeffa95d99",
  },
  {
    label: "signature + start_param",
    initData:
      "user=%7B%22id%22%3A42%2C%22first_name%22%3A%22%F0%9F%90%8B+Whale%22%7D&auth_date=1787391771&start_param=stand_abc123&chat_type=private&signature=ZmFrZV9lZDI1NTE5X3NpZ25hdHVyZV92YWx1ZV9mb3JfdGVzdA&hash=8180d9e4410a4339fa647bcfaaf4f3d62ca79f76d290152bb7fa136a94633002",
  },
  {
    label: "plain",
    initData:
      "user=%7B%22id%22%3A777000999%2C%22first_name%22%3A%22Probe%22%7D&auth_date=1787391771&query_id=AAF_x&signature=&hash=13f876e11ef69ecdad74db704de85b8cb169d5469eb705c2acbdccf4d91aef97",
  },
  {
    label: "unicode",
    initData:
      "user=%7B%22id%22%3A1%2C%22first_name%22%3A%22%D0%92%D0%BB%D0%B0%D0%B4%D0%B8%D0%BC%D0%B8%D1%80%22%2C%22last_name%22%3A%22%D0%9F%D1%91%D1%82%D1%80%22%7D&auth_date=1787391771&signature=&hash=bd6029ae93305903585e803c9bd191f658d7c939e789315c3a99e4919444b7d0",
  },
  {
    label: "emoji+start_param",
    initData:
      "user=%7B%22id%22%3A3%2C%22first_name%22%3A%22%F0%9F%90%8B+Whale%22%7D&auth_date=1787391771&start_param=stand_abc&signature=&hash=061bb55a78f3a4d08f4e2301fd12712f37ac3fd7a28a43890fd141eb14de7703",
  },
  {
    label: "premium",
    initData:
      "user=%7B%22id%22%3A5%2C%22first_name%22%3A%22P%22%2C%22is_premium%22%3Atrue%2C%22photo_url%22%3A%22https%3A%2F%2Ft.me%2Fi%2Fx.jpg%22%7D&auth_date=1787391771&signature=&hash=924d5f970c2ab1af9b005003ef47f2de988dc5c2bbb55f15ecc8e6ca54a9b36a",
  },];

let passed = 0;
let failed = 0;

function pass(label: string): void {
  console.log(`  PASS  ${label}`);
  passed += 1;
}

function fail(label: string, detail: string): void {
  console.log(`  FAIL  ${label} — ${detail}`);
  failed += 1;
}

function expectAccepted(label: string, initData: string): void {
  try {
    verifyInitData(initData, { botToken: TOKEN, maxAgeSeconds: 86_400, now });
    pass(label);
  } catch (error) {
    const reason = error instanceof InitDataError ? error.reason : 'unknown';
    fail(label, `rejected as ${reason}`);
  }
}

function expectRejected(label: string, initData: string, wanted: string): void {
  try {
    verifyInitData(initData, { botToken: TOKEN, maxAgeSeconds: 86_400, now });
    fail(label, 'accepted, but should have been rejected');
  } catch (error) {
    const reason = error instanceof InitDataError ? error.reason : 'unknown';
    if (reason === wanted) pass(`${label} -> ${reason}`);
    else fail(label, `rejected as ${reason}, expected ${wanted}`);
  }
}

console.log('\nGenuine payloads from an independent signer:');
for (const item of VALID) expectAccepted(item.label, item.initData);

console.log('\nForgery and expiry:');
const genuine = VALID[0]!.initData;

const swapUser = new URLSearchParams(genuine);
swapUser.set('user', JSON.stringify({ id: 999999999, first_name: 'Attacker' }));
expectRejected('user id swapped', swapUser.toString(), 'BAD_SIGNATURE');

// Guards the fix directly: if `signature` were excluded again, editing it
// would no longer change the hash and this payload would be accepted.
const tamperSignature = new URLSearchParams(genuine);
tamperSignature.set('signature', 'forged_value');
expectRejected('signature tampered', tamperSignature.toString(), 'BAD_SIGNATURE');

const dropSignature = new URLSearchParams(genuine);
dropSignature.delete('signature');
expectRejected('signature removed', dropSignature.toString(), 'BAD_SIGNATURE');

const dropHash = new URLSearchParams(genuine);
dropHash.delete('hash');
expectRejected('hash removed', dropHash.toString(), 'NO_HASH');

expectRejected('foreign bot token', genuine.replace(/hash=.*/, `hash=${'0'.repeat(64)}`), 'BAD_SIGNATURE');

try {
  verifyInitData(genuine, {
    botToken: TOKEN,
    maxAgeSeconds: 60,
    now: () => SIGNED_AT_MS + 3_600_000,
  });
  fail('stale payload', 'accepted');
} catch (error) {
  const reason = error instanceof InitDataError ? error.reason : 'unknown';
  if (reason === 'EXPIRED') pass('stale payload -> EXPIRED');
  else fail('stale payload', `rejected as ${reason}`);
}

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed === 0 ? 0 : 1);
