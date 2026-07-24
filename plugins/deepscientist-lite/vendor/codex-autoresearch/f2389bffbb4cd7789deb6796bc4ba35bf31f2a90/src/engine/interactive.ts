/**
 * 业务职责：交互模块负责在 CLI 缺失必要参数时做最小补问，
 * 让直接任务和 skill 执行都能保持“命令优先、必要时补齐”的体验。
 *
 * 为什么这里只做最小能力：
 * - 本项目主路径仍然是命令优先和自动化优先，交互只是补缺，不应该演变成复杂表单系统。
 */
import { stdin as input, stdout as output } from "node:process";
import { createInterface } from "node:readline/promises";

/**
 * 业务职责：向终端请求一个业务参数值，避免 skill 模板因为缺少关键输入而无法落地执行。
 *
 * 示例：
 * - `skill run research` 缺少 `topic` 时，可以即时补问而不是直接失败。
 * - 根入口无参数时，也能用同一个交互能力询问是 `run / skill / resume / app`。
 */
export async function ask(question: string, defaultValue?: string): Promise<string> {
  const rl = createInterface({ input, output });
  const suffix = defaultValue ? ` (${defaultValue})` : "";
  const answer = (await rl.question(`${question}${suffix}: `)).trim();
  rl.close();
  return answer || defaultValue || "";
}
