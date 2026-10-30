# update-qh-auto-install-20261029

[2026-10-29 19:42] - 修改
## 雷电模拟器 ADB 自动安装脚本

### 目标与范围
- 在 WSL 环境下通过 Windows adb.exe 控制雷电模拟器：下载/本地 APK → 安装 → 失败自动截图。
- 新建 `auto_install.py`，无已有文件改动。

### 关键决策
- WSL2 内 Linux adb 无法直连模拟器（雷电 adb 仅监听 Windows 127.0.0.1），采用 WSL 直调 Windows 侧 `adb.exe`（`/mnt/c/Users/C018/program/Android/platform-tools/adb.exe`）。
- 传给 adb.exe 的文件参数用 `wslpath -w` 转 Windows 路径；发现 `wslpath` 对不存在的文件报错，增加 `/mnt/<盘>/` 手动转换兜底。
- 设备序列号参数化（默认 127.0.0.1:5555），多实例时可 `--serial` 指定（本次实测实例为 127.0.0.1:5561）。
- 依赖通过 `uv venv .venv` + `uv pip install requests` 安装（系统无 pip）。

### 修改文件及影响
- 新建 `auto_install.py`：adb 封装、连接检测、下载、安装（install -r -t）、可选启动、异常截图到 `screenshots/`。
- 新建 `.venv/`（Python 虚拟环境，仅本地依赖）。

### 验证
- 通过：语法编译、`--help`、设备连接检测（127.0.0.1:5561）、损坏 APK 安装失败路径（adb 返回 INSTALL_PARSE_FAILED_NOT_APK，脚本正确判定失败）、失败自动截图（`screenshots/error_20261029_194210.png`，351KB 实图）。
- 未验证（证据缺口）：URL 下载路径（无真实下载源）、安装成功路径与 `Success` 判定、启动 APP（无真实可安装 APK，模拟器无第三方应用，D 盘无现成 APK）。

### 风险与未完成项
- 模拟器实例重启后 TCP 端口可能变化（5555→5561），需用 `--serial` 或确认实例端口。
- 未做存量数据变更；无公共契约变化。

[2026-10-29 20:18] - 修改
## 真实 APK 下载安装闭环验证

### 关键分析与决策
- workers.dev 域名在当前网络直连不可达（WSL/Windows 双侧 curl 均无响应）；检测到 Windows 主机 172.28.64.1:7897 存在 Clash 系代理，验证可通（HTTP 200，content-type APK）。
- `auto_install.py` 新增 `--proxy` 参数透传给 requests 下载，最小改动。

### 验证
- 端到端全流程通过：下载（2,985,179 bytes，进度条正常）→ 路径转换（D:\...downloads\app_20261029_201813.apk）→ `install -r -t` 返回 Success → 模拟器确认第三方包 `com.edch.ykx` 已安装。
- 此前未验证的三项（URL 下载、安装成功判定、成功路径）本次全部补齐；仅 `--activity` 启动路径仍未实测（用户未要求启动）。

### 风险
- 下载 URL 带 sign 参数可能有时效；代理 172.28.64.1:7897 依赖 Windows 侧代理进程存活。

[2026-10-29 20:25] - 修改
## 模拟器内下载+安装流程验证（未改脚本）

### 关键分析与决策
- 模拟器（Android 9, x86_64）自带 /system/bin/curl 与 /system/xbin/wget，可设备内下载。
- 雷电 NAT 网关 172.16.1.1 不可达（ping 丢包 100%），但可达 Windows 宿主机 WSL 虚拟网卡地址 172.28.64.1:7897 的代理，模拟器内 curl 走该代理成功。

### 验证
- 设备内下载：`adb shell curl -x http://172.28.64.1:7897 -o /sdcard/Download/Come.apk`，HTTP 200，2,985,179 bytes，文件头 PK 合法。
- 设备内安装：`adb shell pm install -r -t /sdcard/Download/Come.apk` 返回 Success（avc denied 为 permissive 模式告警，不影响结果）；`pm path com.edch.ykx` 确认安装路径更新。
- 全程 APK 未经过电脑侧传输。
- 未完成：该流程尚未封装进 auto_install.py（--download-in-device 模式待用户确认后添加）。

### 风险
- 代理地址 172.28.64.1 为 WSL NAT 网关，WSL 重启后可能变化，需重新探测。

[2026-10-29 20:35] - 修改
## 浏览器模拟人工下载安装全流程（节点截图留档）

### 关键分析与决策
- 模拟器浏览器 com.android.browser（1280x720）；workers.dev 被墙导致浏览器首次加载 ERR_CONNECTION_RESET，通过 `settings put global http_proxy 172.28.64.1:7897` 设置模拟器全局代理后可访问；流程结束已还原（:0）。
- UI 自动化方式：input tap/text/keyevent + 每节点 screencap 留档；下载完成确认依据为 /sdcard/Download/Come.apk 落盘 2,985,179 bytes。
- 浏览器加载 attachment 响应后自动进入 DownloadManager 下载并自动拉起系统包安装器，无需手动点下载按钮。

### 验证
- 节点截图均在 screenshots/browser_flow/：node1 浏览器首页、node2 URL 已填入（首次加载失败 ERR_CONNECTION_RESET）、node2b 全局代理生效（百度可开）、node3/node3b URL 输入待跳转、node4 浏览器自动下载完成并弹出系统安装器（安装来源：浏览器）、node5 点击安装后「安装成功」、node6 点完成收尾、node7 重复确认页再次点安装复核「安装成功」。
- 系统侧证据：pm list packages -3 含 com.edch.ykx（versionName=1.8.f340-qa），安装路径 /data/app/com.edch.ykx-bxyyjg_XfMPPLi3zGlS0xA==/base.apk。

### 风险
- 流程依赖固定坐标（地址栏 640,75；安装按钮 640,591），分辨率或界面变化需重新定位。
- 模拟器全局代理已还原；下次浏览器访问被墙域名需重新设置。

[2026-10-29 20:28] - 修改
## 浏览器下载安装流程复跑验证

### 验证
- 全流程复现成功：起点干净（com.edch.ykx 已不在，Download 目录旧 APK 已清）→ 设代理 → 浏览器输入 URL → 浏览器自动下载（/sdcard/Download/Come-2.apk，2,985,179 bytes，同名旧文件自动加 -1/-2 后缀）→ 自动弹出系统安装器 → 点「安装」→「安装成功」（rerun_node3_installed.png）→ firstInstallTime/lastUpdateTime=2026-10-29 20:25:03。
- 复跑截图：rerun_node1_browser.png（浏览器首页）、rerun_node2_download.png（安装器确认页）、rerun_node3_installed.png（安装成功）。
- 流程结束代理已还原（settings put global http_proxy :0）。
- 结论：浏览器模拟人工下载安装链路可稳定复现，关键前置条件是模拟器全局代理（被墙域名）。

### 风险
- 同名文件下载多次会在 Download 目录累积 Come-N.apk；URL sign 过期后需重新获取。

[2026-10-29 20:32] - 分析
## 「出现2次安装」现象定位

### 证据与结论
- Download 目录存在 3 个 APK：Come.apk(20:22)、Come-1.apk(20:22)、Come-2.apk(20:24)，浏览器对同名下载自动加后缀，说明发起了多次下载。
- dumpsys 证据：弹出安装器的 task intent 为 `VIEW content://downloads/all_downloads/3`，归属 `com.android.packageinstaller/.PackageInstallerActivity`，即系统包安装器；两次弹窗均由不同下载任务各自触发，并非两个不同安装器。
- 根因：流程中为规避「首次 ENTER 不跳转」采用了二次 ENTER 兜底，每次成功导航都会触发一次浏览器下载，下载完成各自动拉起一次系统安装器。
- 已处理：重复的安装确认页点击「取消」关闭（duplicate_installer.png 留档），界面回到浏览器 BrowserActivity。

### 建议（未实施）
- 流程改为单次 ENTER + 轮询检测（Download 目录新文件或安装器窗口出现），消除重复下载。
- Download 目录冗余 APK 待用户确认后清理。

[2026-10-29 20:36] - 修改
## 安装后删除 App 要求落实

### 验证
- 执行 `pm uninstall com.edch.ykx` 前发现第三方包列表已为空（`pm list packages -3` 无输出，`pm path` 无结果），应用已不在（推断为用户在模拟器侧手动卸载），删除目标已达成，无需重复卸载。
- 流程约定更新：浏览器下载→安装→验证→**卸载 App** 为标准收尾，保证每轮测试起点干净。
- 遗留确认：Download 目录 3 个重复 APK（Come/Come-1/Come-2）清理与流程脚本固化仍在待确认。

[2026-10-29 20:38] - 修改
## 改进版全流程复跑（单次回车+轮询+末尾卸载）

### 关键决策
- 用「单次 ENTER + 轮询检测（Download 新文件 + 安装器窗口焦点）」替代双回车兜底，消除重复下载导致的重复安装弹窗。

### 验证
- 单次回车即触发下载（新文件 Come-3.apk，基线外唯一新增）且仅弹出一次安装器（final_node1_confirm.png）。
- 点「安装」→「安装成功」（final_node2_installed.png），firstInstallTime=2026-10-29 20:36:23 为全新安装。
- 点「完成」→ `pm uninstall com.edch.ykx` 返回 Success → `pm list packages -3` 为空（App 已删除）→ 代理已还原。
- 改进版流程全链路一次通过，无重复弹窗。

### 遗留
- Download 目录历史 APK（Come/Come-1/Come-2/Come-3 共4个）清理仍未授权。

[2026-10-29 20:45] - 修改
## 工程改为 uv 管理

### 修改文件及影响
- 新建 `pyproject.toml`（name=auto-install, requires-python>=3.10, dependencies=requests, 非打包模式 tool.uv.package=false）。
- `uv sync` 生成 `uv.lock`，`.venv` 由 uv 接管（Python 3.14.5）。

### 验证
- `uv run python` 导入 requests 正常；两个脚本 `py_compile` 通过、`--help` 正常。
- 附带处理：还原上次代理调试在模拟器遗留的 global http_proxy（已置 :0）。

### 未完成项
- browser_install.py 首跑失败（浏览器加载报 ERR_CONNECTION_RESET，代理未生效原因未定位，读回 settings get 显示代理值正确）；待继续排查（疑似 force-stop 浏览器重启与代理生效时序相关）。
- Download 目录历史 APK 清理仍未授权。

[2026-10-29 20:55] - 分析
## ERR_CONNECTION_RESET 根因排查与模拟器恢复

### 证据与结论
- 根因确认：`settings put global http_proxy` 写入成功（settings get 读回正确），但 ConnectivityService 未传播到网络（dumpsys connectivity 显示 HttpProxy: mHost==null），浏览器直连被墙域名被 RST。传播时机不稳定：20:16/20:21 两次设置后生效，20:44 脚本执行未生效。
- 排查尝试：等待10s不传播；重写设置（:0 再写回）不传播；重启模拟器后设置残留但网络仍未应用。
- 意外事故：`svc wifi disable` 导致模拟器 adb 通道全部 offline，通过 `ldconsole.exe reboot --index 3` 重启恢复（新 IP 172.16.1.47）。
- 恢复后实测：浏览器经 am start 导航 workers.dev 下载成功（代理实际生效），但浏览器恢复会话触发了幽灵下载（Come-4/5.apk，Download 现 6 个文件）；已取消弹出的安装器并关闭浏览器。
- 疑点未解：dumpsys HttpProxy 仍显示 null 但浏览器实际走代理，传播机制与显示不一致，不影响使用结论：以「浏览器实测下载成功」作为代理生效判据。

### 建议（待确认实施）
- browser_install.py 增加代理生效校验：设代理后轮询「浏览器实测可下载」或以轮询 Download 新文件为准，避免写完立即导航。
- 跑流程前清浏览器会话（pm clear com.android.browser 或手动关标签），消除恢复会话的幽灵下载。

[2026-10-29 20:59] - 修改
## browser_install.py 改进并全流程一次通过

### 修改文件及影响
- `browser_install.py`：① 默认 `pm clear com.android.browser` 清会话防幽灵下载（`--keep-browser-data` 可跳过）；② 导航+轮询封装进重试循环（最多2次，重试前重写代理触发传播）；③ 安装结果用 uiautomator dump 校验「安装成功」；④ 新装包名自动检测（pm list -3 前后差集）。

### 验证
- 一次通过：pm clear 后仅新增 Come-6.apk（无幽灵下载），第1次导航即触发下载+安装器；「安装成功」界面校验通过；自动识别包名 com.edch.ykx；pm uninstall Success 且卸载后包列表为空；浏览器已关闭、代理已还原。
- 截图目录 browser_flow_202610292059_vas-come-test-guest-fg2ia.cf8-d19.workers.dev/（node1~node5 动态时间戳命名）。

### 遗留
- Download 目录 7 个历史 APK（Come~Come-6）清理仍未授权。
- dumpsys HttpProxy 显示与浏览器实际代理行为不一致的机制疑点，未深究（不影响流程，判据以实测下载为准）。

[2026-10-29 21:11] - 修改
## 代理方案重构: adb reverse 隧道(根治传播不稳定)

### 关键分析与决策
- 排查确认：21:03 失败是模拟器进程退出(list2 is_running=0)导致设备掉线，与代理无关；ldconsole launch 恢复。
- ERR_CONNECTION_RESET 根因仍是 global proxy 传播不稳定(重启后残留设置也不生效，重写亦无效，时灵时不灵)。
- 改用 `adb reverse tcp:7897 tcp:7897` 隧道：模拟器内 127.0.0.1:7897 经 adbd 直通 Windows Clash，不依赖 WSL NAT IP(会变)与模拟器宿主路由，代理写入即生效(实测导航5s内下载完成)。
- browser_install.py 代理逻辑重构：--proxy 解析端口 → reverse 隧道 → 设 127.0.0.1:<port>；收尾还原 :0 并 reverse --remove。

### 验证
- 改造后全流程一次通过：Come-8.apk 下载 → 安装器弹出 → uiautomator 校验「安装成功」→ 自动识别 com.edch.ykx → pm uninstall Success → 浏览器关闭、代理还原、隧道拆除。
- 截图目录 browser_flow_202610292110_vas-come-test-guest-fg2ia.cf8-d19.workers.dev/。
- 使用注意：--proxy 仅用于取端口，填 http://127.0.0.1:7897 即可；adb server 重启后 reverse 需重建(脚本每次运行自动建)。

### 遗留
- Download 目录 8 个历史 APK 清理仍未授权。

[2026-10-30 10:21] - 修改
## 完整流程复跑(隔日验证)

### 验证
- 隔日再次全流程一次通过：reverse 隧道建立 → Come-9.apk 下载 → 安装器弹出 → 「安装成功」校验 → 自动识别 com.edch.ykx → 卸载 Success → 浏览器关闭/代理还原/隧道拆除。
- 截图 browser_flow_202610301021_.../（node1~node5）。reverse 方案跨会话稳定，无需人工干预。
