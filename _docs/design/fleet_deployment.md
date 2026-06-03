# 设计：Fleet 部署 — GHCR + 共享 Classic PAT

## Motivation

新 Pi 加入 fleet 时要做的事必须最少。运维约束：
- **Pi 端零长期凭证**是理想，但要权衡复杂度
- 不接受"每台 Pi 一把 token"（凭证扩散）
- 不接受 IP 写死的"内网 registry"（registry 主机搬家时全 fleet 改）
- 不接受"latest tag"（fleet 版本无法回滚）

## Proposed Solution（当前阶段）

**镜像分发**：GHCR private package `ghcr.io/aptitudemedicalsystems/print-server-zebra`，由 GitHub Actions 在 `v*` tag 上 buildx 推 `linux/arm64,linux/amd64`。

**Pi 端拉取**：用一把 **Classic PAT**（scope = `read:packages`）烧进 Pi base image 的 `~pi/.docker/config.json`。

**版本管理**：compose 引用具体 tag (`:0.2.0`)，不用 `:latest`；升级 = 改 `.env` 里 `PRINT_SERVER_VERSION` + `compose pull && up -d`。

**一键 setup**：`setup.sh` 接受 `GHCR_TOKEN` env，clone repo → 写 `.env` → docker login → compose pull/up → 健康检查。

### CICD 流程

`.github/workflows/release.yml`：
- 触发：push tag `v*`（或 `workflow_dispatch` 手动）
- 步骤：checkout → QEMU + buildx → GHCR login (`GITHUB_TOKEN`) → docker/metadata-action 产生 tag 集 → docker/build-push-action 多架构推送
- 缓存：`type=gha,mode=max`

### 凭证模式

- **当前**：用户个人 Classic PAT 临时验证。**强烈建议**轮换为：注册 bot 账号 → 邀请进所有相关 org → bot 生成 PAT → 烧进 base image
- 漏点 = 拉所有该 bot 能看到的私有镜像；不能 push、不能动代码
- 撤销 = bot 一键 revoke，全 fleet 失效（已跑容器照常）

## Alternatives

| 方案 | Pi 上凭证 | 集中点 | 工作量 | 否决原因 |
|---|---|---|---|---|
| GHCR public | 无 | 无 | 5 min | org policy 限制，无法公开 |
| Fine-grained PAT | 一个共享只读 token | base image | 15 min | 单 org 限制 + UI 缺 packages 项（org policy） |
| 内网 `registry:2` | 无 | registry 主机 | 30 min | 多一个服务要维护、IP 漂移会牵连全 fleet |
| **Classic PAT**（当前） | 一个共享只读 token | base image | 15 min | ✅ 采用 |
| SSH-key 换 GHCR token broker | 无（用 SSH key） | broker + GitHub App | ~1 hr | 见 `ssh_broker_research.md`（延后） |

## Impact

- 新增 `.github/workflows/release.yml`
- 新增 `setup.sh`（一键 setup）
- `docker-compose.yml` 改为 `image: ghcr.io/...` + `pull_policy: always`
- 新增 `docker-compose.dev.yml`（local build override）
- pi-gen base image **需要**添加：写入 `~pi/.docker/config.json`（生效一次性 login）

## Revision History

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-06-03 | 初版 | GHCR public 受 org policy 阻断，落地 Classic PAT 方案 |
