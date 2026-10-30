# 量化天成 MCP & Skill

让 AI 连接量化天成研究检索和课程目录，并按有来源的步骤整理资料。

- [官网 AI赋能 · 新手说明](https://lhtc2026.com/?preview=ai)
- [登录并连接自己的 AI](https://lhtc2026.com/mcp-connect)
- [下载研究 Skill](https://lhtc2026.com/mcp-skill.zip)

## MCP 和 Skill 有什么区别？

**MCP 负责连接。** 它是一种让 AI 软件连接外部工具的通用方式。量化天成 MCP 提供研究搜索、原文文本或原件入口、课程目录、本人权限和复盘入口。

**Skill 提供方法。** 它是一套操作说明与配套资料，引导 AI 先确认权限，再检索、核对来源，说明日期与资料缺口。本套 Skill 还附有 Python 辅助调用脚本。

先连接 MCP 即可使用工具；Skill 可选。仅下载 Skill 不等于已安装或已连接，也不会自动获得会员或独立付费课程权益。

例如：“搜索人工智能产业链的研究，列出资料来源和明确日期，再整理需要核实的问题。”

## 客户如何开始

1. 打开官网连接页，用自己的官网账号登录。
2. 自行创建个人密钥，只填入信任的 AI 客户端。
3. 客户端需支持远程 MCP / Streamable HTTP 与自定义 Authorization 请求头。服务地址为 `https://lhtc2026.com/mcp`，请求头为 `Authorization: Bearer <本人密钥>`。
4. 重新加载客户端 MCP，再提一个问题试用。需要 Skill 时，按照客户端说明安装 `skills/tiancheng-research/`。

个人密钥默认7天有效，同时受官网登录会话有效期限制；可在连接页撤销。不要把密钥提交到仓库、截图或聊天。

### Codex 配置示例

```toml
[mcp_servers.tiancheng]
url = "https://lhtc2026.com/mcp"
bearer_token_env_var = "TIANCHENG_MCP_TOKEN"
```

将本人密钥提供给本机环境变量 `TIANCHENG_MCP_TOKEN` 或客户端支持的安全存储，再重新加载。配置模板不含密钥；具体操作见 [Codex 官方说明](https://learn.chatgpt.com/docs/extend/mcp)。当前实现尚不支持 OAuth 一键登录。

### 没有原生 MCP 时

可使用 Python 标准库脚本 `skills/tiancheng-research/scripts/call.py`。在本地设置 `TC_MCP_TOKEN` 为自己的有效密钥后：

```text
python skills/tiancheng-research/scripts/call.py --list
python skills/tiancheng-research/scripts/call.py search_research --args '{"query":"人工智能","limit":3}'
```

命令参数中的 JSON 引号按所用终端调整；也可以通过 `--args-file` 读取本地 JSON 文件。

## 已开放工具

| 工具 | 用途 |
|---|---|
| get_service_info | 服务范围与能力边界 |
| get_my_access | 本人研究权限 |
| search_research | 搜索研究片段，最多10条 |
| read_research_source | 可见原文文本；PDF仅返回官网原件入口 |
| list_courses | 课程目录、人民币分价格及访问提示 |
| get_review_entry | 复盘系统官网入口 |

另有 `tiancheng://usage` 资源和 `research_brief` 提示词。

研究日期缺失返回 null；抓取时间不是资料日期，检索片段不等于全文。研究沿用会员权限，独立付费课程仍需另购。首版不提供实时行情、复盘数值、视频下载、批量导出或交易功能；AI软件或模型的费用按各自规则计算。

## 开发与自托管

需要 Python 3.11+。依赖版本是已测试版本，不代表最新版本。

```text
python -m venv .venv
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

运行服务前，安装并使用虚拟环境中的 Python。必须设置：

- `TC_MCP_ENCRYPTION_KEY`：独立生成并持久保存的 Fernet 密钥，不提交 Git。
- `TC_MCP_DB`：私有 SQLite 状态文件路径。
- `TC_PUBLIC_ORIGIN`：客户使用的 HTTPS 正式域名。
- `TC_UPSTREAM_ORIGIN`：同一官网原接口的 HTTPS 地址，需提供 `/member/me`、`/member/search`、`/member/source`、`/courses/list` 等现有接口。

```text
python -m uvicorn server:app_factory --factory --host 127.0.0.1 --port 8766 --no-access-log
```

`deployment/` 提供初始化、systemd和同域反向代理模板，需按实际环境适配，不能不核对就覆盖整站配置。服务仅回环监听，经官网HTTPS代理暴露指定路径。客户领钥需同域官网登录会话；不存在共享会员Cookie或公共研究密钥。

密钥仅保存摘要，网站会话使用 Fernet 加密落盘；每次请求复查上游本人身份，研究工具再检查会员权限。撤销会清空对应会话密文。服务器管理员仍能接触主密钥与数据库，这是应用加密，非端到端加密。

## 验证范围与版本

协议服务/Skill版本0.1.0；官网引导界面版本20261030.2。22项隔离测试通过，并已用本人真实会话完成6工具发现、权限、3条搜索命中及其中第一条PDF原件入口调用；没有解析该PDF全文。本机Codex自身发现6工具。其他客户角色、所有客户端、压力负载和真实会员到期反例仍未完成生产验证。

仓库不包含研究资料、会员数据库、客户密钥、登录会话或私有运维记录。研究资料和课程用于学习交流，不构成投资建议，不承诺收益。

概念参考：[MCP 官方](https://modelcontextprotocol.io/docs/getting-started/intro)、[Skills 官方说明](https://developers.openai.com/plugins/concepts/skills)。
