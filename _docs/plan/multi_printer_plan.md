# Plan: 多打印机 + 模板尺寸自匹配（v0.3.0）

关联：`_docs/design/multi_printer.md`

## Objective

把 print-server 从"单 printer 写死配置"升级到"多 printer 配置 + 模板尺寸自动匹配"。范围：

- 数据模型：单 printer → printers 列表（即便 1 Pi 1 台）
- 模板 `@label` 加 `dpi=`，新增 `compatible_with(printer)` 校验
- API：`/print/*` `/status` 加可选 `printer` 字段；`/info` 重塑为 `printers[]` + `templates[].compatible_printers`
- UI：顶部 printer 下拉，模板↔打印机互相过滤
- 兼容性：旧 env 模式仍可跑（合成单 printer `name=default`），旧客户端不传 `printer` 仍走 default

不在本期范围：
- Fleet 视图聚合（由外部消费者做，不进 print-server）
- 中心 print-router 服务
- CUPS 替换

## Tasks

| # | Phase | Task | Status |
|---|---|---|---|
| 1 | Design | `_docs/design/multi_printer.md` | done (f13dc80) |
| 2 | Design | 把 dpi 字段加到 `@label` 文法 | todo |
| 3 | Build | `config.py` 引入 `Printer` dataclass + `load_printers()`（yaml + env 回退） | todo |
| 4 | Build | `printer.py` 参数化（接 `Printer`，每台一把 flock） | todo |
| 5 | Build | `templates.py` 解析 dpi + `compatible_with()` | todo |
| 6 | Build | `main.py` `/info` 重塑 + `/print/*` 加 `printer` 字段 + 兼容字段保留 | todo |
| 7 | Build | `printers.example.yaml` + docker-compose 挂卷示例 | todo |
| 8 | UI | `static/index.html` printer 下拉 + 双向过滤 | todo |
| 9 | Docs | `architecture/overview.md` 同步新模型 + env 表更新 | todo |
| 10 | Test | qwh-pi5-c 单 printer 回归（env 模式不挂 yaml） | todo |
| 11 | Test | 第二台 ZD（或虚拟 device）双 printer 验证 | todo |
| 12 | Release | tag `v0.3.0` 触发 Actions → GHCR | todo |
| 13 | Rollout | qwh-pi5-c 切到 v0.3.0；station-v2 stack 验证不受影响 | todo |

## Dependencies

- 现有 `@label` 解析（已在 `app/templates.py`）
- `fcntl.flock` 多锁能力（标准库，零依赖）
- 第二台打印机或虚拟 USB device（task 11 才需要；单台先回归 task 10）

## Open Questions

- **udev 命名**：多打印机时 `/dev/usb/lp0` `lp1` 会漂，是否要在 pi-gen base 写 udev rule 按序列号固定？或者用 `/dev/usb/lp-by-id-XXX`？→ 倾向后者，文档化
- **`compatible_with` 容差**：0.5 mm 还是 0.2 mm？标签卷误差通常 0.3 mm 内，先取 0.5 留余量
- **Multi-printer `/preview`**：preview 跟 printer 无关（Labelary 只渲染 ZPL），但 UI 要不要让用户先选 printer 再 preview？倾向不绑定，preview 是模板的属性
- **API 失败语义**：传不存在的 `printer` → 404 还是 400？倾向 400（请求语义错），但要明确

## [Post] Results

待执行后填写。

## [Post] Follow-up

待执行后填写。
