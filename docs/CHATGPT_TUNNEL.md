# 从零连接自己的 ChatGPT 与自己的电脑

## 0. 确认使用模式

~~~text
你的 ChatGPT 账号 / 你的插件
       |
你自己的 OpenAI Secure MCP Tunnel（出站 HTTPS）
       |
你电脑上的 tunnel-client
       |
本机 stdio server.py
       |
你授权访问的文件夹 /（可选）命令与 X11 桌面
~~~

**不要使用仓库作者的 Tunnel ID 或 API key，也不要把密钥发给别人。** 每个使用者必须自己创建并管理 Tunnel。此连接不需要开放公网入站端口。

## 1. 安装本地 MCP

需要 Linux、Python 3.11、Git 与 uv。复制仓库后：

~~~bash
git clone https://github.com/yuyudawang-nb/local-computer-assistant-mcp.git
cd local-computer-assistant-mcp
uv sync --python 3.11
uv run --frozen pytest -q
uv run --frozen python tests/smoke_mcp.py
~~~

smoke 测试会在它自己的临时 MCP 进程中执行无副作用的 pwd 命令；这并不表示日常启动时自动启用了命令执行。

## 2. 获得 OpenAI Tunnel ID

打开 https://platform.openai.com/settings/organization/tunnels，创建 Tunnel 并记下 tunnel_... ID。必须使用你想连接的 ChatGPT workspace 关联的组织/工作空间。

在 Platform 里创建有 **Tunnels Read + Use** 权限的受限运行密钥；创建/维护 Tunnel 本身需要 Tunnels Read + Manage。ChatGPT 自定义 MCP 插件接入另受账号、工作空间或管理员政策限制。

## 3. 安装官方 tunnel-client

按照 https://github.com/openai/tunnel-client/releases 和 https://developers.openai.com/api/docs/guides/secure-mcp-tunnels 安装适合你 CPU/操作系统的官方构建，检查官方发布信息和校验值。

确认命令可用：

~~~bash
tunnel-client --help
~~~

如果可执行文件不在 PATH 中，设置绝对路径：

~~~bash
export TUNNEL_CLIENT="/absolute/path/to/tunnel-client"
~~~

不要从别人发来的网盘复制 Tunnel 客户端或者作者的密钥。

## 4. 启动自己的连接

~~~bash
cd local-computer-assistant-mcp
export LOCAL_RESEARCH_ROOT="$HOME/Documents"   # 根据你的实际工作目录修改
./start_chatgpt_tunnel.sh tunnel_YOUR_OWN_ID
~~~

首次启动时，会提示在本机终端隐藏输入自己的受限运行密钥。验证后仅保存在：

~~~text
~/.config/local-computer-assistant-mcp/tunnel-runtime.key
~~~

权限为 0600。密钥绝不提交到 Git 或粘贴到聊天中。更换自己的密钥时：

~~~bash
LOCAL_RESEARCH_REKEY=1 ./start_chatgpt_tunnel.sh tunnel_YOUR_OWN_ID
~~~

如果终端显示 doctor 通过并开始轮询，就保持该终端运行。如果无法访问 Platform，请检查你自己的网络或在终端自行设置 HTTPS_PROXY（不要使用作者机器的代理地址）。

## 5. 在 ChatGPT 添加插件

打开 ChatGPT 的 Plugins，选择 Add custom MCP server，连接类型选择 Tunnel，使用自己的 tunnel_...，按界面完成认证、风险提示与安装。如果选不到 Tunnel，检查 Platform organization 和 ChatGPT workspace 关联，以及相关权限。

新聊天 @ 选择插件，先执行 machine_profile 和 list_files；输出应显示你自己的计算机信息和目录。如果工具列表没有最新工具，停止并重启 tunnel-client，然后从插件详情刷新工具列表。

## 6. 启用可选的本机执行 / 桌面控制

**默认这些高权限功能都关闭。** 仅在确有需要且明确理解风险时：

~~~bash
export LOCAL_RESEARCH_ROOT="$HOME/Documents"
export LOCAL_RESEARCH_ALLOW_EXEC=1
export LOCAL_RESEARCH_ALLOW_DESKTOP=1
# 如果是 X11，先 echo "$DISPLAY" 检查是否已有正确值
./start_chatgpt_tunnel.sh tunnel_YOUR_OWN_ID
~~~

桌面功能只实现了 X11，需要正在登录的桌面会话和 xclip。运行中修改环境变量无效，需要重新启动 Tunnel 子进程。

### 常见问题

- **看不到插件：** 检查 workspace 权限、Tunnel 关联、是否安装自定义插件。
- **密钥权限错误：** 使用自己组织中具备 Tunnels Read + Use 权限的 Restricted key。
- **找不到 tunnel-client：** 用 TUNNEL_CLIENT 指定可执行文件，或加入 PATH。
- **脚本说找不到 .venv：** 在源码目录重新运行 uv sync --python 3.11。
- **桌面截图失败：** 检查 X11 DISPLAY、XAUTHORITY 与操作系统权限；Wayland 并不受支持。
- **“run_command disabled”：** 这是安全默认值，只有明确同意后设置 LOCAL_RESEARCH_ALLOW_EXEC=1。
- **插件断线：** 确认 Tunnel 终端仍在运行；关闭 Tunnel 不会删除本机持久任务。
- **8080 端口冲突：** 启动脚本当前使用本机 127.0.0.1:8080 的健康检查地址，退出冲突程序或单独调整脚本配置。
- **怀疑泄露密钥：** 立即在 Platform 中撤销密钥、重新生成；必要时删除已配置 Tunnel。

官方说明：https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
