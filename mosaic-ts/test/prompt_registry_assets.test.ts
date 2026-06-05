import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  loadPromptAssetJson,
  loadPromptAssetText,
  PromptAssetNotFoundError,
  promptAssetPathCandidates,
  promptIrPath,
  promptRepoRootFromPromptsRoot,
  resolvePromptAssetPath,
  sharedContractPath,
} from "../src/agents/prompts/registry_assets.js";

function makePromptRepo(): { repo: string; promptsRoot: string; cleanup: () => void } {
  const repo = mkdtempSync(join(tmpdir(), "mosaic-prompt-assets-"));
  const promptsRoot = join(repo, "prompts", "mosaic");
  mkdirSync(promptsRoot, { recursive: true });
  return {
    repo,
    promptsRoot,
    cleanup: () => rmSync(repo, { recursive: true, force: true }),
  };
}

function putAsset(repo: string, relativePath: string, body: string): string {
  const path = join(repo, relativePath);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, body, "utf-8");
  return path;
}

describe("prompt registry assets", () => {
  const repos: Array<{ cleanup: () => void }> = [];

  afterEach(() => {
    for (const repo of repos.splice(0)) repo.cleanup();
  });

  it("derives the prompt repo root from a prompts/mosaic root", () => {
    expect(promptRepoRootFromPromptsRoot("/tmp/MOSAIC-Prompts/prompts/mosaic")).toBe(
      "/tmp/MOSAIC-Prompts",
    );
  });

  it("resolves bundled repo-level assets from promptsRoot", async () => {
    const bundled = makePromptRepo();
    repos.push(bundled);
    const expected = putAsset(
      bundled.repo,
      promptIrPath("macro.central_bank"),
      '{"agent_id":"macro.central_bank"}',
    );

    const found = resolvePromptAssetPath({
      relativePath: promptIrPath("macro.central_bank"),
      promptsRoot: bundled.promptsRoot,
    });
    const payload = await loadPromptAssetJson<{ agent_id: string }>({
      relativePath: promptIrPath("macro.central_bank"),
      promptsRoot: bundled.promptsRoot,
    });

    expect(found).toBe(expected);
    expect(payload.agent_id).toBe("macro.central_bank");
  });

  it("prefers private prompt repo assets over bundled assets", async () => {
    const bundled = makePromptRepo();
    const privateRepo = makePromptRepo();
    repos.push(bundled, privateRepo);
    putAsset(bundled.repo, sharedContractPath("rke_runtime_contract", "md"), "bundled");
    putAsset(privateRepo.repo, sharedContractPath("rke_runtime_contract", "md"), "private");

    const text = await loadPromptAssetText({
      relativePath: sharedContractPath("rke_runtime_contract", "md"),
      promptsRoot: bundled.promptsRoot,
      privatePromptsRoot: privateRepo.promptsRoot,
    });

    expect(text).toBe("private");
  });

  it("redacts private paths in not-found errors", async () => {
    const bundled = makePromptRepo();
    const privateRepo = makePromptRepo();
    repos.push(bundled, privateRepo);

    await expect(
      loadPromptAssetText({
        relativePath: "shared_contracts/missing.md",
        promptsRoot: bundled.promptsRoot,
        privatePromptsRoot: privateRepo.promptsRoot,
      }),
    ).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(PromptAssetNotFoundError);
      const message = (err as Error).message;
      expect(message).toContain("<private-prompt-repo>");
      expect(message).not.toContain(privateRepo.repo);
      return true;
    });
  });

  it("redacts private paths discovered from env configuration", async () => {
    const privateRepo = makePromptRepo();
    repos.push(privateRepo);
    const oldPromptsRoot = process.env.MOSAIC_PROMPTS_ROOT;
    try {
      process.env.MOSAIC_PROMPTS_ROOT = privateRepo.promptsRoot;

      await expect(
        loadPromptAssetText({
          relativePath: "shared_contracts/missing.md",
        }),
      ).rejects.toSatisfy((err: unknown) => {
        expect(err).toBeInstanceOf(PromptAssetNotFoundError);
        const message = (err as Error).message;
        expect(message).toContain("<private-prompt-repo>");
        expect(message).not.toContain(privateRepo.repo);
        return true;
      });
    } finally {
      if (oldPromptsRoot === undefined) {
        delete process.env.MOSAIC_PROMPTS_ROOT;
      } else {
        process.env.MOSAIC_PROMPTS_ROOT = oldPromptsRoot;
      }
    }
  });

  it("rejects asset paths that escape the prompt repo", () => {
    expect(() =>
      promptAssetPathCandidates({
        relativePath: "../secrets.json",
        promptsRoot: "/tmp/MOSAIC-Prompts/prompts/mosaic",
      }),
    ).toThrow(/must not traverse/);
  });
});
