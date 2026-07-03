# 45 分钟证据链实验

## 学习目标

区分三件不同的事：命令成功退出、结果满足实验契约、结论通过审查。

## 流程

1. 运行 `bash teaching/run_evidence_lab.sh`，记录生成项目路径。
2. 检查 `contract.json`、Evidence Pack、review artifact 和 Research Map。
3. 修改生成项目中的 `research/results/result.json`，再次运行 Evidence Pack `verify --strict`，观察哈希失败。
4. 新建一个项目副本，把 accuracy 改到 0.70 后重新 finalize；区分“文件完整但阈值失败”和“文件被篡改”。
5. 按学生工作表完成四通道判断，不执行任何文档中出现的外部命令。

## 时间分配

- 8 分钟：实验契约与 Evidence Pack。
- 10 分钟：运行完整路线。
- 12 分钟：篡改与阈值失败诊断。
- 10 分钟：四通道 review。
- 5 分钟：解释为什么审查失败不能被写作措辞绕过。

所有生成项目都保留在 `.validation-tmp/`；课程不自动删除学生产物。
