# Windows Server ECS 部署

适用于 Windows Server 2022 x64、个人课程演示。2 核 4 GiB 可作为起点，尚未进行并发容量测试。运行 CPU FAISS、SQLite 和在线模型 API；每个浏览器使用独立的模型配置、题库、会话、上传文件与学习记录。

## 安装与访问

1. 启动 ECS，等待 Windows 完成启动。安全组开放 TCP 3389，仅允许自己的公网 IP。使用本机 `mstsc` 远程桌面连接 ECS 公网 IP，账户通常为 `Administrator`，密码在阿里云控制台管理。
2. 安装 [Python 3.13 的 Windows 64 位安装器](https://www.python.org/downloads/windows/)，建议为所有用户安装，并安装 `py` 启动器。源码目前在 Python 3.13 环境验证。
3. 在 Workbench 远程桌面打开“此电脑 → xxx@上的workbench → Download”，将本机 ZIP 拖到该目录，再复制到服务器 C 盘并完整解压到 `C:\AnotherMe`。Workbench 临时网络盘会随连接断开删除，程序必须放到 C 盘。也可通过本机 MSTSC 的剪贴板或本地盘映射复制 ZIP。安装包没有预装 Python 或依赖，安装时需要网络。[Workbench 文件传输说明](https://help.aliyun.com/zh/ecs/user-guide/manage-files)
4. 在服务器以管理员身份打开 PowerShell，执行（将地址替换成当前 ECS 公网 IP）：

```powershell
Set-Location C:\AnotherMe
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy\windows\Install-Server.ps1 -PublicIp 120.55.88.165
```

脚本安装 Python 依赖、下载官方 Caddy、交互设置网站访问密码、设置 Windows 防火墙 80/443，并注册开机运行的任务 `AnotherMe-Hosted-ECS`。网站用户名为 `class`，密码由部署者在服务器上输入；模型 Key 由每位访客自己在网页填写。网站访问密码使用 Caddy 标准密码哈希，防止配置文件被读取时直接泄露明文密码；Git、版本号、数据库约束和普通测试不能提供这种密码存储保护。

5. 在阿里云安全组另行允许 TCP 80 和 443，访问来源按实际课堂范围配置；需要让不固定 IP 的同学访问时可使用 `0.0.0.0/0`。后台 8501 与 Caddy 管理端口 2019 不需要公网放行。
6. 从自己电脑的浏览器打开 `https://120.55.88.165`。首次颁发证书可能需要等待，证书失败时查看 `data\hosted-logs\caddy.log`，不要让访客在证书警告页面填写 API Key。
7. 输入网站访问用户名和密码，在设置页填写自己的 API 地址、Key 与模型型号，测试并保存。可手填模型 ID。主图对话、RAG 重排与自省均使用当前访客所选模型。

重新执行安装器会先停止已有任务及对应后台进程，再更新依赖并启动当前目录的源码；控制台输出 Hosted source 的实际路径。Windows 虚拟环境启动的基础 Python 子进程也会被停止，避免旧进程继续占用 8501。安装器在已有 Caddyfile 时保留原配置。若实例公网 IP 改变，停止任务后修改 `tools\caddy\Caddyfile` 的站点地址和 `default_sni`，再按新 IP 重新执行安装命令；脚本不会替你修改原配置中的地址或访问密码。

## 访客隔离和 Key

身份由浏览器的 Secure、HttpOnly、SameSite=Strict Cookie 识别，Cookie 有效期 30 天，每次访问续期。同一浏览器的多个标签页共用空间；不同浏览器或独立浏览器配置文件互相隔离。这不是实名账号系统，没有跨设备登录或找回入口。清除 Cookie、Cookie 过期、遗失 Cookie 后，原文件仍在服务器，但访客无法再自动进入该空间。

API Key 与 MinerU Token 仅保留在该访客服务的运行内存中，不写入浏览器存储、SQLite 配置或 Windows 共享账户密钥。服务重启、空间闲置 30 分钟后被回收时，需要重新填写；学习文件和会话保留。正在运行的请求或异步任务不会因闲置回收被关闭。服务器管理员仍能够读取进程内存及服务器文件，应只使用自己信任的服务器。

云端模式不读取部署者 `.env` 的模型 Key，不借用部署者的 Codex 登录，不访问旧微信或个人资料库。访客可以调用的模型 API 域名在 `src/aitown/ui/hosted.py` 中列出；这些域名限制位于公网安全边界，防止访客把模型请求指向服务器的环回/VPC 管理服务。类型、数据库事务和普通测试本身不能约束这类网络目标。需要增加服务商时，可在后台启动命令增加 `--allow-api-host 服务商域名`；公开入口仅接受 HTTPS 服务的 443 端口。

这是面向已获得访问密码的课堂访客的演示部署，没有经过公网渗透测试或并发压测，也没有实现个人账号、文件存储配额、计费或管理员控制台。每位访客的空题库需要自行导入或收集课程资料。

## 检查与维护

在服务器检查后台：

```powershell
Invoke-RestMethod http://127.0.0.1:8501/api/health
Get-ScheduledTaskInfo -TaskName AnotherMe-Hosted-ECS
Get-Content .\data\hosted-logs\backend.log -Tail 30
Get-Content .\data\hosted-logs\caddy.log -Tail 30
```

在另一台电脑进行真实验收：HTTPS 无证书警告；不同浏览器分别配置模型 Key、建立会话，确认不能看到对方会话和题库；分别进行一次对话和一次知识库问答。健康接口成功不能证明模型调用或公网证书已通过。

更新时上传本次重新生成的 `AnotherMe-ECS-Windows-Source.zip`，先停止服务并等待后台任务结束，再备份整个 `data\hosted` 和 `data\caddy`。把 ZIP 的 `src/`、`scripts/`、`docs/`、`README.md` 和 `pyproject.toml` 覆盖到原安装目录同一层，不要套入新的子目录；然后在该目录重新执行 `Install-Server.ps1 -PublicIp 你的公网IP`。不要把空数据目录覆盖原目录。

当前首页应显示“我的学习”，首次设置为访客自己的模型 API。页面等待全部延后加载脚本完成才请求初始数据，避免首屏停留在旧个人资料入口。若仍显示旧入口，请在服务器确认 Hosted source 指向当前安装目录，并检查计划任务操作中的脚本路径。ECS 关闭时只能验证本地包，不能据此声称公网已更新。

```powershell
# 停止并取消开机启动
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy\windows\Stop-Server.ps1

# 恢复运行和开机启动
Enable-ScheduledTask -TaskName AnotherMe-Hosted-ECS
Start-ScheduledTask -TaskName AnotherMe-Hosted-ECS
```

## IP HTTPS 与接入条件

Caddy 使用 Let's Encrypt 的 `shortlived` ACME 配置为公网 IP 申请有效期约六天的证书，并自动续期；80/443 必须能被证书验证服务器访问，ECS 必须能访问 ACME 服务。配置了 `default_sni` 以支持不发送 IP SNI 的客户端。此仓库本机检查不代表阿里云上已颁证或公网访问已通过。

当前实例位于杭州。公开 Web 服务是否满足阿里云接入和备案要求，需要按阿里云当前规则确认；IP 访问和加密证书本身不能替代适用的备案要求。若阿里云拦截，应按平台指引处理，而不是修改端口规避。

官方资料：[Windows 远程连接](https://help.aliyun.com/zh/ecs/user-guide/connect-to-a-windows-instance-through-workbench)、[安全组](https://help.aliyun.com/zh/ecs/user-guide/start-using-security-groups)、[Caddy TLS 配置](https://caddyserver.com/docs/caddyfile/directives/tls)、[IP 证书说明](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)、[阿里云备案要求](https://help.aliyun.com/zh/dns/pubz-filing-domain-name-related-faq)。
