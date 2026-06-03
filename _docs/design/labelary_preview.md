# 设计：Labelary 多标签预览

## Motivation

UI 上希望"打之前看效果"——不要打废纸。但本地写完整 ZPL 渲染器是 1–2 周工程；Labelary 公开 API 已经覆盖了几乎所有 ZPL 指令。需要一个**最小代价**的预览路径，且支持单 ZPL 含**多张 `^XA…^XZ`** 的情况（Station V2 一次打多个设备标签的场景）。

## Proposed Solution

1. **服务端 `/preview` 端点**：接 `{zpl}`，无需 token（纯渲染，无副作用）
2. **dry_run 链路**：所有 `/print/*` 端点新增 `dry_run: bool`；为 `true` 时跳过 USB 写 + 跳过 token，返回 `{zpl, bytes}`
3. **前端两步走**：UI 调 `/print/<type>?dry_run=true` 得 ZPL → 把 ZPL 转给 `/preview` 得图

### 多标签处理

Labelary URL 路径里含 0-based label index，一次请求只返一张图。处理：

```python
def render_all_pngs(zpl):
    first, total = _fetch(0, zpl_bytes)  # 读响应 X-Total-Count
    if total <= 1:
        return [first]
    with ThreadPoolExecutor(max_workers=8) as pool:
        rest = pool.map(lambda i: _fetch(i, zpl_bytes), range(1, min(total, MAX)))
    return [first, *rest]
```

- 第一次请求 `index=0`，读 `X-Total-Count` 知道总数
- 多于 1 张时并发拉余下 index（线程池 max 8）
- 硬上限 `_MAX_LABELS=16`，防恶意 ZPL 引爆出网请求

### 响应格式

统一 JSON（不论单/多标签）：
```json
{ "count": 2, "images": ["data:image/png;base64,iVBOR...", "data:image/png;base64,..."] }
```

前端纵向叠放，每张带 `label N / total` 小标签。

## Alternatives

- **本地 ZPL 渲染器（Canvas 子集）**：1 天 MVP + 几天补 `^FB` / `^FR` / `^GFA`。完全离线但永远跟不上 ZPL 指令集
- **自托管 Labelary**：他们不开源
- **PDF 多页（`Accept: application/pdf`）**：Labelary 原生支持，一次返回多页。前端用 `<embed>` 内联 PDF 体验飘忽，列表式 PNG 更可控
- **不实现 preview**：用户体验差，调试模板非常痛苦

## Impact

- 新增 `app/preview.py`
- `app/main.py`：新增 `/preview` 端点 + 所有 `/print/*` 加 `dry_run` 字段 + 配套 token 旁路
- `app/config.py`：`PREVIEW_ENABLED`、`LABELARY_URL`、`LABELARY_TIMEOUT`
- 前端 `static/index.html`：每个 tab 多 `Preview` 按钮 + 预览栏（preview_enabled=false 时隐藏）
- **隐私**：调用 `/preview` = 把 ZPL 发到 `api.labelary.com`。当前模板都不含 PII；如果将来要打病人姓名，`PREVIEW_ENABLED=false` 一关或改本地渲染器

## Revision History

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-06-03 | 初版（单标签） | 接 Labelary |
| 2026-06-03 rev 2 | 加多标签分页 | 用户报 bug：双 `^XA` 只渲染第一张 |
