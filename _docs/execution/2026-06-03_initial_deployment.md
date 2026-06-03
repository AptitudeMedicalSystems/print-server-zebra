# 2026-06-03 — 初次部署 + v0.2.0 发布

## Date & Ref

- 日期：2026-06-03
- 关联：`plan/initial_release_plan.md`
- Commit：参见 `git log --until=2026-06-04` 上的 `v0.2.0` tag

## Changes

新建仓 + 全栈：
- `app/main.py` — FastAPI 入口
- `app/config.py` — 环境变量
- `app/printer.py` — USB 写 + flock + `~HQES`
- `app/templates.py` — 模板引擎（frontmatter + `{{var}}`）
- `app/table.py` — 表格 → ZPL 渲染
- `app/preview.py` — Labelary 多标签代理
- `static/index.html` — 单文件 UI（Template / Table / Text / Raw / Upload + 预览）
- `templates/{sample_label,zd411_test,station_v2}.zpl`
- `Dockerfile` — python:3.11-slim
- `docker-compose.yml` — host network、`/dev/usb/lp0`、bind-mount 模板和 `/var/lock`
- `docker-compose.dev.yml` — 本地 build override
- `.github/workflows/release.yml` — tag 触发 buildx 推 GHCR
- `setup.sh` — 新 Pi 一键 setup

Pi 端：
- 部署目录 `/home/pi/print-server/`
- 服务地址 `http://192.168.1.7:8088` / `http://qwh-pi5-c.local:8088`
- 容器名 `print-server`
- 跑在 host network 上，端口 `8088`

GitHub 端：
- 公开仓 `AptitudeMedicalSystems/print-server-zebra`
- 私有 GHCR 包 `ghcr.io/aptitudemedicalsystems/print-server-zebra:0.2.0`
- 本次跑通的 Actions run：`release` workflow, run id `26918991535`

## Issues

| 问题 | 解决 |
|---|---|
| qwh-pi5-c 主机名解析不到 | 用 mDNS `.local` 后缀（`qwh-pi5-c.local` = 192.168.1.7） |
| 用户 pi 不在 `lp` 组 | 容器内 `user: "0:0"`（root）写 `/dev/usb/lp0` |
| station-v2 老 printer-service 也写同一 USB | 加 `flock("/var/lock/zd411.lock")` 串行写 |
| Labelary 多 `^XA` ZPL 只返第一张 | `/preview` 改为：probe `index=0` 读 `X-Total-Count` + 并发拉余下 |
| dry_run 时还要求 token 不友好 | 改为 `dry_run=true` 跳过 token 校验 |
| GHCR package 无法 public | org policy 阻断 → 退到 Classic PAT |
| Fine-grained PAT UI 找不到 packages 项 | org 未启用 fine-grained PAT 政策 → 同样退到 Classic PAT |
| 临时 token 进了对话历史 | 计划立刻 revoke + 用 bot 账号重发 |
| 本机 DNS 漂（Tailscale 抖） | 临时切到 1.1.1.1/8.8.8.8 |
| GitHub OAuth token 无 `workflow` scope，推 workflow 被拒 | `gh auth refresh -h github.com -s workflow` |

## Verification

| 检查 | 结果 |
|---|---|
| `docker compose up -d`（local build） | ✅ container Up |
| `/healthz` | ✅ `{"status":"ok"}` |
| `/info` | ✅ ZD411 connected, 406×406 dots, 3 templates |
| 直写 `dd ... > /dev/usb/lp0` | ✅ 671 B 写入，物理出标签 |
| `/print/raw`（用户给的 ZPL） | ✅ 671 B 出标签 |
| `/print/table` 4 行表格 | ✅ 815 B 出标签 |
| `/print/template` station_v2 + 默认值 | ✅ 877 B 出标签 |
| 单标签 `/preview` → Labelary | ✅ 17 KB PNG 406×406 |
| 双标签 ZPL `/preview` | ✅ `count: 2`，两张独立 PNG |
| GitHub Actions release run | ✅ `success`，~3 min |
| Pi 切到 GHCR 镜像后 `/info` | ✅ version 0.2.0 / 3 templates / connected |

## Notes

- 当前 ZD411 是 **2×2 inch = 50.8×50.8 mm**（406×406 dots @ 203 dpi），跟默认 50×30 不一样，已写进 Pi `.env`
- `printer-service` 老服务还在跑（station-v2 stack），8086 端口；本服务 8088。flock 防字节交错，但老服务 **没**获锁——高频时仍可能错位
- Pi 上还在用 Weihao 个人 Classic PAT 做 docker login。**待办**：切 bot 账号 + 烧 base image
- 出网依赖：Labelary（预览）+ GHCR（pull 镜像）。两者都不可达时，服务能跑（已有镜像在本地，preview 失败但打印不受影响）
