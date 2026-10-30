# auto-install

雷电模拟器 ADB 自动化安装工具，运行于 **Windows WSL** 环境，通过调用 **Windows 侧 adb.exe** 控制雷电模拟器。

包含两个脚本：

| 脚本 | 方式 | 流程 |
|---|---|---|
| `auto_install.py` | ADB 直装 | 下载 APK（URL）→ `adb install` 安装 → 失败自动截图 |
| `browser_install.py` | 浏览器模拟人工 | 清浏览器数据 → 填 URL → 下载 → 点「安装」→ 校验「安装成功」→ 卸载 App → 关浏览器 |

## 环境要求

- **WSL2**（Ubuntu，Python ≥ 3.10，[uv](https://docs.astral.sh/uv/) 管理依赖）
- **雷电模拟器 9**（已开启 ADB 调试），Windows 侧 adb.exe：
  `C:\Users\<用户>\program\Android\platform-tools\adb.exe`（路径不同用 `--adb` 指定）
- **代理**（Clash 系，默认端口 7897）：下载 `workers.dev` 等被墙域名必须走代理

> 为什么用 Windows adb.exe：雷电模拟器的 adb 只监听 Windows 侧，WSL2 的 Linux adb 无法直连；
> WSL 中直接调用 `adb.exe` 已实测稳定。

## 安装

```bash
uv sync          # 创建 .venv 并安装依赖（requests）
```

## 使用

### 1. ADB 直装（auto_install.py）

```bash
# 从 URL 下载安装（走代理）
uv run python auto_install.py \
  --url 'https://xxx/xxx.apk' \
  --proxy http://172.28.64.1:7897 \
  --serial 127.0.0.1:5561

# 本地 APK 安装并启动
uv run python auto_install.py \
  --apk /mnt/d/apk/test.apk \
  --package com.xxx --activity .MainActivity
```

| 参数 | 说明 | 默认 |
|---|---|---|
| `--url` / `--apk` | APK 来源（二选一，必填） | — |
| `--serial` | 设备序列号 | `127.0.0.1:5555` |
| `--adb` | Windows adb.exe 路径 | 见脚本内 `DEFAULT_ADB` |
| `--proxy` | HTTP 代理（下载用） | 无 |
| `--package` / `--activity` | 安装后启动的 App | 不启动 |

### 2. 浏览器模拟人工下载安装（browser_install.py）

```bash
uv run python browser_install.py \
  --url 'https://vas-come-test-guest-fg2ia.cf8-d19.workers.dev/2?hash=xxx&sign=xxx' \
  --proxy http://127.0.0.1:7897 \
  --serial 127.0.0.1:5561
```

自动化节点（每步截图留档）：

```
清浏览器数据 → 启动浏览器(node1) → 地址栏填 URL(node2) → 回车
→ 轮询等待下载+安装器弹出(node3) → 点「安装」→ 校验「安装成功」(node4)
→ 点「完成」→ 自动识别新装包名 → 卸载 App(node5) → 关浏览器 → 还原代理
```

| 参数 | 说明 | 默认 |
|---|---|---|
| `--url` | APK 下载地址（必填） | — |
| `--proxy` | 代理地址，**只取端口**建 `adb reverse` 隧道 | 无 |
| `--serial` | 设备序列号 | `127.0.0.1:5555` |
| `--package` | 指定要卸载的包名 | 自动检测新增包 |
| `--timeout` | 等待下载+安装器超时（秒） | 120 |
| `--keep-browser-data` | 不清浏览器数据 | 默认 `pm clear` 防幽灵下载 |

**截图目录**：`screenshots/browser_flow_{yyyyMMddHHmm}_{域名}/`（时间戳取脚本运行时刻）

## 代理方案说明（重要）

被墙域名（如 `*.workers.dev`）下载依赖代理，脚本使用 **`adb reverse` 隧道**：

```
模拟器内 127.0.0.1:7897 ──adbd 隧道──> Windows 127.0.0.1:7897 (Clash)
```

- 不依赖 WSL NAT IP（`172.28.64.1` 重启会变）和模拟器↔宿主机路由
- 代理**写入即生效**，绕开 `settings put global http_proxy` 传播不稳定的问题
- `--proxy` 只用于取端口，填 `http://127.0.0.1:7897` 即可；adb server 重启后脚本每次运行会自动重建隧道

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `device not found` / 设备掉线 | 模拟器可能已退出或端口变化：`ldconsole.exe list2` 查实例状态，`ldconsole.exe launch --index N` 启动；或 `adb connect 127.0.0.1:5561` 重连 |
| `ERR_CONNECTION_RESET` | 浏览器走了直连：确认 Clash 在运行、`--proxy` 端口正确；脚本失败会自动重写代理重试一次 |
| 推送 GitHub 失败 | WSL 无凭据时用 Windows git：`"/mnt/c/Program Files/Git/mingw64/bin/git.exe" -C "D:\\quanyou\\auto-install" push origin main` |
| 下载 URL 失效 | URL 带 `sign` 签名有时效，过期需重新获取 |
| 按钮点不到 | 脚本坐标基于 1280x720 分辨率硬编码（见 `browser_install.py` 的 `COORDS`），分辨率变化需调整 |

## 已知限制

- 模拟器内下载的 APK 会累积在 `/sdcard/Download/Come-N.apk`（浏览器对同名文件自动加后缀），需定期清理
- 安装坐标、地址栏坐标依赖雷电默认分辨率，多分辨率适配未做
- URL 的 `sign` 签名有时效性，自动化前确认链接可用
