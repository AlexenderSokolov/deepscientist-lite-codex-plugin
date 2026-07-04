# 30分钟路径可移植实验：同一份 Graph 怎样跨机器使用

## 前置条件和目标

适合在 Windows、Git Bash 或 WSL 上完成。目标是区分项目相对路径、项目外绝对路径和 `external://` 符号路径。

## 0–8分钟：准备工作区

```bash
python teaching/lab_runner.py --lab paths --mode student --output .validation-tmp/paths-student
```

runner 会创建带中文和空格的项目内文件，以及工作区中的 `external-data/观测 数据.csv`。

## 8–18分钟：观察一次拒绝和一次成功

查看 `logs/absolute-path-rejection.log`：把项目外绝对路径直接写入 Graph 应失败。再看 `project/research/state/graph.json`：同一个外部文件通过 `external://dataset/观测 数据.csv` 关联，Graph 中没有本机根目录。

项目内 `inputs/中文 数据.txt` 使用 POSIX 相对路径。课程测试 UTF-8、空格和路径边界，不故意制造损坏编码。

## 18–25分钟：一段式 Codex 挑战

```text
请审计当前项目的 evidence paths：指出哪些是项目相对路径，哪些是 external alias；确认 Graph 没有保存本机绝对根目录。然后说明在另一台机器上应怎样设置 DS_LITE_EXTERNAL_DATASET。不要手改 graph.json。
```

## 25–30分钟：提交与常见错误

提交路径分类表、拒绝原因和另一台机器的环境变量示例。不要把本机绝对根目录写入答案仓库；不要声称外部文件默认已经哈希，除非明确使用了 `--hash-external`。

参考模式：

```bash
python teaching/lab_runner.py --lab paths --mode reference --output .validation-tmp/paths-answer
```
