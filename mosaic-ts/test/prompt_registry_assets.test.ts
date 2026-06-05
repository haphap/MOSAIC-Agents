import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { checkPromptRegistryAssets } from "../src/agents/prompts/registry_asset_checks.js";
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

function putJsonAsset(repo: string, relativePath: string, body: unknown): string {
  return putAsset(repo, relativePath, JSON.stringify(body));
}

function putMinimalRkeAssets(repo: string, overrides: { researchOnlyCap?: number } = {}): void {
  putAsset(repo, "shared_contracts/rke_runtime_contract.md", "# Contract\n\nConfidence Policy");
  putJsonAsset(repo, "shared_contracts/confidence_policy.v1.json", {
    confidence_policy_id: "confidence_policy.v1",
    formula: { final_confidence: "min(data_confidence, research_confidence, confidence_cap)" },
    caps: { research_only: overrides.researchOnlyCap ?? 0.5 },
  });
  putJsonAsset(repo, "shared_contracts/rule_aggregation_policy.v1.json", {
    rule_aggregation_policy_id: "rule_aggregation_policy.v1",
    conflict_object_required: true,
  });
  putJsonAsset(repo, promptIrPath("macro.central_bank"), {
    agent_id: "macro.central_bank",
    guardrails: ["research_only_no_trade"],
    status: { production_allowed: false },
  });
  putAsset(repo, "rendered_prompts/macro.central_bank.rke.md", "# macro.central_bank");
  putJsonAsset(repo, "agent_overlays/macro.central_bank.rke.json", {
    prompt_ir_ref: promptIrPath("macro.central_bank"),
    rendered_prompt_ref: "rendered_prompts/macro.central_bank.rke.md",
    shared_contract_refs: [
      "shared_contracts/rke_runtime_contract.md",
      "shared_contracts/confidence_policy.v1.json",
      "shared_contracts/rule_aggregation_policy.v1.json",
    ],
  });
  putJsonAsset(repo, "cohort_overlays/cohort_default/macro.central_bank.rke.json", {
    prompt_ir_ref: promptIrPath("macro.central_bank"),
    production_allowed: false,
  });
  putJsonAsset(repo, "mutation_patches/central_bank_parameter_update.json", {
    mutation: {
      target_path:
        "/rule_packs/macro.central_bank.liquidity.v1/rules/macro.central_bank.soft.001/learnable_parameters/net_injection_window_days/value",
    },
    production_allowed: false,
  });
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

  it("accepts a complete RKE prompt registry asset set", async () => {
    const repo = makePromptRepo();
    repos.push(repo);
    putMinimalRkeAssets(repo.repo);

    const result = await checkPromptRegistryAssets({ promptsRoot: repo.promptsRoot });

    expect(result.ready).toBe(true);
    expect(result.failures).toEqual([]);
    expect(result.checkedAssets).toContain("shared_contracts/confidence_policy.v1.json");
  });

  it("rejects research-only confidence caps above the no-trade limit", async () => {
    const repo = makePromptRepo();
    repos.push(repo);
    putMinimalRkeAssets(repo.repo, { researchOnlyCap: 0.6 });

    const result = await checkPromptRegistryAssets({ promptsRoot: repo.promptsRoot });

    expect(result.ready).toBe(false);
    expect(result.failures).toContainEqual({
      relativePath: "shared_contracts/confidence_policy.v1.json",
      reason: "research_only confidence cap must be <= 0.50",
    });
  });
});
