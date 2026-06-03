# 设计：模板引擎 + frontmatter schema

## Motivation

"标准化网络打印服务"意味着调用方（station、内网工程师、未来其他服务）不能每次都靠看 ZPL 源码猜要传什么参数。我们需要：

1. **可发现**：`GET /info` / `GET /templates/{name}` 能告诉调用方"这个模板要哪些字段、类型、是否必填、默认值"
2. **保留 ZPL 全自由度**：不要发明 DSL，调用方/设计师能用任意 ZPL 指令（`^GF` 位图、`^FB` 块状文字、`^FR` 反色都得支持）
3. **零工具链**：模板就是 `.zpl` 文本文件，能用 ZebraDesigner / Labelary playground / 任意编辑器编辑

## Proposed Solution

模板 = "frontmatter 声明 + 任意 ZPL + `{{var}}` 占位符"。

### Frontmatter 语法

用 ZPL 已经不识别的 `;;` 行打头（ZPL 在 `^XA` 之前的内容会忽略），引擎装载时解析：

```
;; @label width=50mm height=30mm
;; @field patient: str required "Patient name"
;; @field qty: int default=1
;; @field date: str
^XA
^CI28
^FO20,20^A0N,30,30^FD{{patient}}^FS
^XZ
```

- `@label` 声明标签物理尺寸（参考；权威值仍来自 env，避免 Pi 间标签换尺寸时全部模板都要改）
- `@field name: type [required] [default=X] ["description"]`
- `{{name}}` 在 body 里做字符串替换

### Schema 自动发现

如果模板**没有 @field 声明**，引擎扫所有 `{{name}}`，自动登记为 `str required`：

```
^XA
^FO20,20^FD{{title}}^FS
^XZ
```

→ `/info` 报告这个模板有一个必填字段 `title: str`。让调用方"丢一个 ZPL 上来就能用"。

### 渲染流程

1. `TemplateStore.get(name)` 读 `.zpl` 文件 → `parse_template()` 得 `Template` 对象
2. `TemplateStore.render(name, data)`：
   - 检查必填字段是否有传、应用默认值
   - 按字段类型 coerce（`str` / `int` / `float` / `bool`）
   - `VAR_RE.sub` 替换 `{{var}}` → 返回完整 ZPL

实现见 `app/templates.py`。

### 内置模板

- `zd411_test` — 打印机自检（字号、Code128、QR、规格）
- `station_v2` — Station V2 设备标签（SN + 条码 + DUID + MID + URL）
- `sample_label` — 最小可用样例

## Alternatives

- **Jinja2**：能解决，但带"任意 Python 表达式"风险，且要装依赖、模板写起来更复杂。我们只需要插值，不需要循环 / 条件 / filter
- **YAML/JSON 元数据 + 单独 schema 文件**：模板和 schema 双文件易脱节。frontmatter 让"声明"和"模板"在同一个文件里，单一事实来源
- **从 ZPL `^FX` 注释里挖**：`^FX` 是合法 ZPL（打印机识别为注释），但在 `^XA` 内部出现，混进了"指令流"，解析复杂。`;;` 在 `^XA` 之前更干净
- **强类型 schema (Pydantic-on-template)**：过度工程；调用方拿到 `/info` 用普通 dict 校验已足够

## Impact

- 新增 `app/templates.py`（150 行）
- 模板都放 `templates/*.zpl`，bind-mount 到容器 `/data/templates`
- `/info` 响应里多 `templates: [{name, fields, label_width_mm, label_height_mm}]`
- 字符串替换**不转义** `^` / `~`：如果业务字段可能含这两个字符，调用方要自清；将来如有需要可在 `/print/template` 加 `escape: true` 选项

## Revision History

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-06-03 | 初版 | 自描述模板引擎 |
