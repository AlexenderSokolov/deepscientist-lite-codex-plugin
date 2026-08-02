# 委派与交接

只有用户或 OpenScience 明确批准后才能启动 child。最多三个任务，路径和结果引用互斥，`nested_delegation=false`，父 worker 是唯一整合者。handoff 只包含目标、输入、允许路径、预算、验证、停止条件、配置摘要和结果引用，不含完整对话、凭据或隐藏推理。child 的“完成”不是证据；父 worker 必须检查 diff、artifact、测试和状态。partial、blocked、ambiguous 都原样交回，不能自动补发。
