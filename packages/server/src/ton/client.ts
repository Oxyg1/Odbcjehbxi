import { Address, beginCell, Cell } from '@ton/core';
import { TonClient } from '@ton/ton';
import { sha256 } from '@ton/crypto';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';

/** Lazily constructed: nodes with the watcher disabled never open a socket. */
let client: TonClient | null = null;

export function getTonClient(): TonClient {
  if (!client) {
    client = new TonClient({
      endpoint: env.TON_API_ENDPOINT,
      ...(env.TON_API_KEY ? { apiKey: env.TON_API_KEY } : {}),
    });
  }
  return client;
}

/** Normalise any address form to the raw `0:<hex>` representation we store. */
export function toRawAddress(address: string): string {
  return Address.parse(address).toRawString();
}

export function toFriendlyAddress(rawAddress: string, bounceable = false): string {
  return Address.parse(rawAddress).toString({ bounceable, urlSafe: true });
}

export function isValidAddress(address: string): boolean {
  try {
    Address.parse(address);
    return true;
  } catch {
    return false;
  }
}

/* ------------------------- TON Connect proof ---------------------------- */

export interface TonProof {
  timestamp: number;
  domain: { lengthBytes: number; value: string };
  signature: string;
  payload: string;
  stateInit?: string;
}

const TON_PROOF_PREFIX = 'ton-proof-item-v2/';
const TON_CONNECT_PREFIX = 'ton-connect';
/** Proofs older than this are rejected regardless of signature validity. */
const PROOF_MAX_AGE_SECONDS = 15 * 60;

/**
 * Verify a TON Connect `ton_proof`.
 *
 * The wallet signs
 *   sha256( 0xffff ++ "ton-connect" ++ sha256(message) )
 * where message is
 *   "ton-proof-item-v2/" ++ workchain ++ addrHash ++ domainLen ++ domain
 *                        ++ timestamp ++ payload
 *
 * Reference: https://docs.ton.org/develop/dapps/ton-connect/sign
 */
export async function buildTonProofMessage(
  rawAddress: string,
  proof: TonProof,
): Promise<Buffer> {
  const address = Address.parse(rawAddress);

  const workchainBuffer = Buffer.alloc(4);
  workchainBuffer.writeInt32BE(address.workChain);

  const domainLengthBuffer = Buffer.alloc(4);
  domainLengthBuffer.writeUInt32LE(proof.domain.lengthBytes);

  const timestampBuffer = Buffer.alloc(8);
  timestampBuffer.writeBigUInt64LE(BigInt(proof.timestamp));

  const message = Buffer.concat([
    Buffer.from(TON_PROOF_PREFIX),
    workchainBuffer,
    address.hash,
    domainLengthBuffer,
    Buffer.from(proof.domain.value),
    timestampBuffer,
    Buffer.from(proof.payload),
  ]);

  const messageHash = await sha256(message);

  return Buffer.concat([
    Buffer.from([0xff, 0xff]),
    Buffer.from(TON_CONNECT_PREFIX),
    messageHash,
  ]);
}

export interface VerifyProofInput {
  rawAddress: string;
  proof: TonProof;
  /** The nonce we handed out; replaying an old payload must fail. */
  expectedPayload: string;
  /** Domains we accept a proof for. */
  allowedDomains: string[];
  publicKeyHex: string;
}

export async function verifyTonProof(input: VerifyProofInput): Promise<boolean> {
  const { proof } = input;

  const ageSeconds = Math.floor(Date.now() / 1000) - proof.timestamp;
  if (ageSeconds > PROOF_MAX_AGE_SECONDS || ageSeconds < -60) {
    logger.debug({ ageSeconds }, 'ton proof rejected: stale timestamp');
    return false;
  }
  if (proof.payload !== input.expectedPayload) {
    logger.debug('ton proof rejected: payload mismatch');
    return false;
  }
  if (!input.allowedDomains.includes(proof.domain.value)) {
    logger.debug({ domain: proof.domain.value }, 'ton proof rejected: untrusted domain');
    return false;
  }

  try {
    const fullMessage = await buildTonProofMessage(input.rawAddress, proof);
    const digest = await sha256(fullMessage);
    const { signVerify } = await import('@ton/crypto');
    return signVerify(
      digest,
      Buffer.from(proof.signature, 'base64'),
      Buffer.from(input.publicKeyHex, 'hex'),
    );
  } catch (error) {
    logger.warn({ err: error }, 'ton proof verification threw');
    return false;
  }
}

/** Text comment payload, so a transfer can carry our transaction id on-chain. */
export function buildCommentPayload(comment: string): Cell {
  return beginCell().storeUint(0, 32).storeStringTail(comment).endCell();
}

export function parseCommentPayload(body: Cell): string | null {
  try {
    const slice = body.beginParse();
    if (slice.remainingBits < 32) return null;
    const opcode = slice.loadUint(32);
    if (opcode !== 0) return null;
    return slice.loadStringTail();
  } catch {
    return null;
  }
}
