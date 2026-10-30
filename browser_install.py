#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雷电模拟器 浏览器模拟人工下载安装脚本（Windows WSL 环境）
流程: 设代理 → 启动浏览器 → 填 URL → 单次回车 → 轮询下载/安装器 →
      截图 → 点安装 → 验证 → 点完成 → 卸载 App → 关闭浏览器 → 还原代理
截图目录: screenshots/browser_flow_{yyyyMMddHHmm}_{域名}/  (时间戳取脚本运行时刻)

用法:
    .venv/bin/python browser_install.py --url '<APK下载地址>' \
        [--proxy http://172.28.64.1:7897] [--serial 127.0.0.1:5561] [--package com.xxx]

注意: 按钮坐标基于雷电模拟器 1280x720 分辨率硬编码, 分辨率变化需调整 COORDS。
"""

import argparse
import datetime
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ADB = r"/mnt/c/Users/C018/program/Android/platform-tools/adb.exe"
DEFAULT_SERIAL = "127.0.0.1:5555"  # 雷电默认 TCP 序列号, 多实例用 --serial 覆盖
BROWSER_PKG = "com.android.browser"

# 1280x720 分辨率下的界面坐标
COORDS = {
    "address_bar": (640, 75),   # 浏览器顶部地址栏
    "install_btn": (640, 591),  # 安装确认页「安装」
    "done_btn": (640, 658),     # 「完成」/「取消」
}

ADB_TIMEOUT = 120


class FlowError(RuntimeError):
    pass


def to_win_path(path: str) -> str:
    """WSL 路径转 Windows 路径; wslpath 对不存在的文件报错, /mnt/<盘>/ 手动兜底"""
    out = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip()
    parts = Path(path).parts
    if len(parts) > 3 and parts[1] == "mnt" and len(parts[2]) == 1 and parts[2].isalpha():
        return f"{parts[2].upper()}:\\\\" + "\\\\".join(parts[3:])
    raise FlowError(f"路径转换失败: {path}")


class Adb:
    def __init__(self, adb_path: str, serial: str):
        if not Path(adb_path).exists():
            raise FileNotFoundError(f"找不到 adb: {adb_path}")
        self.base = [adb_path, "-s", serial]
        self.serial = serial

    def sh(self, args: list, timeout: int = ADB_TIMEOUT, check: bool = True) -> str:
        result = subprocess.run(self.base + args, capture_output=True, text=True,
                                timeout=timeout)
        out = (result.stdout or "") + (result.stderr or "")
        if check and result.returncode != 0:
            raise FlowError(f"adb {' '.join(args)} 失败: {out.strip()}")
        return out.strip()

    def sh_raw(self, cmd: str, timeout: int = ADB_TIMEOUT) -> str:
        """执行带引号复杂度的 shell 串"""
        return self.sh(["shell", cmd], timeout=timeout)

    def ensure_connected(self):
        out = self.sh(["devices"])
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == self.serial and parts[1] == "device":
                print(f"✅ 设备在线: {self.serial}")
                return
        raise FlowError(f"设备不可用: {self.serial}\n{out}")

    def screenshot(self, save_path: Path):
        remote = "/sdcard/_flow_shot.png"
        self.sh_raw(f"screencap -p {remote}")
        self.sh(["pull", remote, to_win_path(save_path)])
        self.sh_raw(f"rm {remote}")
        print(f"📸 {save_path.name}")

    def focus(self) -> str:
        out = self.sh(["shell", "dumpsys window"])
        for line in out.splitlines():
            if "mCurrentFocus" in line:
                return line
        return ""

    def third_packages(self) -> set:
        return {l.split(":")[1] for l in self.sh(["shell", "pm list packages -3"]).splitlines()
                if l.startswith("package:")}


def main() -> int:
    parser = argparse.ArgumentParser(description="浏览器模拟人工下载安装+卸载")
    parser.add_argument("--url", required=True, help="APK 下载地址")
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help="设备序列号")
    parser.add_argument("--adb", default=DEFAULT_ADB, help="Windows adb.exe 路径")
    parser.add_argument("--proxy", help="模拟器全局 HTTP 代理, 如 http://172.28.64.1:7897")
    parser.add_argument("--package", help="安装后要卸载的包名(默认自动检测新增包)")
    parser.add_argument("--timeout", type=int, default=120, help="等待下载+安装器超时秒数")
    parser.add_argument("--keep-browser-data", action="store_true",
                        help="不清除浏览器数据(默认 pm clear 防止恢复会话触发幽灵下载)")
    args = parser.parse_args()

    adb = Adb(args.adb, args.serial)
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M")  # yyyyMMddHHmm 动态时间戳
    domain = urlparse(args.url).netloc
    shot_dir = SCRIPT_DIR / "screenshots" / f"browser_flow_{ts}_{domain}"
    shot_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 截图目录: {shot_dir.name}")

    # 代理方案: adb reverse 隧道 —— 模拟器内 127.0.0.1:<port> 直通 Windows 侧 Clash,
    # 不依赖 WSL NAT IP(172.28.64.1 会变)和模拟器<->宿主路由, 且写入即生效
    proxy_port = urlparse(args.proxy).port if args.proxy else None
    dev_proxy = f"127.0.0.1:{proxy_port}" if proxy_port else None

    try:
        adb.ensure_connected()

        # 1. 建 reverse 隧道 + 设代理 + 记录下载目录基线 + 包基线
        if proxy_port:
            adb.sh(["reverse", f"tcp:{proxy_port}", f"tcp:{proxy_port}"])
            adb.sh_raw(f"settings put global http_proxy {dev_proxy}")
            print(f"🌐 reverse 隧道+代理已设: {dev_proxy}")
        dl_before = set(adb.sh_raw("ls /sdcard/Download/").split())
        pkg_before = adb.third_packages()

        # 2. 启动导航 + 轮询等待(最多重试一次; 重试时重写代理触发传播)
        new_file = None
        for attempt in (1, 2):
            print(f"🚀 第 {attempt} 次尝试导航")
            adb.sh_raw(f"am force-stop {BROWSER_PKG}")
            time.sleep(1)
            if not args.keep_browser_data:
                adb.sh(["shell", "pm", "clear", BROWSER_PKG])
            adb.sh(["shell", "monkey", "-p", BROWSER_PKG,
                    "-c", "android.intent.category.LAUNCHER", "1"], check=False)
            time.sleep(3)
            adb.screenshot(shot_dir / "node1_browser_home.png")

            # 填 URL (节点2: 输入完成)
            x, y = COORDS["address_bar"]
            adb.sh_raw(f"input tap {x} {y}")
            time.sleep(1)
            adb.sh_raw("input keyevent 123")            # MOVE_END
            for _ in range(40):
                adb.sh_raw("input keyevent 67")         # DEL 逐个删除旧 URL
            adb.sh_raw(f"input text '{args.url}'")
            time.sleep(1)
            adb.screenshot(shot_dir / "node2_url_input.png")
            adb.sh_raw("input keyevent 66")             # ENTER, 单次

            # 轮询: 新下载文件 + 系统安装器弹出 (节点3: 安装确认页)
            deadline = time.time() + args.timeout
            while time.time() < deadline:
                time.sleep(5)
                dl_now = set(adb.sh_raw("ls /sdcard/Download/").split())
                new_file = dl_now - dl_before
                if new_file and "packageinstaller" in adb.focus():
                    break
            if new_file and "packageinstaller" in adb.focus():
                break
            if attempt == 1 and dev_proxy:
                print("🔁 未检测到下载, 重写代理触发传播后重试")
                adb.sh_raw("settings put global http_proxy :0")
                time.sleep(1)
                adb.sh_raw(f"settings put global http_proxy {dev_proxy}")
        else:
            raise FlowError(f"等待下载/安装器超时({args.timeout}s)x2, 新文件={new_file or '无'}")
        print(f"⬇️ 下载完成: {sorted(new_file)}, 安装器已弹出")
        adb.screenshot(shot_dir / "node3_installer_confirm.png")

        # 5. 点「安装」, 用 uiautomator dump 验证「安装成功」 (节点4)
        x, y = COORDS["install_btn"]
        adb.sh_raw(f"input tap {x} {y}")
        time.sleep(4)
        adb.sh_raw("uiautomator dump /sdcard/_ui.xml")
        ui = adb.sh_raw("cat /sdcard/_ui.xml")
        adb.sh_raw("rm /sdcard/_ui.xml")
        adb.screenshot(shot_dir / "node4_install_result.png")
        if "安装成功" not in ui and "安装完成" not in ui:
            raise FlowError("安装结果校验失败: 未在界面找到「安装成功」")
        print("✅ 界面校验: 安装成功")

        # 6. 点「完成」, 检测新增包名
        x, y = COORDS["done_btn"]
        adb.sh_raw(f"input tap {x} {y}")
        time.sleep(2)
        pkg_new = adb.third_packages() - pkg_before
        package = args.package or (sorted(pkg_new)[0] if pkg_new else None)
        if not package:
            raise FlowError("无法确定新安装的包名, 请用 --package 指定")
        print(f"📦 新装包: {package}")

        # 7. 卸载 App (节点5)
        out = adb.sh(["shell", "pm", "uninstall", package])
        if "Success" not in out:
            raise FlowError(f"卸载失败: {out}")
        left = adb.third_packages()
        if package in left:
            raise FlowError("卸载后包仍存在")
        print(f"🗑️ 已卸载: {package}")
        adb.screenshot(shot_dir / "node5_uninstalled.png")

        print("🎉 全流程完成")
        return 0
    except Exception as err:
        print(f"🔥 执行异常: {err}", file=sys.stderr)
        try:
            adb.screenshot(shot_dir / f"error_{datetime.datetime.now():%H%M%S}.png")
        except Exception as e:
            print(f"⚠️ 异常截图失败: {e}", file=sys.stderr)
        return 1
    finally:
        # 8. 收尾: 关闭浏览器 + 还原代理 + 拆除隧道
        try:
            adb.sh_raw(f"am force-stop {BROWSER_PKG}")
            print("🔒 浏览器已关闭")
            adb.sh_raw("settings put global http_proxy :0")
            if proxy_port:
                adb.sh(["reverse", "--remove", f"tcp:{proxy_port}"], check=False)
            print("🌐 代理已还原, 隧道已拆除")
        except Exception as e:
            print(f"⚠️ 收尾步骤失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
