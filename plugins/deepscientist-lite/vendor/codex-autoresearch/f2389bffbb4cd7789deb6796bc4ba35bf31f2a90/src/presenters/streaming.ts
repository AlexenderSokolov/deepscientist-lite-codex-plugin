/**
 * 业务职责：流式终端 presenter 在任务执行过程中实时输出彩色进度到 stderr，
 * 让用户像 `tail -f` 一样观察每轮 attempt 的 AI 回复和工具调用。
 *
 * 事件格式基于 codex exec --json 的实际输出：
 * - thread.started: { type, thread_id }
 * - turn.started / turn.completed: { type, usage? }
 * - item.started / item.completed: { type, item: { id, type, ... } }
 *   item.type 可为: agent_message, command_execution, mcp_tool_call, file_change
 */

export interface StreamCallbacks {
  onAttemptStart: (attempt: number) => void;
  onAttemptEnd: (attempt: number, exitCode: number, elapsed: number) => void;
  onEvent: (event: Record<string, unknown>) => void;
}

const CYAN = "\x1b[36m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const BLUE = "\x1b[34m";
const RED = "\x1b[31m";
const DIM = "\x1b[2m";
const BOLD = "\x1b[1m";
const RESET = "\x1b[0m";
const HIDE_CURSOR = "\x1b[?25l";
const SHOW_CURSOR = "\x1b[?25h";
const CLEAR_LINE = "\x1b[2K\r";

const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

export function createStreamingPresenter(stream: NodeJS.WritableStream): StreamCallbacks {
  const isTTY = (stream as { isTTY?: boolean }).isTTY === true;
  const c = (code: string, text: string) => (isTTY ? `${code}${text}${RESET}` : text);
  const cols = (stream as { columns?: number }).columns ?? 80;

  let spinnerTimer: ReturnType<typeof setInterval> | undefined;
  let spinnerFrame = 0;
  let spinnerLabel = "";

  function startSpinner(label: string): void {
    if (!isTTY) return;
    stopSpinner();
    spinnerLabel = label;
    spinnerFrame = 0;
    stream.write(HIDE_CURSOR);
    spinnerTimer = setInterval(() => {
      const frame = SPINNER_FRAMES[spinnerFrame % SPINNER_FRAMES.length];
      stream.write(`${CLEAR_LINE}${c(DIM, `${frame} ${spinnerLabel}`)}`);
      spinnerFrame++;
    }, 80);
  }

  function stopSpinner(): void {
    if (spinnerTimer !== undefined) {
      clearInterval(spinnerTimer);
      spinnerTimer = undefined;
      stream.write(`${CLEAR_LINE}${SHOW_CURSOR}`);
    }
  }

  function write(text: string): void {
    stopSpinner();
    stream.write(text);
  }

  function formatTime(): string {
    return new Date().toISOString().replace("T", " ").replace(/\.\d+Z$/, "");
  }

  function formatElapsed(ms: number): string {
    const s = Math.round(ms / 1000);
    return s >= 60 ? `${Math.floor(s / 60)}m${s % 60}s` : `${s}s`;
  }

  /** 把 AI 消息按行输出，长段落自动折行 */
  function writeMessage(text: string): void {
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const prefix = i === 0 ? "🤖 " : "   ";
      write(`${c(GREEN, prefix + lines[i])}\n`);
    }
  }

  /** 把命令输出截取前几行有意义的内容 */
  function formatOutput(raw: string, maxLines: number): string {
    const lines = raw.split("\n").filter(l => l.trim().length > 0);
    if (lines.length === 0) return "";
    const shown = lines.slice(0, maxLines);
    const rest = lines.length - shown.length;
    const result = shown.map(l => `   │ ${truncateLine(l, cols - 8)}`).join("\n");
    if (rest > 0) {
      return `${result}\n   ${c(DIM, `… +${rest} more lines`)}`;
    }
    return result;
  }

  return {
    onAttemptStart(attempt: number) {
      const line = `━━━━ 第 ${attempt} 轮 ${"━".repeat(30)}  ${formatTime()}`;
      write(`\n${c(CYAN, line)}\n`);
      startSpinner("等待响应...");
    },

    onAttemptEnd(attempt: number, exitCode: number, elapsed: number) {
      const line = `━━━━ 第 ${attempt} 轮结束 (exit ${exitCode}, 耗时 ${formatElapsed(elapsed)}) ${"━".repeat(10)}`;
      write(`${c(CYAN, line)}\n`);
    },

    onEvent(event: Record<string, unknown>) {
      const eventType = event.type as string | undefined;
      const item = event.item as Record<string, unknown> | undefined;
      const itemType = item?.type as string | undefined;

      // --- turn.completed: 显示 token 用量 ---
      if (eventType === "turn.completed") {
        const usage = event.usage as { input_tokens?: number; output_tokens?: number; cached_input_tokens?: number } | undefined;
        if (usage) {
          const parts: string[] = [];
          if (usage.input_tokens) parts.push(`in:${formatTokens(usage.input_tokens)}`);
          if (usage.cached_input_tokens) parts.push(`cached:${formatTokens(usage.cached_input_tokens)}`);
          if (usage.output_tokens) parts.push(`out:${formatTokens(usage.output_tokens)}`);
          write(`${c(DIM, `📊 ${parts.join(" / ")}`)}\n`);
        }
        return;
      }

      if (!item || !itemType) return;

      // --- agent_message: AI 的文本回复 ---
      if (itemType === "agent_message") {
        const text = item.text as string | undefined;
        if (text && eventType === "item.completed") {
          writeMessage(text);
          write("\n");
          startSpinner("思考中...");
        }
        return;
      }

      // --- command_execution: shell 命令 ---
      // 只在 item.completed 时输出，同时显示命令和结果，避免重复
      if (itemType === "command_execution" && eventType === "item.completed") {
        const command = item.command as string | undefined;
        const exitCode = item.exit_code as number | undefined;
        const output = item.aggregated_output as string | undefined;

        if (command) {
          const desc = humanizeCommand(extractShellCommand(command));
          const exitTag = exitCode !== undefined && exitCode !== 0
            ? c(RED, ` [exit ${exitCode}]`)
            : "";
          write(`${c(YELLOW, `  ⚡ ${desc}`)}${exitTag}\n`);
        }

        if (output && output.trim()) {
          const formatted = formatOutput(output, 6);
          if (formatted) {
            write(`${c(DIM, formatted)}\n`);
          }
        }

        startSpinner("思考中...");
        return;
      }

      // --- mcp_tool_call: MCP 工具调用 ---
      // 只在 item.completed 时输出
      if (itemType === "mcp_tool_call" && eventType === "item.completed") {
        const server = item.server as string | undefined;
        const tool = item.tool as string | undefined;
        const args = item.arguments as Record<string, unknown> | undefined;
        const status = item.status as string | undefined;
        const error = item.error as { message?: string } | undefined;

        const label = [server, tool].filter(Boolean).join("/");
        const argsSummary = args ? summarizeArgs(args) : "";
        write(`${c(YELLOW, `  🔌 ${label}`)}${argsSummary ? c(DIM, ` ${argsSummary}`) : ""}\n`);

        if (status === "failed" && error?.message) {
          write(`${c(RED, `     ✗ ${error.message}`)}\n`);
        }

        startSpinner("思考中...");
        return;
      }

      // --- mcp_tool_call item.started: 只显示 spinner ---
      if (itemType === "mcp_tool_call" && eventType === "item.started") {
        const tool = item.tool as string | undefined;
        startSpinner(`执行 ${tool ?? "MCP"}...`);
        return;
      }

      // --- command_execution item.started: 只显示 spinner ---
      if (itemType === "command_execution" && eventType === "item.started") {
        startSpinner("执行命令...");
        return;
      }

      // --- file_change: 文件变更 ---
      if (itemType === "file_change" && eventType === "item.completed") {
        const changes = item.changes as Array<{ path?: string; kind?: string }> | undefined;
        if (changes && changes.length > 0) {
          for (const change of changes) {
            const kind = change.kind ?? "change";
            const filePath = change.path ?? "unknown";
            // 只显示文件名，不显示完整路径
            const shortPath = shortenPath(filePath);
            const icon = kind === "create" ? c(GREEN, "+") : kind === "delete" ? c(RED, "-") : c(BLUE, "~");
            write(`  📝 [${icon}] ${c(BOLD, shortPath)}\n`);
          }
          startSpinner("思考中...");
        }
        return;
      }
    }
  };
}

// ────────────────────────── helpers ──────────────────────────

/**
 * 从 `/bin/zsh -lc "actual command"` 格式中提取实际命令。
 */
function extractShellCommand(raw: string): string {
  // codex 的 command 字段格式: /bin/zsh -lc "actual command"
  // JSON 解析后双引号已经是普通字符
  const match = raw.match(/^\/bin\/(?:ba|z)?sh\s+-\w+\s+"(.+)"$/s);
  if (match) return match[1];
  const match2 = raw.match(/^\/bin\/(?:ba|z)?sh\s+-\w+\s+(.+)$/s);
  return match2 ? match2[1] : raw;
}

/**
 * 把 shell 命令转为人类可读描述。
 * 例：sed -n '1,260p' 'path/to/file' → read path/to/file :1-260
 */
function humanizeCommand(cmd: string): string {
  // sed -n 'Ns,Nep' 'file' → read file :Ns-Ne
  const sedMatch = cmd.match(/^sed\s+-n\s+'(\d+),(\d+)p'\s+'(.+)'$/);
  if (sedMatch) {
    return `read ${shortenPath(sedMatch[3])} :${sedMatch[1]}-${sedMatch[2]}`;
  }

  // head/tail -n N file → read file (head/tail N)
  const headMatch = cmd.match(/^(head|tail)\s+-(?:n\s*)?(\d+)\s+'?(.+?)'?$/);
  if (headMatch) {
    return `${headMatch[1]} ${shortenPath(headMatch[3])} -${headMatch[2]}`;
  }

  // cat 'file' → read file
  const catMatch = cmd.match(/^cat\s+'(.+)'$/);
  if (catMatch) {
    return `read ${shortenPath(catMatch[1])}`;
  }

  // ls / find / rg → 保持简短
  const lsMatch = cmd.match(/^ls\s+(?:-\S+\s+)?'(.+)'$/);
  if (lsMatch) {
    return `ls ${shortenPath(lsMatch[1])}`;
  }

  // find 'dir' ... → find dir
  const findMatch = cmd.match(/^find\s+'([^']+)'\s/);
  if (findMatch) {
    return `find ${shortenPath(findMatch[1])} ...`;
  }

  // rg patterns → grep "pattern" ...
  const rgMatch = cmd.match(/^rg\s+(?:--?\S+\s+)*["']?(.{1,40})["']?\s/);
  if (rgMatch) {
    return `grep "${truncateLine(rgMatch[1], 30)}" ...`;
  }

  // wc -l 'file' → wc file
  const wcMatch = cmd.match(/^wc\s+-\w+\s+'(.+)'$/);
  if (wcMatch) {
    return `wc ${shortenPath(wcMatch[1])}`;
  }

  // 其他命令直接截断
  return truncateLine(cmd, 80);
}

/** 缩短路径：只保留最后两级目录 + 文件名 */
function shortenPath(fullPath: string): string {
  const parts = fullPath.replace(/^\/+/, "").split("/");
  if (parts.length <= 3) return parts.join("/");
  return `…/${parts.slice(-3).join("/")}`;
}

/** 把 MCP 参数对象生成简短摘要 */
function summarizeArgs(args: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(args)) {
    if (typeof value === "string") {
      parts.push(`${key}="${truncateLine(value, 40)}"`);
    } else if (typeof value === "number" || typeof value === "boolean") {
      parts.push(`${key}=${value}`);
    }
  }
  const joined = parts.join(", ");
  if (joined.length > 100) {
    return `(${joined.slice(0, 100)}...(+${joined.length - 100} chars))`;
  }
  return parts.length > 0 ? `(${joined})` : "";
}

/** token 数量格式化：大数用 k 表示 */
function formatTokens(n: number): string {
  return n >= 10000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function truncateLine(s: string, maxLen: number): string {
  const clean = s.replace(/[\n\r]/g, " ").trim();
  if (clean.length <= maxLen) return clean;
  const omitted = clean.length - maxLen;
  return `${clean.slice(0, maxLen)}...(+${omitted})`;
}
