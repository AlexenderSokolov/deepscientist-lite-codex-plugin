/**
 * 业务职责：Codex 参数测试负责锁住后台执行的审批与沙箱语义，
 * 防止永动机任务再次因为默认 `--full-auto` 触发无人可响应的审批而把所有 MCP 调用统一取消。
 */
import { describe, expect, it } from "vitest";
import { buildCodexArgs } from "../src/engine/codex.js";
import type { JobMetadata } from "../src/engine/state.js";

/**
 * 业务职责：构造最小可用任务元信息，复用真实执行参数拼装函数验证后台运行口径。
 */
function createMetadata(overrides: Partial<JobMetadata> = {}): JobMetadata {
  return {
    jobId: "job-test",
    stateDir: "/tmp/job-test",
    stateRoot: "/tmp",
    workdir: "/tmp/workdir",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: "pending",
    attemptCount: 0,
    confirmText: "CONFIRMED: all tasks completed",
    nonce: "aaaa-bbbb-cccc",
    doneToken: "cccc-bbbb-aaaa",
    fullAuto: true,
    dangerouslyBypass: false,
    skipGitRepoCheck: false,
    startWithResumeIfPossible: true,
    lastMessageFile: "/tmp/job-test/last-message.txt",
    eventLogFile: "/tmp/job-test/events.jsonl",
    runnerLogFile: "/tmp/job-test/runner.log",
    sessionIdFile: "/tmp/job-test/session-id.txt",
    goalContractFile: "/tmp/job-test/goal-contract.md",
    goalManifestFile: "/tmp/job-test/goal-manifest.json",
    workingPlanFile: "/tmp/job-test/working-plan.latest.md",
    planRevisionsFile: "/tmp/job-test/plan-revisions.jsonl",
    metaFile: "/tmp/job-test/meta.json",
    ...overrides
  };
}

describe("codex execution policy args", () => {
  /**
   * 业务职责：验证无人值守的 full-auto 后台任务会被翻译成显式 `never + workspace-write`，
   * 避免继续依赖会触发审批死锁的 `--full-auto` 快捷别名。
   */
  it("maps unattended full-auto runs to explicit never approval and workspace-write sandbox", () => {
    const args = buildCodexArgs(createMetadata(), {
      codexBin: "codex",
      prompt: "do work",
      mode: "initial"
    });

    expect(args).toContain("-a");
    expect(args).toContain("never");
    expect(args).toContain("-s");
    expect(args).toContain("workspace-write");
    expect(args).not.toContain("--full-auto");
  });

  /**
   * 业务职责：验证用户显式指定审批和沙箱策略时，引擎必须优先透传用户口径，
   * 让排障或高权限场景可以稳定覆盖默认后台策略。
   */
  it("prefers explicit approval and sandbox settings over the implicit full-auto defaults", () => {
    const args = buildCodexArgs(createMetadata({
      approvalPolicy: "on-request",
      sandboxMode: "read-only"
    }), {
      codexBin: "codex",
      prompt: "do work",
      mode: "initial"
    });

    expect(args).toContain("on-request");
    expect(args).toContain("read-only");
    expect(args).not.toContain("never");
    expect(args).not.toContain("workspace-write");
  });
});
