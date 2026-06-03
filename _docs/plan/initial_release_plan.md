# Plan: Initial Release v0.2.0

## Objective

把"通用网络打印服务"从想法落到 qwh-pi5-c 上跑起来，并完成 fleet 级标准化发布通道。范围包括：

- 独立 FastAPI 服务（与 station-v2 `printer-service` 物理隔离）
- 自描述 + 模板引擎 + 表格 + Labelary 预览
- 单文件前端 UI
- GitHub 公开仓 + Actions tag-触发的 GHCR 镜像发布
- 一台 Pi 上端到端验证（含真打）

## Tasks

| # | Phase | Task | Status |
|---|---|---|---|
| 1 | Probe | SSH 上 qwh-pi5-c 摸清环境（docker / USB / 已有服务） | done |
| 2 | Design | API 表面 + 模板 schema + flock 共存方案 | done |
| 3 | Build | FastAPI + ZPL 渲染 + flock + 模板引擎 | done |
| 4 | Containerize | Dockerfile + compose.yml | done |
| 5 | Deploy | rsync + build + up + 真打 ZD411 test | done |
| 6 | UI | 单文件前端（4 tab） | done |
| 7 | Templates | 加 `station_v2` 模板 | done |
| 8 | Preview | Labelary 代理 + dry_run + 多标签分页 | done |
| 9 | CICD | GitHub Actions buildx 推 GHCR | done |
| 10 | Visibility | GHCR package public（被 org policy 阻断） | blocked |
| 11 | Credentials | 改用 Classic PAT 烧 Pi | done |
| 12 | Pi cutover | compose 改成 pull 镜像 + 验证 | done |
| 13 | Docs | 按 DOC_GUIDE 补 `_docs/` | done |

## Dependencies

- qwh-pi5-c 上有 docker + docker compose v2 + ZD411 接好（站 V2 已经准备好）
- GitHub org `AptitudeMedicalSystems` 可访问
- GHCR 私有包能用 PAT 拉

## Status

完成。v0.2.0 已在 GHCR、qwh-pi5-c 已切到 pull 模式。

## [Post] Results

**成功**：
- `/info` 自描述生效（型号、dpi、标签尺寸、模板含 schema、preview flag）
- 三种内置模板（zd411_test / station_v2 / sample_label）落地
- 多标签预览修好（之前 bug：双 `^XA` 只渲染第一张）
- GitHub Actions buildx 多架构构建跑通 ~3 分钟
- Pi 上 `compose pull && up -d` 切到 GHCR 镜像无回归

**计划偏差**：
- GHCR public 不可行（org policy 限制 + fine-grained PAT UI 找不到 packages 项）→ 退到 Classic PAT。文档化在 `design/fleet_deployment.md`
- SSH-key broker 延后到将来研究（见 memory + design 备忘）

## [Post] Follow-up

- [ ] **凭证轮换**：当前用 Weihao 个人 PAT。建议尽快换 bot 账号 + 长期 PAT
- [ ] **pi-gen base 集成**：写 `~pi/.docker/config.json` 进 base image，新 Pi 烧完即用，不用跑 setup.sh
- [ ] **老 printer-service 加 flock**：让 station-v2 也获 `/var/lock/zd411.lock`，彻底解决并发风险
- [ ] **老 printer-service 改用 HTTP**：中长期，station 调 `:8088/print/template` 而不是直写 USB
- [ ] **CI 测试**：main push 时跑 ruff + 容器起后 `curl /healthz`（目前只 release tag 触发，main push 无校验）
- [ ] **本地 ZPL 渲染器**：将来打 PII 标签时换掉 Labelary
