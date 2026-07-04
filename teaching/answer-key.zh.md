# 教学参考答案

## 快速体验

PROJECT 保存长期目标和约束；STATUS 是短交接；Graph 保存节点、关系和 active node；Research Map 是可重建的人类投影；artifact 解释某一步做了什么。模板生成不等于 intake 已完成。

## 证据审查

| 场景 | 完整性 | 契约/指标 | 总决定 | 原因 |
| --- | --- | --- | --- | --- |
| clean | pass | pass | pass | 文件未变化，accuracy 0.85 达到0.80 |
| tampered | fail | 不应继续提升 | fail | finalize 后输出变化，哈希不一致 |
| threshold-miss | pass | fail | fail | 文件完整，但 accuracy 0.70 未达阈值 |

退出码只说明进程状态；哈希说明所审查文件是否仍是封装时的文件；阈值说明预先约定是否满足；review 还要检查规范、来源和方法对齐。

## 三分支决策

- A：early 0.82，但 final 0.68 低于0.75，fail。
- B：final 0.79，输入合规，pass；参考路线选择 B。
- C：final 0.93，但读取 `inputs/test_labels.json`，违反 policy，fail。

Evidence Pack 完整不代表输入使用合规。未选路线保留，不能删除。

## 路线语义

progression 路线是 intake → scout → idea → decision。all 模式可以沿 supports 形成更短路径。rollback 记录返回意图，不改写根到 active 的推进历史。Graph 不保存隐藏思维链，也不保存每次 revision 的完整快照。

## 路径与 Revision

项目内路径保存为 POSIX 相对路径；项目外文件使用 `external://dataset/...`，绝对根目录留在环境变量。Revision 实验中，旧 revision 写入以退出码4失败；正确恢复是重读、协调、带新 revision 重试。
