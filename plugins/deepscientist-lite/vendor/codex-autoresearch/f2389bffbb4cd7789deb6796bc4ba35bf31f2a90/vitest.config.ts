/**
 * 业务职责：统一测试入口负责把单元测试、集成测试和 MCP 契约测试纳入同一套 Node 环境，
 * 方便验证 CLI、执行引擎和对外接口在开源发布前的一致性。
 */
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"]
  }
});
