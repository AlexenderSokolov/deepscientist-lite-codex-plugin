# 状态与恢复

先读 `PROJECT.md`、`STATUS.md`、work-unit 和 Mission Board，再判断当前阶段。Graph 只通过 state CLI 修改，必须带 `--expected-revision`。artifact 是记录，不等于进展；进展必须能在 Mission Board 看见。一次 worker 只做一个有界动作，留下结果、反思、回退点和下一步。遇到 transport 不明、重复风险、权限或容量不明时保留 `partial/blocked`，不自动重试。换上下文时依赖项目文件和 handoff，不依赖聊天记忆。
