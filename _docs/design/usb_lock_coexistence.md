# 设计：与 station-v2 printer-service 共存 `/dev/usb/lp0`

## Motivation

qwh-pi5-c 上原本就跑着 `station-v2-docker/printer-service`（端口 8086），它通过 `printer_manager.py` 直接 `open(/dev/usb/lp0, "wb")` 写 ZPL。新的 `print-server` 也要写同一个 USB 设备。

USB 字符设备没有内核级互斥；两个进程同时写会**字节流交错**，导致打印机收到一段被另一段截断的 ZPL，渲染出错乱标签或彻底丢张。

我们需要一种**跨容器、跨进程**的串行机制，且不能要求改动老服务（迁移它是另一个工程）。

## Proposed Solution

在 host 文件系统上放一个文件锁，两个容器 bind-mount `/var/lock` 后用 `fcntl.flock` 获取锁再写设备：

```python
@contextmanager
def _device_lock(timeout: float = 5.0):
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o666)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EACCES):
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError(...)
            time.sleep(0.05)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
```

- **锁路径**：`/var/lock/zd411.lock`，env `LOCK_PATH` 可改
- **超时**：默认 5 秒，超时返回结构化错误（业务侧能重试）
- **作用域**：包住"open + write copies + close"，确保一次完整 ZPL 是原子的
- **挂载**：compose 里 `volumes: - /var/lock:/var/lock`

实现见 `app/printer.py: _device_lock`。

## Alternatives

- **基于 Redis 的分布式锁**：station-v2 已经在跑 Redis。但要老服务也改才能起效，反而增加耦合，且锁定语义没 OS flock 直接
- **CUPS 队列**：CUPS 天然串行，但要装 Zebra 驱动、引入 PPD、改业务调用路径，重量级且没必要
- **`open(..., "wb")` 加 OS 文件锁（不显式 flock）**：Linux 字符设备的 advisory locking 行为不一致，靠不住
- **彻底替代老服务**：方向正确但代价大，且需要 station 侧改调用。flock 让我们能"先并存，后迁移"

## Impact

- `app/printer.py`：新增 `_device_lock` + `send_zpl()` / `query_status()` 调用
- `docker-compose.yml`：bind-mount `/var/lock:/var/lock`，权限 `user: "0:0"`（`/dev/usb/lp0` 属 `lp` 组，root 直接写最省事）
- **老 `station-v2-docker/printer-service` 不变** → 高频打印场景下仍可能出错；建议后续提一个 PR 给老服务，让它也获 `/var/lock/zd411.lock` 后再写

## Revision History

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-06-03 | 初版 | 与老 printer-service 共存 |
