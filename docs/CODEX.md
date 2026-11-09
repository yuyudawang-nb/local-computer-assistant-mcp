# Codex CLI 本地 MCP 接入

Codex 在同一台电脑上可直接通过 stdio 启动 Python MCP，不需要 OpenAI Secure MCP Tunnel。

1. 安装源码和依赖：

~~~bash
git clone https://github.com/yuyudawang-nb/local-computer-assistant-mcp.git
cd local-computer-assistant-mcp
uv sync --python 3.11
~~~

2. 在自己的 ~/.codex/config.toml 中添加（所有路径必须替换成自己的绝对路径）：

~~~toml
[mcp_servers.local_computer_assistant]
command = "/absolute/path/local-computer-assistant-mcp/.venv/bin/python"
args = ["/absolute/path/local-computer-assistant-mcp/server.py"]

[mcp_servers.local_computer_assistant.env]
LOCAL_RESEARCH_ROOT = "/absolute/path/to/your/workspace"
LOCAL_RESEARCH_ALLOW_EXEC = "0"
LOCAL_RESEARCH_ALLOW_DESKTOP = "0"
~~~

3. 重启 Codex，在对话中让它调用 machine_profile 和 list_files 验证。

4. 如果用户自行决定启用更高权限，将 LOCAL_RESEARCH_ALLOW_EXEC 或 LOCAL_RESEARCH_ALLOW_DESKTOP 改为 "1"；重启 Codex。命令执行以你的系统账户运行，没有 OS 沙箱；桌面功能仅支持 Linux X11。

对话结束并不保证模型继续自主推理；可让 MCP 管理本机长时间进程，但那不同于一个始终运行的大模型 Agent。
