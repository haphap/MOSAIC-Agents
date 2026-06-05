/**
 * Loader for prompt-repo registry assets outside ``prompts/mosaic``.
 *
 * The markdown prompt loader reads per-agent prompt bodies. The RKE prompt
 * evolution plan also needs repo-level assets such as ``prompt_ir/*.json`` and
 * ``shared_contracts/*``. These helpers use the same private/bundled precedence
 * as prompt files, while resolving asset paths relative to the prompt repo root.
 */

import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, normalize } from "node:path";
import { redactSensitiveText } from "../../security/redaction.js";
import { findPrivatePromptsRoot, findPromptsRoot } from "./cohorts.js";

export class PromptAssetNotFoundError extends Error {
  override readonly name = "PromptAssetNotFoundError";

  constructor(
    public readonly relativePath: string,
    public readonly triedPaths: string[],
    redactionRoots: ReadonlyArray<string> = [],
    cause?: unknown,
  ) {
    const redactedTriedPaths = triedPaths.map((path) => redactSensitiveText(path, redactionRoots));
    super(
      `Prompt registry asset not found for relativePath='${relativePath}'. ` +
        `Tried: ${redactedTriedPaths.join(" | ")}`,
      cause !== undefined ? { cause } : undefined,
    );
    this.triedPaths = redactedTriedPaths;
  }
}

export interface PromptAssetOptions {
  /** Repo-relative asset path, e.g. ``prompt_ir/macro.central_bank.json``. */
  relativePath: string;
  /** Bundled prompt root override; normally ``<repo>/prompts/mosaic``. */
  promptsRoot?: string;
  /** Private prompt root override; normally ``<privateRepo>/prompts/mosaic``. */
  privatePromptsRoot?: string;
}

export function promptRepoRootFromPromptsRoot(promptsRoot: string): string {
  const root = normalize(promptsRoot);
  if (basename(root) === "mosaic" && basename(dirname(root)) === "prompts") {
    return dirname(dirname(root));
  }
  return root;
}

function assertSafeRelativePath(relativePath: string): void {
  if (!relativePath.trim()) {
    throw new Error("prompt registry asset relativePath is required");
  }
  if (isAbsolute(relativePath)) {
    throw new Error("prompt registry asset relativePath must be repo-relative");
  }
  if (relativePath.split(/[\\/]+/).includes("..")) {
    throw new Error("prompt registry asset relativePath must not traverse outside the repo");
  }
}

export function promptAssetPathCandidates(opts: PromptAssetOptions): string[] {
  assertSafeRelativePath(opts.relativePath);
  const baselineRoot = promptRepoRootFromPromptsRoot(opts.promptsRoot ?? findPromptsRoot());
  const privatePromptsRoot =
    opts.privatePromptsRoot ?? (opts.promptsRoot ? undefined : findPrivatePromptsRoot());
  const privateRoot = privatePromptsRoot
    ? promptRepoRootFromPromptsRoot(privatePromptsRoot)
    : undefined;
  const roots: string[] = [];
  for (const root of [privateRoot, baselineRoot]) {
    if (root && !roots.includes(root)) roots.push(root);
  }
  return roots.map((root) => join(root, opts.relativePath));
}

export function resolvePromptAssetPath(opts: PromptAssetOptions): string | null {
  for (const path of promptAssetPathCandidates(opts)) {
    if (existsSync(path)) return path;
  }
  return null;
}

function redactionRoots(opts: PromptAssetOptions): string[] {
  const privatePromptsRoot =
    opts.privatePromptsRoot ?? (opts.promptsRoot ? undefined : findPrivatePromptsRoot());
  if (!privatePromptsRoot) return [];
  return [privatePromptsRoot, promptRepoRootFromPromptsRoot(privatePromptsRoot)];
}

export async function loadPromptAssetText(opts: PromptAssetOptions): Promise<string> {
  const path = resolvePromptAssetPath(opts);
  if (path === null) {
    throw new PromptAssetNotFoundError(
      opts.relativePath,
      promptAssetPathCandidates(opts),
      redactionRoots(opts),
    );
  }
  try {
    return await readFile(path, { encoding: "utf-8" });
  } catch (err) {
    throw new PromptAssetNotFoundError(
      opts.relativePath,
      [`${path} (${(err as Error).message})`],
      redactionRoots(opts),
      err,
    );
  }
}

export async function loadPromptAssetJson<T = unknown>(opts: PromptAssetOptions): Promise<T> {
  const text = await loadPromptAssetText(opts);
  return JSON.parse(text) as T;
}

export function promptIrPath(agentId: string): string {
  return `prompt_ir/${agentId}.json`;
}

export function sharedContractPath(contractId: string, extension = "md"): string {
  return `shared_contracts/${contractId}.${extension}`;
}
