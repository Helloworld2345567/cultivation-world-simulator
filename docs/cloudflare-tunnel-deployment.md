# Cloudflare Tunnel 公网部署

本文档将修仙世界模拟器安全发布到 `https://world.ym0v0.com`。公网入口只有 Cloudflare Tunnel：后端不发布宿主端口，前端仅绑定宿主回环地址 `127.0.0.1:8123`，`cloudflared` sidecar 通过 Docker 内部服务名 `http://frontend:80` 访问 Nginx。

该方案不会自动登录 Cloudflare、创建 Tunnel 或修改 DNS。Cloudflare 侧的 Tunnel、Public Hostname 与 DNS 仍需由账号管理员在 Dashboard 中完成。

## 架构与安全边界

```text
Internet
   |
Cloudflare HTTPS edge: world.ym0v0.com
   |
cloudflared container (outbound-only tunnel)
   |
frontend Nginx :80 ───── backend :8002
   |
127.0.0.1:8123 (local health check only)
```

- `backend` 没有 `ports`，只能由 `frontend` 在 Docker 私有网络中访问。
- `cloudflared` 不加入后端网络，不能绕过 Nginx 直接访问后端。
- `frontend` 的宿主端口固定绑定 `127.0.0.1`，局域网和公网无法直连。
- Cloudflare Tunnel 是出站连接，无需路由器端口转发或公网 IP。
- 公网 Compose 强制要求 `CWS_ADMIN_PASSWORD`、`CWS_ADMIN_SESSION_SECRET` 和 `CLOUDFLARE_TUNNEL_TOKEN`；缺少任一项时 Compose 会拒绝启动。
- 公网栈仅在 Cloudflare Tunnel 边界内启用 `CF-Connecting-IP` 作为登录限流来源；普通本地运行默认不信任可伪造的转发头。
- `CWS_ADMIN_COOKIE_SECURE=1` 强制管理员会话 Cookie 只通过 HTTPS 发送，`CWS_ALLOWED_ORIGINS=https://world.ym0v0.com` 将浏览器跨域来源收敛到正式域名。
- `CWS_DISABLE_AUTO_PAUSE=1` 防止最后一位公网访客断开 WebSocket 时自动暂停世界；`CWS_DISABLE_AUTO_SHUTDOWN=1` 防止服务随无人连接而退出。
- 管理员密码、会话签名密钥和 Tunnel token 都是高敏感凭据。拥有 Docker 管理权限的用户仍可读取容器环境变量，因此 Docker 主机本身必须是受信任的管理边界。

## 1. 前置条件

1. `ym0v0.com` 已托管到 Cloudflare。
2. 主机已安装 Docker 与 Docker Compose；建议先运行 `docker compose version`。
3. 在 Cloudflare Zero Trust Dashboard 的 **Networks > Tunnels** 创建一个 remotely managed Cloudflared Tunnel，并取得一次性展示的 Tunnel token。
4. 在该 Tunnel 的 **Public Hostnames** 中添加：
   - Hostname：`world.ym0v0.com`
   - Service type：`HTTP`
   - URL：`http://frontend:80`
5. 不要把 origin 配成 `localhost:8123`。对 sidecar 而言，`localhost` 指 cloudflared 容器本身；正确地址是 Docker 服务名 `frontend:80`。

WebSocket 会沿同一 Public Hostname 转发。若 Cloudflare 账号中曾显式关闭 WebSockets，需要在 Network 设置中重新启用。不要为 `/api/*` 或 `/ws` 创建“Cache Everything”规则。

宿主机无需安装 `cloudflared` CLI；Compose 会运行官方容器。本机 CLI 只在需要做 Cloudflare 账户诊断时才是可选项。

Compose 默认使用官方 `cloudflared 2026.8.2`（构建于 2026-08-14），并固定到多架构 RepoDigest `cloudflare/cloudflared@sha256:0aa26e284f05e6c77ae375b8c9c11d9eb6a448fb7bcd8d40f31cb6176189eb38`，避免 `latest` 或版本标签漂移。后续升级可在仓库外环境文件中通过 `CLOUDFLARED_IMAGE` 覆盖，但应先核对官方镜像清单并更新契约测试。

## 2. 准备运行时秘密

以 [deploy/cloudflare.env.example](../deploy/cloudflare.env.example) 为模板，在仓库外创建真实环境文件。例如 Windows 可放到：

```text
C:\Users\<你的用户名>\.config\cultivation-world\cloudflare.env
```

Linux 可放到：

```text
/etc/cultivation-world/cloudflare.env
```

填写三个独立的随机秘密：

- `CWS_ADMIN_PASSWORD`：管理员登录密码；
- `CWS_ADMIN_SESSION_SECRET`：至少 32 个字符，用于签名会话，不应与密码相同；建议由密码管理器生成不少于 32 个随机字节后编码得到；
- `CLOUDFLARE_TUNNEL_TOKEN`：Dashboard 为该 Tunnel 提供的 token。

示例中的 `CWS_ALLOWED_ORIGINS=https://world.ym0v0.com` 不是秘密，但必须与实际 Public Hostname 保持一致。多个可信来源使用逗号分隔；不要填写 `*`。

环境文件应仅允许部署账号读取。建议使用密码管理器生成值。不要把真实值放进仓库内的 `.env`、命令示例、截图、Issue 或聊天记录。仓库的 Docker 构建上下文是项目根目录，把“已被 Git 忽略”的秘密文件留在仓库内仍可能把它发送给 Docker daemon，因此真实环境文件必须放在仓库外。

## 3. 部署

以下 PowerShell 示例中的环境文件路径按实际位置修改：

```powershell
$CwsEnvFile = 'C:\Users\<你的用户名>\.config\cultivation-world\cloudflare.env'

docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml config --quiet
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml pull cloudflared
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml build
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml up -d
```

Linux 命令等价，只需把 `$CwsEnvFile` 替换为环境文件绝对路径。

首次构建可能需要下载 Python、Node、Nginx 和 cloudflared 镜像。部署后不要再启动基础 `docker-compose.yml`，两个栈会争用同一数据目录和端口。

## 4. 验证

先确认容器及 Tunnel 连接：

```powershell
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml ps
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml logs --tail 100 cloudflared
```

`cloudflared` 日志应出现已注册的 tunnel connection，且不应持续重连或报 token/ingress 错误。

验证本机回环入口：

```powershell
Invoke-RestMethod http://127.0.0.1:8123/api/health
```

验证公网 DNS、HTTPS 与公共查询：

```powershell
Resolve-DnsName world.ym0v0.com
Invoke-RestMethod https://world.ym0v0.com/api/health
Invoke-RestMethod https://world.ym0v0.com/api/v1/query/runtime/status
```

还应人工确认：

1. 未登录访客可以浏览公开世界信息；
2. 未登录请求不能调用命令、敏感设置或存档接口；
3. 管理员能登录、执行一次受控操作并正常退出；
4. 浏览器开发者工具中的 WebSocket 连接保持在线；
5. `docker compose ... port backend 8002` 不返回宿主映射；
6. 从局域网另一台机器访问 `<宿主机局域网 IP>:8123` 失败。

不要为了验证鉴权而对正在运行的重要世界发送可能成功的破坏性命令。优先使用只读会话状态、测试环境或仓库自动化测试。

## 5. 备份、升级与凭据轮换

所有用户设置、密钥、存档和日志位于宿主机 `docker-data`。做一致性备份时先暂停该栈，复制整个目录，再恢复服务：

```powershell
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml stop
# 使用你的备份工具复制 docker-data；不要把备份提交到 Git。
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml start
```

升级前保留上一版本代码/镜像和 `docker-data` 备份。若更新 cloudflared 镜像：

```powershell
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml pull cloudflared
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml up -d cloudflared
```

若 Tunnel token 泄露，在 Cloudflare Dashboard 中立即轮换 token，更新仓库外环境文件，然后重建 cloudflared 容器。管理员密码或会话密钥泄露时也应立即轮换；更换会话密钥会使现有管理员会话失效，这是预期行为。

## 6. 停止与回滚

紧急切断公网入口但保留本机服务：

```powershell
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml stop cloudflared
```

完整停止公网栈：

```powershell
docker compose --env-file $CwsEnvFile -f docker-compose.cloudflare.yml down
```

`down` 不会删除绑定挂载的 `docker-data`；不要手工删除该目录。随后切回上一份已验证的代码/Compose 文件，先执行 `config --quiet`，再重新 `up -d`。若改回仓库原始 `docker-compose.yml`，注意它会把后端 `8002` 和前端 `8123` 发布到所有宿主接口，必须先用主机防火墙限制访问。

如需永久撤销公网访问，还应在 Cloudflare Dashboard 中删除 `world.ym0v0.com` 的 Public Hostname，并撤销或删除对应 Tunnel。停止容器本身不会删除 Cloudflare 侧配置。

## 常见问题

- **Tunnel 显示 healthy，但域名返回 502**：Public Hostname origin 应为 `http://frontend:80`；检查 `frontend` 健康状态和 cloudflared 日志。
- **域名存在重定向循环或安全 Cookie 异常**：确认正在使用 `deploy/nginx.cloudflare.conf`，它会保留 Cloudflare 传入的 `X-Forwarded-Proto`。
- **本机 8123 可访问，其他机器也能访问**：这是异常配置；检查 Compose 展开结果必须是 `127.0.0.1:8123:80`。
- **Compose 提示缺少变量**：使用 `--env-file` 指向仓库外的真实环境文件，并确认三个必需秘密均非空。
- **需要换域名**：在 Dashboard 修改 Public Hostname，并同步修改 `CWS_PUBLIC_HOSTNAME` 元数据与 `CWS_ALLOWED_ORIGINS`；无需改 cloudflared 容器的 origin 服务名。
