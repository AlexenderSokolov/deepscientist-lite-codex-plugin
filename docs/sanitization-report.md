# 脱敏处理报告

## 已处理内容

- 根目录不再放 `run_validate.sh` 和 `run_validate.ps1`。
- 验证工具移动到 `tools/validation/`，避免被误认为插件运行入口。
- 教学材料移动到 `teaching/`，和插件运行时分离。
- 范式比较案例改为脱敏教学案例，不再作为插件主线目标。
- 文档中避免出现本机绝对路径、Windows 用户名、具体 GPU 型号和私有运行环境。
- 文档中不提供访问凭据或密钥示例。

## 有意保留内容

- manifest 中的 repository/homepage 字段应在发布仓库中指向真实仓库地址；这是插件元数据，不属于本机隐私。
- README 中的安装命令可以在发布前替换为真实 owner，也可以在模板版中写成 `<owner>/<repo>`。

## 发布前检查

运行：

```bash
rg -n "<local-drive-pattern>|<user-home-pattern>|<project-local-name>|<hardware-id>|<secret-prefix>" .|rg -n "<local-drive-pattern>|<user-home-pattern>|<project-local-name>|<hardware-id>|<secret-prefix>" .|rg -n "<local-drive-pattern>|<user-home-pattern>|<project-local-name>|<hardware-id>|<secret-prefix>" .|rg -n "<local-drive-pattern>|<user-home-pattern>|<project-local-name>|<hardware-id>|<secret-prefix>" .|rg -n "<local-drive-pattern>|<user-home-pattern>|<project-local-name>|<hardware-id>|<secret-prefix>" .|rg -n "<local-drive-pattern>|<user-home-pattern>|<project-local-name>|<hardware-id>|<secret-prefix>" .|rg -n "<local-drive-pattern>|<user-home-pattern>|<project-local-name>|<hardware-id>|<secret-prefix>" .
python tools/validation/validate_repo.py
```

如果命中真实本机路径、硬件信息或凭据痕迹，需要先处理再发布。
