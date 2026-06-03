# Architecture Overview

> 活文档。代码或部署方式变了就回来更新这里。

## System Overview

`print-server` 是局域网通用 ZPL 打印服务，把单台 Zebra ZD411（USB 直连 Pi）暴露成 HTTP 接口，供 Station V2 工位、内网工程师、未来其他服务共用。**自描述**（`GET /info` 暴露标签尺寸、模板及字段 schema）+ **可标准化 fleet 部署**（GHCR 镜像 + Pi 上 docker compose pull）。

跟 `station-v2-docker/printer-service` 的关系：那个服务只服务 station-v2 内部、只能打病人标签、不对外。`print-server` 是新独立服务，端口 8088，与老服务并存；中长期老服务的"写 `/dev/usb/lp0`"会迁成"调 `print-server` 的 HTTP API"。

## Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  Pi (qwh-pi5-c)                                              │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  print-server container (host network, :8088)        │    │
│  │                                                      │    │
│  │  ┌──────────┐    ┌──────────────┐   ┌──────────┐    │    │
│  │  │ FastAPI  │───▶│ TemplateStore│   │ preview  │    │    │
│  │  │  (main)  │    │   (engine)   │   │(Labelary)│    │    │
│  │  └────┬─────┘    └──────────────┘   └────┬─────┘    │    │
│  │       │                                  │          │    │
│  │       ▼                                  ▼          │    │
│  │  ┌──────────┐                       公网 HTTPS      │    │
│  │  │ printer  │  flock                                │    │
│  │  │ (USB IO) │ ──────▶ /var/lock/zd411.lock          │    │
│  │  └────┬─────┘                                       │    │
│  └───────┼──────────────────────────────────────────────┘    │
│          ▼ /dev/usb/lp0                                      │
│       Zebra ZD411 (USB)                                      │
└──────────────────────────────────────────────────────────────┘
            ▲                  ▲
            │                  │
   curl / station 调用    浏览器访问 /ui/
```

## Data Flow

**打印请求**：
1. 调用方 POST `/print/template`（或 `/print/table`、`/print/raw`、`/print/text`）
2. `main.py` 校验 token（如启用），分发到对应 handler
3. handler 调 `TemplateStore.render()` 或 `table.render_table()` 生成 ZPL 字符串
4. `printer.send_zpl()` 获取 `flock` → 打开 `/dev/usb/lp0` → 写字节 → 释放锁
5. 返回 `{success, bytes, copies}`

**预览请求**：
1. UI 点 Preview → 前端调对应 `/print/*` 加 `dry_run: true` 得到 ZPL（不打、不要 token）
2. 前端再 POST `/preview` 把 ZPL 转给服务端
3. `preview.render_all_pngs()` 先用 `index=0` 请求 Labelary 拿到 `X-Total-Count`，多于 1 张时并发拉余下 index
4. 服务端返回 `{count, images:[data:image/png;base64]}`，UI 叠图显示

**自描述**：
1. 任何调用方 `GET /info` → 立即返回打印机型号 / dpi / 标签 mm 与 dots / 模板清单 + 每个模板的 `@field` schema
2. 模板的 frontmatter 注释（`;; @field` 等行）由 `templates.parse_template()` 在装载时解析

## Interfaces

| 类型 | 接口 | 用途 |
|---|---|---|
| HTTP | `GET /healthz` | k8s/docker healthcheck |
| HTTP | `GET /info` | 自描述（打印机 + 标签 + 模板 + 是否启用 preview） |
| HTTP | `GET /status` | 实时 `~HQES` 状态查询（缺纸 / 头开 / 暂停等） |
| HTTP | `GET /templates`, `GET /templates/{name}` | 模板列表 + 单模板含 body |
| HTTP | `PUT /templates/{name}`, `DELETE` | 上传 / 删模板（token） |
| HTTP | `POST /print/template`, `/print/table`, `/print/raw`, `/print/text` | 打印；`dry_run:true` 时返回 ZPL 不打 |
| HTTP | `POST /preview` | ZPL → 多 PNG（Labelary 代理） |
| 静态 | `GET /ui/` | 单页前端（4 个 tab + 预览） |
| 外向 HTTP | `api.labelary.com` | 预览渲染（`PREVIEW_ENABLED=false` 关闭） |
| 文件 | `/dev/usb/lp0` (rw) | USB 写 ZPL；`flock` 串行 |
| 文件 | `/var/lock/zd411.lock` | 跨容器/进程串行写入打印机 |
| 文件 | `/data/templates/*.zpl` | 模板存储（容器内路径，bind-mount 到 host `./templates`） |

## Tech Stack

- **运行时**：Python 3.11-slim（多架构镜像 linux/arm64 + linux/amd64）
- **Web**：FastAPI 0.115 + Uvicorn 0.30
- **数据**：Pydantic 2.9（请求/响应模型）
- **打印机交互**：标准库 `fcntl.flock` + 二进制写 `/dev/usb/lp0`
- **预览代理**：标准库 `urllib`（无新依赖）+ `concurrent.futures` 并发
- **容器**：Docker（host network、`--device /dev/usb/lp0`）
- **构建**：GitHub Actions + buildx，`v*` tag 触发推 GHCR

## Deployment

| 项 | 值 |
|---|---|
| 镜像 | `ghcr.io/aptitudemedicalsystems/print-server-zebra:<version>` |
| 端口 | `8088`（host network） |
| 启动 | `docker compose up -d`（参见根目录 `docker-compose.yml`） |
| 凭证 | Classic PAT (`read:packages`) 烧进 Pi 的 `~pi/.docker/config.json` |
| 一键 setup | `GHCR_TOKEN=... bash <(curl -fsSL https://raw.githubusercontent.com/AptitudeMedicalSystems/print-server-zebra/main/setup.sh)` |

**关键环境变量**（详见 `app/config.py`）：

| env | 默认 | 说明 |
|---|---|---|
| `PORT` | `8088` | HTTP 端口 |
| `LABEL_WIDTH_MM` / `LABEL_HEIGHT_MM` | `50.8` / `50.8` | 标签物理尺寸（Pi 间可不同） |
| `PRINTER_DPI` | `203` | 决定 dots/mm 换算 |
| `DEVICE_PATH` | `/dev/usb/lp0` | USB 字符设备路径（空 = 自动发现） |
| `LOCK_PATH` | `/var/lock/zd411.lock` | flock 路径 |
| `PREVIEW_ENABLED` | `true` | 关掉 = `/preview` 返 404 |
| `LABELARY_URL` | `https://api.labelary.com` | 预览后端 |
| `PRINT_API_TOKEN` | 空 | 非空时写/打印端点要 `Authorization: Bearer` |
| `TEMPLATES_DIR` | `/data/templates` | 模板挂卷路径 |
