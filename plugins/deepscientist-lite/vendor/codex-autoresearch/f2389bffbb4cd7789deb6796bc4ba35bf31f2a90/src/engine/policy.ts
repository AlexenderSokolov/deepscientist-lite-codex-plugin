/**
 * 业务职责：执行策略类型模块统一收口后台 Codex 子进程的审批与沙箱口径，
 * 让 CLI、应用层和执行引擎对“无人值守任务该怎样跑”使用同一组枚举定义。
 */

/**
 * 业务职责：审批策略枚举表达 Codex 在执行命令或调用受控能力时的宿主审批口径，
 * 供长任务在无人交互场景下显式避免卡死在“等待确认”状态。
 */
export type ApprovalPolicy = "untrusted" | "on-failure" | "on-request" | "never";

/**
 * 业务职责：沙箱模式枚举表达后台执行对子进程文件系统权限的约束强度，
 * 让长任务可以在安全边界与可执行能力之间做稳定、可记录的取舍。
 */
export type SandboxMode = "read-only" | "workspace-write" | "danger-full-access";

/**
 * 业务职责：审批策略白名单为 CLI 参数校验和测试提供单一真值源，
 * 避免不同入口各自维护一份字符串列表导致能力漂移。
 */
export const APPROVAL_POLICIES: ApprovalPolicy[] = ["untrusted", "on-failure", "on-request", "never"];

/**
 * 业务职责：沙箱模式白名单为 CLI 参数校验和测试提供单一真值源，
 * 避免不同入口对同一策略名出现拼写不一致。
 */
export const SANDBOX_MODES: SandboxMode[] = ["read-only", "workspace-write", "danger-full-access"];
