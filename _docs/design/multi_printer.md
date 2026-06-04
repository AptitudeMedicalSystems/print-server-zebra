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

## Revision History

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-06-04 | 初版 | 用户反馈：将来一 Pi 多打印机 + 模板尺寸要能自动匹配可打印机 |
