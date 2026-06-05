import {
  loadPromptAssetJson,
  loadPromptAssetText,
  type PromptAssetOptions,
  promptIrPath,
} from "./registry_assets.js";

export interface PromptRegistryAssetFailure {
  relativePath: string;
  reason: string;
}

export interface PromptRegistryAssetCheckResult {
  ready: boolean;
  checkedAssets: string[];
  failures: PromptRegistryAssetFailure[];
}

const RKE_ASSETS = [
  "shared_contracts/rke_runtime_contract.md",
  "shared_contracts/confidence_policy.v1.json",
  "shared_contracts/rule_aggregation_policy.v1.json",
  promptIrPath("macro.central_bank"),
  "rendered_prompts/macro.central_bank.rke.md",
  "agent_overlays/macro.central_bank.rke.json",
  "cohort_overlays/cohort_default/macro.central_bank.rke.json",
  "mutation_patches/central_bank_parameter_update.json",
] as const;

type JsonObject = Record<string, unknown>;

function objectAt(value: JsonObject, key: string): JsonObject {
  const child = value[key];
  return child && typeof child === "object" && !Array.isArray(child) ? (child as JsonObject) : {};
}

function stringArrayAt(value: JsonObject, key: string): string[] {
  const child = value[key];
  return Array.isArray(child)
    ? child.filter((item): item is string => typeof item === "string")
    : [];
}

function numberAt(value: JsonObject, key: string): number | undefined {
  const child = value[key];
  return typeof child === "number" ? child : undefined;
}

async function loadJson(
  relativePath: string,
  opts: Omit<PromptAssetOptions, "relativePath">,
  failures: PromptRegistryAssetFailure[],
): Promise<JsonObject> {
  try {
    return await loadPromptAssetJson<JsonObject>({ ...opts, relativePath });
  } catch (err) {
    failures.push({ relativePath, reason: (err as Error).message });
    return {};
  }
}

async function assertAssetExists(
  relativePath: string,
  opts: Omit<PromptAssetOptions, "relativePath">,
  failures: PromptRegistryAssetFailure[],
): Promise<void> {
  try {
    await loadPromptAssetText({ ...opts, relativePath });
  } catch (err) {
    failures.push({ relativePath, reason: (err as Error).message });
  }
}

function failIf(
  condition: boolean,
  failures: PromptRegistryAssetFailure[],
  relativePath: string,
  reason: string,
): void {
  if (condition) failures.push({ relativePath, reason });
}

export async function checkPromptRegistryAssets(
  opts: Omit<PromptAssetOptions, "relativePath"> = {},
): Promise<PromptRegistryAssetCheckResult> {
  const failures: PromptRegistryAssetFailure[] = [];
  const checkedAssets = new Set<string>();
  for (const relativePath of RKE_ASSETS) {
    await assertAssetExists(relativePath, opts, failures);
    checkedAssets.add(relativePath);
  }

  const promptIrPathValue = promptIrPath("macro.central_bank");
  const promptIr = await loadJson(promptIrPathValue, opts, failures);
  failIf(
    promptIr.agent_id !== "macro.central_bank",
    failures,
    promptIrPathValue,
    "agent_id must be macro.central_bank",
  );
  failIf(
    !stringArrayAt(promptIr, "guardrails").includes("research_only_no_trade"),
    failures,
    promptIrPathValue,
    "guardrails must include research_only_no_trade",
  );
  failIf(
    objectAt(promptIr, "status").production_allowed !== false,
    failures,
    promptIrPathValue,
    "Prompt IR production_allowed must remain false until promotion gates pass",
  );

  const confidencePath = "shared_contracts/confidence_policy.v1.json";
  const confidence = await loadJson(confidencePath, opts, failures);
  const caps = objectAt(confidence, "caps");
  failIf(
    (numberAt(caps, "research_only") ?? Number.POSITIVE_INFINITY) > 0.5,
    failures,
    confidencePath,
    "research_only confidence cap must be <= 0.50",
  );

  const aggregationPath = "shared_contracts/rule_aggregation_policy.v1.json";
  const aggregation = await loadJson(aggregationPath, opts, failures);
  failIf(
    aggregation.conflict_object_required !== true,
    failures,
    aggregationPath,
    "rule aggregation policy must require conflict objects",
  );

  const agentOverlayPath = "agent_overlays/macro.central_bank.rke.json";
  const agentOverlay = await loadJson(agentOverlayPath, opts, failures);
  for (const key of ["prompt_ir_ref", "rendered_prompt_ref"] as const) {
    const ref = agentOverlay[key];
    if (typeof ref === "string") {
      await assertAssetExists(ref, opts, failures);
      checkedAssets.add(ref);
    }
  }
  for (const ref of stringArrayAt(agentOverlay, "shared_contract_refs")) {
    await assertAssetExists(ref, opts, failures);
    checkedAssets.add(ref);
  }

  const mutationPath = "mutation_patches/central_bank_parameter_update.json";
  const mutationPatch = await loadJson(mutationPath, opts, failures);
  const mutation = objectAt(mutationPatch, "mutation");
  const targetPath = mutation.target_path;
  failIf(
    typeof targetPath !== "string" || !targetPath.startsWith("/rule_packs/"),
    failures,
    mutationPath,
    "mutation target_path must be an absolute rule-pack path",
  );
  failIf(
    mutationPatch.production_allowed !== false,
    failures,
    mutationPath,
    "mutation patch production_allowed must remain false before final promotion",
  );

  return {
    ready: failures.length === 0,
    checkedAssets: [...checkedAssets].sort(),
    failures,
  };
}
