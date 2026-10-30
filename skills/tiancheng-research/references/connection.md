# 客户连接

上线后在 https://lhtc2026.com/mcp-connect 使用本人官网账号领取密钥。当前生产是否上线以交付报告为准。

支持自定义请求头的客户端：服务地址 `https://lhtc2026.com/mcp`，传输 Streamable HTTP，请求头 `Authorization: Bearer <本人密钥>`。某些客户端的JSON字段和配置位置不同，不能把一个配置样例承诺适用于所有软件。首版未实现OAuth，不能承诺在所有ChatGPT/Claude连接器中一键登录。

没有原生MCP时，Python 3标准库脚本可调用同一服务：先在可信本地终端设置环境变量 `TC_MCP_TOKEN`（不回显、不提交Git），再执行：

```text
python scripts/call.py --list
python scripts/call.py get_my_access
python scripts/call.py search_research --args '{"query":"人工智能","limit":3}'
```

PowerShell的JSON引号可能被原生命令解释，可使用 `--args-file` 读取UTF-8 JSON文件。脚本不会保存或输出密钥。TC_MCP_URL默认官网；仅允许HTTPS和本机HTTP测试。脚本不代登录、不安装依赖、不购买数据。
