/**
 * 业务职责：执行引擎测试覆盖“搜索型 MCP 被取消但已成功本地回退时不应阻断完成”的回归场景，
 * 防止同一个 job 明明首轮已经做完，却被无意义地自动续跑到第二轮。
 */
import { describe, expect, it } from "vitest";
import { detectBlockingFailureInEventContent } from "../src/engine/job.js";

describe("job blocking failure detection", () => {
  /**
   * 业务职责：验证当 fast-context 取消后已经落地本地检索命令时，
   * 引擎应把这一轮视为“成功回退”而不是继续阻断 completion。
   */
  it("does not treat cancelled MCP search as blocking when local fallback commands completed", () => {
    const eventContent = [
      JSON.stringify({
        type: "item.completed",
        item: {
          id: "item_1",
          type: "mcp_tool_call",
          server: "fast-context",
          tool: "fast_context_search",
          status: "failed",
          error: { message: "user cancelled MCP tool call" }
        }
      }),
      JSON.stringify({
        type: "item.completed",
        item: {
          id: "item_2",
          type: "command_execution",
          status: "completed",
          command: "/bin/zsh -lc 'rg -n \"foo\" src'"
        }
      })
    ].join("\n");

    expect(detectBlockingFailureInEventContent(eventContent)).toBeUndefined();
  });

  /**
   * 业务职责：验证如果取消后没有任何本地回退痕迹，仍然要保留原本的阻断语义，
   * 避免真正未恢复的 MCP 失败被误判成可安全收尾。
   */
  it("still blocks cancelled MCP calls when no local fallback completed", () => {
    const eventContent = JSON.stringify({
      type: "item.completed",
      item: {
        id: "item_1",
        type: "mcp_tool_call",
        server: "fast-context",
        tool: "fast_context_search",
        status: "failed",
        error: { message: "user cancelled MCP tool call" }
      }
    });

    expect(detectBlockingFailureInEventContent(eventContent)?.code).toBe("MCP_TOOL_CALL_CANCELLED");
  });

  /**
   * 业务职责：验证未命中已知可忽略规则的 MCP 失败仍然要走通用阻断逻辑，
   * 避免为了放过搜索回退场景而把其它真实工具失败一并放掉。
   */
  it("keeps generic MCP failures blocking when they do not match the fallback-ignore rules", () => {
    const eventContent = JSON.stringify({
      type: "item.completed",
      item: {
        id: "item_1",
        type: "mcp_tool_call",
        server: "other-server",
        tool: "other_tool",
        status: "failed",
        error: { message: "unexpected remote failure" }
      }
    });

    expect(detectBlockingFailureInEventContent(eventContent)?.code).toBe("MCP_TOOL_CALL_FAILED");
  });
});
