# Local Computer Assistant MCP / 本机电脑助手

一个独立的、本机运行的 Python MCP 服务。让 ChatGPT 或 Codex 使用工具读取项目文件、检查 Git、运行测试、管理任务、操作 Linux X11 桌面。**服务安装在每个人自己的电脑上，不需要把电脑开放到公网。**

> 非 OpenAI 官方产品。源代码独立发布，不包括开发者的私人文件、访问密钥、运行日志、数据库或工作区。Linux X11 是当前桌面功能的已实现平台。务必阅读 [安全说明](docs/SECURITY.md)。

## 功能

| 类型 | 工具 |
|---|---|
| 文件与代码 | list_files, read_file, search_files, apply_unified_patch, git_review |
| 命令与进程 | run_command, start_process / stop_process, start_managed_process / stop_managed_process |
| 桌面（Linux X11） | desktop_info, desktop_screenshot, desktop_click, desktop_move_mouse, desktop_scroll, desktop_hotkey, desktop_type_text |
| 研究与检索 | search_topic, research_and_plan, read_source |
| 项目协作 | task_*, memory_*, project_context, worktree_*, review_panel |
| 环境信息 | machine_profile |

默认 **LOCAL_RESEARCH_ALLOW_EXEC=0**、**LOCAL_RESEARCH_ALLOW_DESKTOP=0**。读文件等工具依然能把内容传给 AI，请仅连接可信模型/工作空间。

## 安装（Ubuntu / Linux）

前置条件：Git、[uv](https://docs.astral.sh/uv/)、Python 3.11（uv 可以安装）；如果需要桌面控制，请使用 X11 会话并安装 xclip。

~~~bash
git clone https://github.com/yuyudawang-nb/local-computer-assistant-mcp.git
cd local-computer-assistant-mcp
uv sync --python 3.11
uv run --frozen pytest -q
uv run --frozen python tests/smoke_mcp.py
~~~

首次运行时可用这个命令确认本机 MCP 能启动（这是 stdio 服务，不会出现网页界面）：

~~~bash
LOCAL_RESEARCH_ROOT="$HOME/Documents" .venv/bin/python server.py
~~~

如果没有 Documents 文件夹，请换成实际存在的个人工作区目录。

## 与 ChatGPT 网页连接（推荐每人独立 Tunnel）

1. 在 [OpenAI Platform Tunnels](https://platform.openai.com/settings/organization/tunnels) **创建自己的** Tunnel，并为自己的 OpenAI 组织、ChatGPT workspace 配置权限。创建/修改 Tunnel 需 Tunnels Read + Manage；运行客户端和选择 Tunnel 需 Tunnels Read + Use。ChatGPT 还需要有添加自定义 MCP 插件的权限。
2. 按 [OpenAI Secure MCP Tunnel 指南](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) 安装官方 [tunnel-client](https://github.com/openai/tunnel-client/releases) 二进制，确认它在 PATH 中（或者设置 TUNNEL_CLIENT 为绝对路径）。不要直接运行来源不明的可执行程序。
3. 在你自己电脑的终端运行以下命令。将 tunnel_... 换成你**自己的 Tunnel ID**，密钥会在终端隐藏输入；不会写入源码目录。

~~~bash
cd local-computer-assistant-mcp
export LOCAL_RESEARCH_ROOT="$HOME/Documents"
./start_chatgpt_tunnel.sh tunnel_YOUR_OWN_ID
~~~

如果你已有自定义代理，在启动前根据自己的网络环境设置 HTTPS_PROXY；本项目**不预设任何作者的代理**。

4. 在 ChatGPT 网页的 Plugins 中选择 **Add custom MCP server → Connection: Tunnel**，选择自己的 Tunnel，完成风险确认并安装插件。
5. 在 ChatGPT 里通过 @ 选择插件，先试：**“读取我电脑的 machine_profile，并列出工作区文件”**。请确认工具确实连接到的是**你自己的电脑**。

**如何按需启用完整能力（有风险）：** 在启动 Tunnel 之前，按自己的意愿设置：

~~~bash
export LOCAL_RESEARCH_ROOT="$HOME/Documents"
export LOCAL_RESEARCH_ALLOW_EXEC=1      # 本机终端命令；以登录用户身份执行，无 OS 沙箱
export LOCAL_RESEARCH_ALLOW_DESKTOP=1   # Linux X11 桌面截图、鼠标和键盘
export DISPLAY=:0                        # 仅在实际 X11 DISPLAY 为 :0 时使用
./start_chatgpt_tunnel.sh tunnel_YOUR_OWN_ID
~~~

执行和桌面工具可能访问工作区之外的文件、操作其他窗口或修改数据；只有了解风险并信任 ChatGPT 插件后才启用。启用桌面工具前，可用 echo "$DISPLAY" 核对实际显示编号。Ubuntu 需安装 xclip 才能使用剪贴板输入。任何操作之前都应核对 ChatGPT 弹出的工具确认。

想让 Tunnel 暂停访问本机，请在启动 Tunnel 的终端按 Ctrl+C。Tunnel 不运行时，网页端不能通过该通道调用此 MCP。

**完整图文式操作说明：** [docs/CHATGPT_TUNNEL.md](docs/CHATGPT_TUNNEL.md)。

## 与 Codex CLI 连接（不需要 Tunnel）

~~~toml
# ~/.codex/config.toml；把 /absolute/path 和 /your/workspace 替换为自己的真实路径
[mcp_servers.local_computer_assistant]
command = "/absolute/path/local-computer-assistant-mcp/.venv/bin/python"
args = ["/absolute/path/local-computer-assistant-mcp/server.py"]

[mcp_servers.local_computer_assistant.env]
LOCAL_RESEARCH_ROOT = "/your/workspace"
LOCAL_RESEARCH_ALLOW_EXEC = "0"
LOCAL_RESEARCH_ALLOW_DESKTOP = "0"
~~~

重启 Codex 会话，读取 machine_profile 测试。详细见 [docs/CODEX.md](docs/CODEX.md)。

## 测试与发布前安全检查

~~~bash
uv run --frozen pytest -q
uv run --frozen python tests/smoke_mcp.py
python3 scripts/check_public_release.py
git status --short
~~~

本仓库只包含**源码白名单**中的文件，没有任何用户的私钥、私人项目、运行密钥或本地 SQLite 记忆数据库。不要提交 .env、运行日志、截图或数据库。添加新文件前先运行安全检查并人工审查 git diff。

## 当前限制

- 桌面控制实现依赖 **Linux X11**；Windows、macOS 和 Wayland 需要适配。纯文件/研究类工具在 Python 3.11 环境可使用。
- 命令工具没有 OS 级沙箱；限制工作目录不等于限制命令可访问的路径。
- MCP 任务状态保存在用户机器本地，并不自动同步到 ChatGPT 原生记忆。
- Tunnel/网页聊天断开后，不会自动有一个大模型持续思考或继续执行新步骤；已启动的受托管进程可能继续运行。
- Secure MCP Tunnel 支持私有连接，不代表把它当作可公开分发的 ChatGPT 插件后端。此 GitHub 仓库提供**每用户独立安装与连接**的开源流程，并非已通过 OpenAI 插件目录审核的产品。

## 许可与资料

MIT License。文档：[安全与权限](docs/SECURITY.md)、[ChatGPT 安装](docs/CHATGPT_TUNNEL.md)、[Codex 设置](docs/CODEX.md)。

OpenAI 官方：[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)、[Add custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server)。
