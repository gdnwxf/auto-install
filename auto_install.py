#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雷电模拟器 ADB 自动安装脚本（Windows WSL 环境）
- 在 WSL 中调用 Windows 侧 adb.exe（WSL2 的 Linux adb 无法直连模拟器）
- 支持 APK 下载（URL）或本地路径安装
- 安装失败自动截图保存到 screenshots/
用法示例:
    python3 auto_install.py --url https://xxx/test.apk
    python3 auto_install.py --apk /mnt/d/apk/test.apk
    python3 auto_install.py --apk ./test.apk --package com.xxx --activity .MainActivity
"""

import argparse
import datetime
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

# WSL 下 Windows 侧 adb.exe 的默认位置
DEFAULT_ADB = r"/mnt/c/Users/C018/program/Android/platform-tools/adb.exe"
DEFAULT_SERIAL = "127.0.0.1:5555"  # 雷电模拟器默认 adb 端口
SCRIPT_DIR = Path(__file__).resolve().parent
SCREENSHOT_DIR = SCRIPT_DIR / "screenshots"
DOWNLOAD_DIR = SCRIPT_DIR / "downloads"

ADB_TIMEOUT = 120          # 单条 adb 命令超时（秒）
DOWNLOAD_TIMEOUT = 300     # 下载超时（秒）


def to_win_path(path: str) -> str:
    """WSL 路径转 Windows 路径（adb.exe 只认 Windows 路径）
    wslpath 对不存在的文件会报错，所以对 /mnt/<盘>/ 路径做手动转换兜底
    """
    out = subprocess.run(["wslpath", "-w", str(path)],
                         capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip()
    parts = Path(path).parts  # ('/', 'mnt', 'd', 'quanyou', ...)
    if len(parts) > 3 and parts[1] == "mnt" and len(parts[2]) == 1 and parts[2].isalpha():
        return f"{parts[2].upper()}:\\" + "\\".join(parts[3:])
    raise RuntimeError(f"路径转换失败: {path}")


class AdbError(RuntimeError):
    """adb 命令执行失败"""


class AdbClient:
    """封装 Windows adb.exe 调用"""

    def __init__(self, adb_path: str, serial: str):
        self.adb_path = adb_path
        self.serial = serial
        if not Path(adb_path).exists():
            raise FileNotFoundError(f"找不到 adb: {adb_path}")

    def _base(self) -> list:
        return [self.adb_path, "-s", self.serial]

    def run(self, args: list, check: bool = True) -> tuple[int, str]:
        """执行 adb 命令，返回 (返回码, 合并输出)"""
        cmd = self._base() + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=ADB_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise AdbError(f"adb 命令超时: {' '.join(args)}")
        output = (result.stdout or "") + (result.stderr or "")
        if check and result.returncode != 0:
            raise AdbError(f"adb {' '.join(args)} 失败(码{result.returncode}): {output.strip()}")
        return result.returncode, output.strip()

    def ensure_connected(self) -> None:
        """确认设备在线；若是 TCP 序列号则先 connect 兜底"""
        _, out = self.run(["devices"])
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == self.serial and parts[1] == "device":
                print(f"✅ 设备已连接: {self.serial}")
                return
        if ":" in self.serial:  # TCP 设备尝试 connect
            result = subprocess.run([self.adb_path, "connect", self.serial],
                                    capture_output=True, text=True, timeout=30)
            print(f"🔌 connect 输出: {(result.stdout + result.stderr).strip()}")
        _, out = self.run(["devices"])
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == self.serial and parts[1] == "device":
                print(f"✅ 设备连接成功: {self.serial}")
                return
        raise AdbError(f"设备不可用: {self.serial}，请确认模拟器已启动\n{out}")

    def install(self, apk_win_path: str) -> None:
        """安装 APK（-r 覆盖安装, -t 允许测试包）"""
        print(f"📦 开始安装: {apk_win_path}")
        ret, out = self.run(["install", "-r", "-t", apk_win_path], check=False)
        if ret != 0 or "Success" not in out:
            raise AdbError(f"APK 安装失败: {out}")
        print("✅ 安装成功")

    def start_app(self, package: str, activity: str | None) -> None:
        """启动 APP；activity 为空时用 monkey 方式启动默认入口"""
        if activity:
            component = activity if "/" in activity else f"{package}/{activity}"
            self.run(["shell", "am", "start", "-n", component])
        else:
            self.run(["shell", "monkey", "-p", package,
                      "-c", "android.intent.category.LAUNCHER", "1"])
        print(f"🚀 已发送启动指令: {package}")

    def screenshot(self, save_path: Path) -> bool:
        """模拟器截图并拉取到 WSL 本地"""
        remote = "/sdcard/auto_install_screen.png"
        try:
            self.run(["shell", "screencap", "-p", remote])
            self.run(["pull", remote, to_win_path(save_path)])
            self.run(["shell", "rm", remote], check=False)
            print(f"📸 截图已保存: {save_path}")
            return True
        except AdbError as e:
            print(f"⚠️ 截图失败: {e}")
            return False


def download_apk(url: str, save_path: Path, proxy: str | None = None) -> Path:
    """流式下载 APK"""
    print(f"⬇️ 开始下载: {url}")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        with requests.get(url, stream=True, timeout=30, proxies=proxies) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done = 0
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            print(f"\r下载进度: {done / total:6.1%}", end="", flush=True)
        print(f"\n✅ APK 下载完成: {save_path} ({save_path.stat().st_size} bytes)")
        return save_path
    except requests.RequestException as e:
        if save_path.exists():
            save_path.unlink(missing_ok=True)  # 清理残缺文件
        raise RuntimeError(f"APK 下载失败: {e}") from e


def filename_from_url(url: str) -> str:
    """从 URL 推断文件名，兜底用时间戳"""
    name = Path(unquote(urlparse(url).path)).name
    return name if name.endswith(".apk") else f"app_{datetime.datetime.now():%Y%m%d_%H%M%S}.apk"


def main() -> int:
    parser = argparse.ArgumentParser(description="雷电模拟器 ADB 自动安装脚本")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="APK 下载链接")
    src.add_argument("--apk", help="本地 APK 路径（WSL 路径即可）")
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help=f"设备序列号 (默认 {DEFAULT_SERIAL})")
    parser.add_argument("--adb", default=DEFAULT_ADB, help="Windows adb.exe 路径")
    parser.add_argument("--package", help="安装后要启动的包名")
    parser.add_argument("--activity", help="要启动的 Activity（可省略，用默认入口）")
    parser.add_argument("--proxy", help="HTTP 代理，如 http://172.28.64.1:7897（workers.dev 等被墙域名需走代理）")
    args = parser.parse_args()

    adb = AdbClient(args.adb, args.serial)
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        adb.ensure_connected()

        # 1. 准备 APK
        if args.url:
            DOWNLOAD_DIR.mkdir(exist_ok=True)
            apk_local = DOWNLOAD_DIR / filename_from_url(args.url)
            download_apk(args.url, apk_local, proxy=args.proxy)
        else:
            apk_local = Path(args.apk).expanduser().resolve()
            if not apk_local.is_file():
                raise FileNotFoundError(f"本地 APK 不存在: {apk_local}")
            if apk_local.suffix.lower() != ".apk":
                raise ValueError(f"不是 .apk 文件: {apk_local}")

        # 2. 安装
        adb.install(to_win_path(apk_local))

        # 3. 可选启动
        if args.package:
            adb.start_app(args.package, args.activity)

        print("🎉 全部完成")
        return 0
    except Exception as err:
        print(f"🔥 执行异常: {err}", file=sys.stderr)
        shot = SCREENSHOT_DIR / f"error_{ts}.png"
        try:
            adb.ensure_connected()
            adb.screenshot(shot)
        except Exception as snap_err:
            print(f"⚠️ 异常截图流程失败: {snap_err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
