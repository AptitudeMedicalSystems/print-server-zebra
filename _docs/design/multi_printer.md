# 设计：多打印机支持 + 模板尺寸自匹配

## Motivation

当前 print-server 一个进程只挂 **1 台** 打印机，配置是 server 级单全局：`LABEL_WIDTH_MM` / `LABEL_HEIGHT_MM` / `PRINTER_DPI` / `DEVICE_PATH` 各只有一份。这套模型在以下场景会出问题：

1. **一台 Pi 接多个打印机**：例如同一台前台同时用 2.25×2 inch（设备标签）和 1×0.5 inch（试管标签），需要两台 ZD411 + 两卷 stock。现在只能开两个独立 print-server 容器，端口/锁文件/compose 都得各开一份，运维复杂。
2. **Fleet 内有不同尺寸 / dpi 的 Pi**：业务侧（station UI 或内网用户）想"选模板→自动打到正确的 Pi"，但目前模板里 `;; @label width=Xmm height=Ymm` 只是元数据声明，**没人校验**，标签卷换错就直接打废。
3. **DPI 信息丢失**：现有 `@label` 只声明 mm，不声明 dpi，但 203 dpi 模板上 300 dpi 打印机会变得很小（dots 不变 mm 变小）。这个隐患还没爆。

业务上希望前端选模板时，"能打这个模板的打印机"自动浮出来，不能打的灰掉。同样地，选打印机后，能打的模板筛出来。

## Proposed Solution

### 拆分原则：单 server 多 printer 配置 + fleet 聚合外置

- **print-server 内核**：升级数据模型，由"单 printer"改为"多 printer 列表"。即使物理上 1 Pi 还是 1 台打印机，配置/接口结构按数组走。
- **fleet 视图**：不写进 print-server，由外部消费者（station UI / 中控台）并发抓多个 Pi 的 `/info` 拼装。print-server 本身不发现别人。

理由：1 Pi 1 打印机是当前主流拓扑，但数据模型用数组对未来同 Pi 多打印机/网络打印机/虚拟队列零成本兼容；fleet 路由是另一个尺度的问题，应该用更轻的方式（前端聚合）解决，不在打印机内核里搞中心节点 / 发现。

### 配置模型

新增可选 `printers.yaml`（挂卷到 `/data/printers.yaml`），声明每台打印机：

```yaml
printers:
  - name: device-labels        # 唯一 id，URL-safe
    model: Zebra ZD411-203dpi
    device_path: /dev/usb/lp0
    dpi: 203
    label_width_mm: 57.15
    label_height_mm: 50.8
    lock_path: /var/lock/zd411-device.lock
    default: true              # 没指定 printer 时用这个
  - name: tube-labels
    model: Zebra ZD411-300dpi
    device_path: /dev/usb/lp1
    dpi: 300
    label_width_mm: 25.4
    label_height_mm: 12.7
    lock_path: /var/lock/zd411-tube.lock
```

**回退兼容**：`printers.yaml` 不存在时，从现有的环境变量（`LABEL_WIDTH_MM` 等）合成单一打印机 `name: "default"`。旧 Pi 不改 `.env` 也能跑。

每条 printer 有自己的 `lock_path`，互不阻塞；同名锁的容器之间继续 flock 串行（与现有 station-v2 写 `/dev/usb/lp0` 共存方案不变）。

### 模板尺寸/DPI 声明

扩展 `;; @label`：

```
;; @label width=57.15mm height=50.8mm dpi=203
```

`dpi` 字段可选（缺省 = 不校验，能匹配任意 dpi 打印机）。`templates.py` 已经解析 `width/height`，加 `dpi` 一行。

**严格相等匹配（默认）**：打印机 P 兼容模板 T iff
- `abs(P.width_mm - T.width_mm) < 0.5`
- `abs(P.height_mm - T.height_mm) < 0.5`
- T 未声明 dpi 或 `P.dpi == T.dpi`

**宽松匹配（可选 `?fit=loose`）**：允许 `P.width >= T.width` 且 `P.height >= T.height`（用大标签打小模板会有空白，可接受）。dpi 必须严格相等。

模板未声明尺寸 = 兼容所有打印机（向后兼容旧模板，列表里全亮）。

### API 变更

- `POST /print/*` 增加可选字段 `printer: str`。缺省 → 取 `default: true` 的；没有 default 且只有一台 → 用那台；多台无 default → 400。
- `GET /info`：响应 schema 改为
  ```json
  {
    "service": "lan-print-server",
    "version": "0.x.y",
    "printers": [
      { "name": "device-labels", "model": "...", "dpi": 203,
        "label": {"width_mm": 57.15, "height_mm": 50.8, "width_dots": 456, "height_dots": 406},
        "device_path": "/dev/usb/lp0", "connected": true, "default": true }
    ],
    "templates": [
      { "name": "station_v2", "fields": [...],
        "label_width_mm": 57.15, "label_height_mm": 50.8, "label_dpi": 203,
        "compatible_printers": ["device-labels"] }
    ],
    "preview_enabled": true
  }
  ```
  顶层 `printer` / `label` 字段保留作为兼容字段（指向 default printer），旧客户端不挂。
- `GET /status?printer=<name>`：单 printer 的 `~HQES`。无 printer 参数 → 返所有打印机 status dict。
- `POST /preview`：不变（与物理打印机无关）。

### 内部模块改动

| 模块 | 变更 |
|---|---|
| `config.py` | 新增 `Printer` dataclass + `load_printers()`（先读 yaml，回退 env） |
| `printer.py` | `send_zpl()` / `query_status()` 加 `printer: Printer` 参数，每台一把 flock |
| `templates.py` | `LABEL_RE` 加 `dpi=` 捕获；`Template` 新增 `label_dpi` 字段；新增 `compatible_with(printer) -> bool` |
| `main.py` | 路由读 `printer` 字段，加 404/400 处理；`/info` 重塑响应 |
| `static/index.html` | 顶部加 printer 下拉；选模板→自动过滤可用 printer 并默认选第一个；选 printer→过滤模板 |
| `docker-compose.yml` | 多卷 `--device /dev/usb/lp1` 时按需追加；`printers.yaml` 挂卷 |

### 前端交互

```
[Printer ▾]  device-labels (57.15×50.8 @203dpi)   ← default
             tube-labels   (25.4×12.7 @300dpi)
             [grayed] tube-labels (offline)

[Template ▾] station_v2   ✓ device-labels
             tube_panel   ✓ tube-labels
             [grayed] big_shipping (no compatible printer)
```

选模板 → 如果当前 printer 不兼容，自动切到第一个兼容的；都不兼容时弹"无可用打印机"。

### Fleet 视图（不在本服务内）

未来 station / console 想"看到全 fleet"时：

1. 配置一份 Pi 清单（mDNS 名或 IP 列表）
2. 前端并发 `GET http://<pi>:8088/info`
3. 聚合 `printers` 数组 + `templates` 取并集
4. 按 (printer, template) 兼容矩阵让用户选

这一步**不**在 print-server 里实现，避免 print-server 反向依赖中心节点；同时 fleet 路由策略（按位置 / 按可用性 / 按队列长度）应由业务决定，不应耦合到打印机本身。

## Alternatives

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| **保持现状（1 server 1 printer）+ 多容器** | 改动最少 | 端口管理、锁文件命名、compose 复杂；fleet 端要发现 N 个端口 | ❌ 运维成本随打印机数线性涨 |
| **CUPS 完全替代** | 工业标准，自带队列/驱动 | 引入大依赖；ZPL raw passthrough 反而绕路；preview/template/HTTP API 还要自己加 | ❌ 重 |
| **单 server 多 printer**（本设计） | 一套配置/接口；前端模型干净；fleet 端只发现 Pi 不发现 printer | print-server 数据模型重构；需要回退兼容旧 env | ✅ 采用 |
| **集中 print-router 服务** | fleet 调度策略集中；打印机看 router | 多一个服务 + 单点；router 重启所有打印阻塞 | ❌ 暂不必 |
| **模板尺寸宽松（仅 `>=`）默认** | 模板少一点报错 | 用大标签打小模板浪费 stock 没保护 | ❌ 默认严格，loose 走 query param |

## Impact

### 代码
- `app/config.py`：新增 `Printer` 类 + yaml 加载 + env 回退
- `app/printer.py`：参数化 + 多 lock
- `app/templates.py`：`dpi` 字段 + `compatible_with()`
- `app/main.py`：所有 `/print/*` `/status` 加 `printer` 参数；`/info` 重塑
- `static/index.html`：UI 改造
- 新增 `printers.example.yaml`

### 兼容性
- **旧客户端**：不传 `printer` → 走 default → 与现状一致
- **旧 Pi 部署**：不挂 `printers.yaml` → env 合成单 printer → 现状一致
- **旧模板**：无 `@label` 或只声明 width/height → `label_dpi=None` → 兼容所有 printer

### 版本规划
- `v0.3.0` ship 多 printer 数据模型 + 兼容字段
- `v0.4.0` 视情移除 `/info` 顶层兼容字段（如果 station-v2 已迁完）

### 风险
- USB device 自动发现：多打印机时不能再"随便挑一个 lpN"，必须按 `device_path` 显式指定
- 一 Pi 多 USB 打印机时 `lpN` 设备号可能换：建议 udev rule 固定（或用 `/dev/usb/by-id/...`），文档要写
- station-v2 老 printer-service 没获 lock：与本设计无关，问题继承

## Roadmap

本设计是从"1 Pi 1 printer"到"1 gateway N printer"的第一步。中长期目标是把这个服务定位为 **print gateway**，让轻量客户端按需挑 gateway 发请求。

### 目标拓扑

```
[Pi Zero fleet client] ──┐
[Pi Zero fleet client] ──┼─► subscribe to ──► [print gateway A]  ──► printer 1, 2, 3
[Pi Zero fleet client] ──┤                    [print gateway B]  ──► printer 4
                         └─►                   [print gateway C]  ──► printer 5, 6
                                                     │
                                                     ▼
                                        ZPL render / preview / route
```

### 角色定义

- **Fleet client (Pi Zero)**：轻量节点，只产生**打印意图**（例如"打这个设备标签 / 这张试管标签"），不持有 ZPL/模板/打印机驱动。代码体量低 → Pi Zero 能跑。
- **Print gateway（本服务）**：拥有完整打印机能力——
  1. **预览**：`/preview` (Labelary 或未来本地渲染器)
  2. **ZPL 生成**：`/print/template` `/print/table` `/print/text` 把结构化输入转 ZPL
  3. **路由**：根据模板尺寸/dpi → 兼容的本地打印机；本地无兼容打印机时 502/404，让 client 换 gateway

### Client → Gateway 关系

- "Subscribe" 不一定是真的 pub/sub。最简：client 知道 **N 个 gateway URL**（配置或 mDNS 发现），启动时并发拉每个 `/info`，缓存 `printers[]` + `templates[]`。
- 发打印请求时由 **client 决策选哪个 gateway**（按 template→gateway 兼容矩阵）。这一步在 client 侧实现，对 gateway 透明。
- 模板存储分两层：**built-in 模板**在 gateway（出厂带 + Pi 端可改），**ad-hoc 模板**由 client 发起时随请求体带（`POST /print/raw` 已经支持）。

### Gateway 部署位置：LAN 或 Internet

Gateway 不绑死局域网——根据业务可以是：

| 部署 | 适用场景 | 客户端访问方式 |
|---|---|---|
| **LAN gateway**（当前 qwh-pi5-c） | 同一办公室/楼层内的打印 | mDNS 发现或局域网静态 IP |
| **Internet gateway**（VPS / 公司云服务器） | 跨站点共享打印机；client 不在同一 LAN | 公网域名 + TLS + token；客户端配 URL |

混合也行：同一 client 同时订阅 1 个 LAN gateway + 1 个 internet gateway。client 端选路逻辑不区分——都是"一个 URL + 一份 `/info`"。

### Pi Zero 单向通信约束

**Pi Zero client 只发起出向请求，不接受入向连接**（NAT 后 / 防火墙后 / 漫游场景）。这给整个架构定了几条铁律：

1. **Gateway 不能回调 client**——没有 webhook、没有反向连接。状态由 client 自己**轮询** `/status` 或 `/jobs/<id>`（若引入异步队列）
2. **打印请求必须同步返回结果**（成功 / 失败 / 错误码），client 不依赖后续推送
3. **TLS 终止在 gateway**——client 验证证书；不需要 mTLS（client 没固定 IP，证书签发难管理），用 `PRINT_API_TOKEN`/per-client token 鉴权
4. **发现机制**：
   - LAN gateway → mDNS（`_print-gateway._tcp`）
   - Internet gateway → 静态 URL 列表（写进 client 配置文件 / 环境变量）
   - **不**做反向注册（client 不暴露端口给 gateway 来连）
5. **网络中断容忍**：client 应缓存最后一次拉到的 gateway `/info`，离线时仍能本地判断"哪些 gateway 此前可用"，但实际发请求时直接试发即可——失败就 fail-fast 让上层重试或换 gateway

### 为什么不把路由放到 client

- 每个 client 维护一份"全 fleet 打印机能力表"成本不高（fleet 几十台 Pi 量级），但 ZPL 生成 / preview 渲染 / 模板存储留在中心 gateway 才能保证 client 轻
- gateway 间不互相发现，互相不路由 → 单点故障域 = 单台 gateway，挂一台只影响接它的 client，不会级联

### 与本期设计的关系

`v0.3.0` 多 printer 数据模型是这个 roadmap 的前置条件——gateway 必须能管多 printer，client 才有"挑 gateway"的意义；模板自描述尺寸+兼容 printer 列表也直接为 client 端的"挑 gateway"逻辑供数据。

### 待解决（roadmap 阶段，不在本期）

- LAN gateway 用 mDNS，Internet gateway 用静态清单——是否需要一个统一的"gateway 目录服务"？
- Client SDK：是否要提供一个 Python/JS 客户端库封装"多 gateway 选路 + 单向轮询"逻辑
- Gateway 之间的能力同步：是否需要 gateway 互相 mirror 模板，还是各自独立
- 鉴权：当前 `PRINT_API_TOKEN` 是 gateway 级单 token；多 client + Internet 部署要不要 per-client token
- TLS：Internet 部署时证书签发/续期路径（Let's Encrypt + 反代 / 自签 + 信任根）
- 异步打印队列：如果将来支持"client 提交后立刻断开，回头查结果"，需要 `POST /jobs` + `GET /jobs/<id>`，仍然是 client 主动轮询

## Revision History

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-06-04 | 初版 | 用户反馈：将来一 Pi 多打印机 + 模板尺寸要能自动匹配可打印机 |
| 2026-06-04 | 加 Roadmap | 用户给出 fleet 拓扑长期愿景：Pi Zero client subscribe 多 print gateway |
| 2026-06-04 | Roadmap 补部署位置 + 单向通信约束 | gateway 可在 LAN 也可在 internet；Pi Zero 只出向不接入 |
