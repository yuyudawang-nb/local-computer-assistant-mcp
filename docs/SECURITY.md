# 安全边界、最小权限与发布规则

## 每个用户连接自己的设备

这个项目使用本机 stdio MCP 和 OpenAI Secure MCP Tunnel。每个使用者必须使用**自己的** Platform Tunnel、受限运行密钥和 ChatGPT 插件配置。共享连接到作者的 Tunnel，可能导致其他使用者调用作者的设备工具，禁止这样操作。不要开放未经认证的公网 MCP 服务。

## 默认权限

- LOCAL_RESEARCH_ROOT 指定 MCP 的主要文件工作区；默认是用户家目录，但建议显式限制到指定项目。
- LOCAL_RESEARCH_ALLOW_EXEC=0：默认禁用命令执行和可启动/停止命令的高权限进程工具。
- LOCAL_RESEARCH_ALLOW_DESKTOP=0：默认禁用 X11 截图、鼠标、键盘工具。
- 文件读取工具仍可把敏感文件内容交给连接的模型；请不要把工作区指向包含私钥、个人文档的目录。
- LOCAL_RESEARCH_ROOT **不是 OS 沙箱**：一旦启用命令执行，子进程可以使用当前登录用户的全部权限。真实隔离应使用容器、专用系统账户或沙箱。
- 任何机器或网络操作均须遵守当地法规和单位的 IT 政策。

## 运行密钥

- Tunnel 密钥通过终端隐藏输入，不出现在命令行参数和 Git 源码中。
- 经校验的受限运行密钥存放在 ~/.config/local-computer-assistant-mcp/tunnel-runtime.key（0600，当前用户）。
- 启动 MCP 子进程之前，包装脚本主动清除 CONTROL_PLANE_API_KEY、OPENAI_API_KEY、OPENAI_ADMIN_KEY、GH_TOKEN、GITHUB_TOKEN 环境变量。
- 本地其他环境变量和文件并不会被自动清除。不要给 MCP 进程提供多余权限或将项目配置为整个主目录。

## 如何安全地贡献代码

仓库只纳入静态源码和匿名化说明。提交前运行：

~~~bash
python3 scripts/check_public_release.py
git diff --cached --name-only
git diff --cached --check
~~~

绝不提交以下内容：SSH 私钥/公钥授权列表、API key、Token、.env、.venv、SQLite 记忆数据库、任务记录、截图、仿真录像、地图数据、电脑专用代理与内网地址、个人邮箱/手机号、研究服务器访问配置。

.gitignore 是减少误提交的工具，不是安全保证；本项目另有白名单和内容扫描。若误提交了密钥，即使删除文件，仍应**立即撤销密钥并清理 Git 历史**，不能只做 git rm。

## 桌面工具风险

X11 截图可能显示密码、聊天、个人文件；鼠标和键盘可能操作任何当前登录账户有权限的 GUI。启用时应确认屏幕没有敏感内容、优先使用单独系统账户，并检查模型拟执行的动作。

## 范围

此项目仅供自行部署。它不是公开 ChatGPT 插件商店的已审核包，也不支持多人共用作者的本机 Tunnel。公开的多租户插件需要独立的身份认证、权限隔离与符合平台要求的 HTTPS 服务端。
