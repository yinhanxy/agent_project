# P5b 知识缺口页 走查 Runbook

> 用途：验证 Phase 5b 前端知识缺口页（列表 / 状态筛选 / 改状态 / 入口）。
> 适用：P5b 已合并 master，直接跑**主仓库**服务即可（无需 worktree，天然避开 dev server 路径错位）。

## 关键裁剪

- 缺口页走查**只依赖 MySQL + Redis + Django + 后端 + 前端**；列表/筛选/改状态只查 MySQL，**不碰** Ollama/Milvus/向量检索，那些可不启动。
- `AGENT_ENGINE` 对缺口页 CRUD 无关，可不设（默认 loop 即可）。
- 缺口页 CRUD 不经 Agent 流式；只有想验证「聊天问超纲问题→自动记缺口」的端到端链路时，才需要再起 Ollama + 向量库 + `AGENT_ENGINE=graph`（见文末）。

## 前提（首次走查前确认；本机已全部满足）

- `DjangoUserService\.venv`、`backend\.venv`（uvicorn）、`front\node_modules` 均存在
- 重排序模型 `D:\Hugging_Face\models\Qwen3-Reranker-0.6B` 存在（后端启动检查）
- Docker 可用（用于起 Redis）
- MySQL57 服务 Running（3306）

## 1. 全栈启动脚本（PowerShell，整段一次粘贴）

```powershell
$root = "D:\source\agent\LangChain-RAG-FastAPI-Service"
$logRoot = "$root\log"
New-Item -ItemType Directory -Force "$logRoot\django","$logRoot\backend","$logRoot\frontend" | Out-Null

# ── 1. 前置：MySQL（应已在跑）+ Redis（后端启动初始化需要）──
& cmd /c "sc query MySQL57" | Select-String "STATE"
if (-not (Test-NetConnection localhost -Port 6379 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    docker run -d --name redis -p 6379:6379 redis:alpine    # 重跑脚本时改用 docker start redis
}

# ── 2. Django 用户服务 8001（登录/JWT 必需，清代理）──
$d = New-Object System.Diagnostics.ProcessStartInfo
$d.FileName = "cmd.exe"
$d.Arguments = "/c set HTTP_PROXY=& set HTTPS_PROXY=& set http_proxy=& set https_proxy=& `"$root\DjangoUserService\.venv\Scripts\python.exe`" manage.py runserver 127.0.0.1:8001 > `"$logRoot\django\django.log`" 2>&1"
$d.WorkingDirectory = "$root\DjangoUserService"; $d.UseShellExecute = $false; $d.CreateNoWindow = $true
[System.Diagnostics.Process]::Start($d) | Out-Null

# ── 3. FastAPI 后端 8000（缺口 API；清代理；首次启动自动建 knowledge_gaps 表）──
$b = New-Object System.Diagnostics.ProcessStartInfo
$b.FileName = "cmd.exe"
$b.Arguments = "/c set HTTP_PROXY=& set HTTPS_PROXY=& set http_proxy=& set https_proxy=& `"$root\backend\.venv\Scripts\uvicorn.exe`" main:app --host 127.0.0.1 --port 8000 --reload > `"$logRoot\backend\fastapi.log`" 2>&1"
$b.WorkingDirectory = "$root\backend"; $b.UseShellExecute = $false; $b.CreateNoWindow = $true
[System.Diagnostics.Process]::Start($b) | Out-Null

# ── 4. 前端 3000（首次无 node_modules 会自动装）──
if (-not (Test-Path "$root\front\node_modules")) { npm install --prefix "$root\front" }
$f = New-Object System.Diagnostics.ProcessStartInfo
$f.FileName = "cmd.exe"
$f.Arguments = "/c npm run dev > `"$logRoot\frontend\frontend.log`" 2>&1"
$f.WorkingDirectory = "$root\front"; $f.UseShellExecute = $false; $f.CreateNoWindow = $true
[System.Diagnostics.Process]::Start($f) | Out-Null

# ── 5. 等待并检查 ──
Start-Sleep 15
"--- Django ---"; Get-Content "$logRoot\django\django.log" -Tail 3
"--- FastAPI ---"; Get-Content "$logRoot\backend\fastapi.log" -Tail 5
"--- 前端 ---"; Get-Content "$logRoot\frontend\frontend.log" -Tail 5
@(8001,8000,3000) | ForEach-Object {
    $ok = Test-NetConnection localhost -Port $_ -InformationLevel Quiet -WarningAction SilentlyContinue
    "端口 $_ : $(if($ok){'✅'}else{'❌'})"
}
```

确认 `fastapi.log` 尾部出现 `Application startup complete`、三个端口都 ✅ 再继续。

## 2. 插测试缺口数据（SQL，在 MySQL 客户端执行，非 PowerShell）

后端首次启动建好 `knowledge_gaps` 表后，在 `chat_history` 库执行（**走查建议用管理员账号登录**，管理员看全部，故 `user_id` 可随便填）：

```sql
USE chat_history;
INSERT INTO knowledge_gaps (user_id, dept_id, title, question, category, suggested_content, status, created_at, updated_at) VALUES
('test-user', NULL, '远程设备报销', '远程办公设备损坏怎么报销', '财务报销', '1.哪些设备可报销 2.是否需审批 3.需提交的证明材料', 'pending', NOW(), NOW()),
('test-user', NULL, '试用期年假', '试用期能否休年假',         '人事',     '1.试用期年假资格 2.折算方式',                       'reviewed', NOW(), NOW());
```

（要测「普通用户只看自己」时，把 `user_id` 换成该普通账号真实的 user_id。）

## 3. 走查清单

浏览器开 `http://localhost:3000`，登录后：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 进「我的」页 | 看到「知识缺口」入口；管理员账号还看到「知识缺口管理」 |
| 2 | 点入口进 `/knowledge-gaps` | 管理员看全部、普通用户只看自己的缺口 |
| 3 | 切顶部 Tabs（待处理/已查看/…） | 列表按状态筛选 |
| 4 | 点某条「改状态」→ 选「已解决」 | Toast「状态已更新」+ 列表刷新 + 刷新页面后状态保持 |
| 5 | 切到无结果的 Tab | 显示「暂无知识缺口」空态 |
| 6 | （可选）普通账号改他人缺口 | Toast「无权修改」 |

## 4. 注意点

- 启动脚本整段一次粘贴，别拆开漏粘 `ProcessStartInfo` 段。
- SQL 单独在 MySQL 客户端跑，不要粘进 PowerShell。
- 重跑脚本时 Redis 那行改 `docker start redis`（容器已存在）。
- 若 8000/8001/3000 已被占用：先确认是不是旧实例（`http://localhost:8000/` 是否 200），或用文末关停脚本清掉再起。

## 5. 关停

```powershell
@(8001,8000,3000) | ForEach-Object {
    $c = Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { taskkill /PID $c.OwningProcess /F }
}
```

## 6. 与其他项目并存（8000 被占时，本项目改用 8010）

`vite.config.js` 已支持环境变量覆盖（默认 3000/8000/8001 不变）。当 8000 被你另一个项目占用，让本项目后端跑 8010、前端代理指向 8010 即可并存。把第 1 节启动脚本的**第 3、4 段**替换为下面两段（其余不变）：

```powershell
# ── 3'. FastAPI 后端改跑 8010 ──
$b = New-Object System.Diagnostics.ProcessStartInfo
$b.FileName = "cmd.exe"
$b.Arguments = "/c set HTTP_PROXY=& set HTTPS_PROXY=& set http_proxy=& set https_proxy=& `"$root\backend\.venv\Scripts\uvicorn.exe`" main:app --host 127.0.0.1 --port 8010 --reload > `"$logRoot\backend\fastapi.log`" 2>&1"
$b.WorkingDirectory = "$root\backend"; $b.UseShellExecute = $false; $b.CreateNoWindow = $true
[System.Diagnostics.Process]::Start($b) | Out-Null

# ── 4'. 前端，把 /api 代理指向 8010 ──
if (-not (Test-Path "$root\front\node_modules")) { npm install --prefix "$root\front" }
$f = New-Object System.Diagnostics.ProcessStartInfo
$f.FileName = "cmd.exe"
$f.Arguments = "/c set API_TARGET=http://127.0.0.1:8010& npm run dev > `"$logRoot\frontend\frontend.log`" 2>&1"
$f.WorkingDirectory = "$root\front"; $f.UseShellExecute = $false; $f.CreateNoWindow = $true
[System.Diagnostics.Process]::Start($f) | Out-Null
```

自检端口把 8000 换成 8010。Django(8001)、前端(3000)若也与另一项目冲突，同理用 `--port`/`FRONT_PORT`/`USER_TARGET` 错开。

> 注意：`set API_TARGET=...&` 里 `&` 紧贴变量值、无空格——它把设置环境变量和 `npm run dev` 连在同一 cmd 里执行。

## 附：端到端缺口触发（可选，验证真实链路而非只看 UI）

若想验证「聊天问一个超纲问题 → 系统自动记一条缺口」，需额外：
- 起 Ollama（11434）+ 向量库（Milvus 19530 或项目配置的 Chroma）
- 后端启动时设 `AGENT_ENGINE=graph`（在第 3 段 uvicorn 命令前加 `set AGENT_ENGINE=graph& `）
- 然后在聊天页问一个知识库明显没有的问题；注意当前缺口触发对「检索到弱相关文档」不敏感（见 5a 设计的已知边界），真正触发需检索 0 命中/极低置信或 coordinator 明确判定 knowledge_gap。
