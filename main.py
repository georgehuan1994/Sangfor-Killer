#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sangfor Killer - 自动检测并终止 Sangfor 相关进程和服务
"""

import os
import sys
import subprocess
import psutil
import time
import ctypes
from pathlib import Path
from typing import Set, List, Optional
from datetime import datetime


class ColorOutput:
    """彩色输出辅助类"""
    # ANSI 颜色代码
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

    @staticmethod
    def init():
        """初始化 Windows 控制台颜色支持"""
        if sys.platform == 'win32':
            try:
                # 启用 Windows 10+ 的 ANSI 颜色支持
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)  # type: ignore
            except Exception:
                pass

    @classmethod
    def print(cls, text: str, color: str = '', bold: bool = False):
        """打印彩色文本"""
        if bold:
            print(f"{cls.BOLD}{color}{text}{cls.RESET}")
        else:
            print(f"{color}{text}{cls.RESET}")

    @classmethod
    def success(cls, text: str):
        """成功消息（绿色）"""
        cls.print(text, cls.GREEN)

    @classmethod
    def error(cls, text: str):
        """错误消息（红色）"""
        cls.print(text, cls.RED)

    @classmethod
    def warning(cls, text: str):
        """警告消息（黄色）"""
        cls.print(text, cls.YELLOW)

    @classmethod
    def info(cls, text: str):
        """信息消息（蓝色）"""
        cls.print(text, cls.BLUE)

    @classmethod
    def header(cls, text: str):
        """标题消息（青色加粗）"""
        cls.print(text, cls.CYAN, bold=True)


def get_all_drives() -> List[str]:
    """获取所有本地磁盘驱动器"""
    drives = []
    try:
        for partition in psutil.disk_partitions():
            # 只获取本地磁盘（排除网络驱动器和光驱）
            if 'fixed' in partition.opts.lower():
                drives.append(partition.device)
    except Exception as e:
        ColorOutput.error(f"[!] 获取磁盘驱动器时出错: {e}")
    return drives


def run_sc_command(args: List[str], timeout: int = 5, encoding: str = 'gbk') -> Optional[str]:
    """执行 sc 命令的辅助函数

    Args:
        args: sc 命令参数列表
        timeout: 超时时间（秒）
        encoding: 编码格式

    Returns:
        命令输出，失败时返回 None
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            encoding=encoding,
            errors='ignore',
            timeout=timeout
        )
        return result.stdout if result.returncode == 0 or result.stdout else None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


class SangforKiller:
    def __init__(self):
        self.sangfor_paths = [
            r"Program Files\Sangfor",
            r"Program Files (x86)\Sangfor"
        ]
        self.exe_files: Set[str] = set()
        self.service_names: Set[str] = set()
        self.loop_mode = False  # 循环模式标志
        self.disable_services = False  # 是否禁用服务
        self.log_file: Optional[Path] = None  # 日志文件路径
        self.watchdog_processes: Set[str] = set()  # 守护进程列表
        self.scheduled_tasks: Set[str] = set()  # 计划任务列表

        # 统计信息
        self.total_processes_killed = 0
        self.total_services_stopped = 0
        self.total_services_disabled = 0
        self.total_tasks_disabled = 0
        self.total_drivers_disabled = 0

    def analyze_restart_sources(self) -> None:
        """分析进程重启的来源"""
        ColorOutput.header("\n" + "=" * 60)
        ColorOutput.header("[*] 分析进程重启源")
        ColorOutput.header("=" * 60)

        ColorOutput.info("\n[*] 检测到的可能重启源：\n")

        # 1. 检查服务
        if self.service_names:
            ColorOutput.warning(f"⚠️  发现 {len(self.service_names)} 个 Windows 服务（会自动重启进程）:")
            for service in sorted(self.service_names):
                print(f"     - {service}")

        # 2. 检查守护进程
        if self.watchdog_processes:
            ColorOutput.warning(f"\n⚠️  发现 {len(self.watchdog_processes)} 个守护进程（监控并重启其他进程）:")
            for watchdog in sorted(self.watchdog_processes):
                print(f"     - {watchdog}")

        # 3. 检查计划任务
        if self.scheduled_tasks:
            ColorOutput.warning(f"\n⚠️  发现 {len(self.scheduled_tasks)} 个计划任务（定时启动进程）:")
            for task in sorted(self.scheduled_tasks):
                print(f"     - {task}")

        ColorOutput.info("\n💡 解决方案：")
        ColorOutput.info("   1. 先禁用所有服务和计划任务")
        ColorOutput.info("   2. 优先终止守护进程")
        ColorOutput.info("   3. 再终止其他进程")
        ColorOutput.info("   4. 使用循环监控模式防止残留进程复活\n")

    def log(self, message: str, level: str = 'INFO'):
        """记录日志到文件"""
        if self.log_file:
            try:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{timestamp}] [{level}] {message}\n")
            except Exception:
                pass

    def find_sangfor_directories(self) -> List[Path]:
        """查找所有磁盘中的 Sangfor 目录"""
        sangfor_dirs = []
        drives = get_all_drives()
        
        ColorOutput.info(f"[*] 检测到的本地磁盘: {', '.join(drives)}")

        for drive in drives:
            for sangfor_path in self.sangfor_paths:
                full_path = Path(drive) / sangfor_path
                if full_path.exists():
                    ColorOutput.success(f"[+] 找到 Sangfor 目录: {full_path}")
                    self.log(f"找到 Sangfor 目录: {full_path}")
                    sangfor_dirs.append(full_path)

        return sangfor_dirs

    def collect_exe_files(self, directories: List[Path]) -> None:
        """收集所有 Sangfor 目录中的 .exe 文件"""
        ColorOutput.info("\n[*] 开始收集 .exe 文件...")

        # 守护进程关键词
        watchdog_keywords = ['watchdog', 'monitor', 'service', 'guard', 'protect', 'daemon']

        for directory in directories:
            try:
                ColorOutput.info(f"    扫描目录: {directory}")
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        if file.lower().endswith('.exe'):
                            exe_name = Path(file).stem  # 不含扩展名的文件名
                            if exe_name not in self.exe_files:
                                self.exe_files.add(exe_name)
                                print(f"      发现: {file}")
                                self.log(f"发现 .exe 文件: {file}")

                                # 检查是否是守护进程
                                exe_name_lower = exe_name.lower()
                                if any(keyword in exe_name_lower for keyword in watchdog_keywords):
                                    self.watchdog_processes.add(exe_name)
                                    ColorOutput.warning(f"        ⚠️  可能的守护进程！")
                                    self.log(f"发现守护进程: {exe_name}", 'WARNING')
            except PermissionError:
                ColorOutput.warning(f"[!] 权限不足，无法访问: {directory}")
                self.log(f"权限不足，无法访问: {directory}", 'WARNING')
            except Exception as e:
                ColorOutput.error(f"[!] 扫描 {directory} 时出错: {e}")
                self.log(f"扫描 {directory} 时出错: {e}", 'ERROR')

        ColorOutput.success(f"\n[+] 共收集到 {len(self.exe_files)} 个不重复的 .exe 文件")
        if self.watchdog_processes:
            ColorOutput.warning(f"[!] 发现 {len(self.watchdog_processes)} 个可能的守护进程: {', '.join(self.watchdog_processes)}")
        self.log(f"共收集到 {len(self.exe_files)} 个 .exe 文件")

    def find_services(self, directories: List[Path]) -> None:
        """查找 Sangfor 目录中可能包含的服务"""
        ColorOutput.info("\n[*] 开始查找相关服务...")

        try:
            # 获取所有服务
            services_output = run_sc_command(['sc', 'query', 'state=', 'all'])

            if not services_output:
                ColorOutput.warning("[!] 无法获取服务列表")
                return
            
            # 方法1: 检查服务名称是否包含 sangfor 关键字
            all_services = []
            for line in services_output.split('\n'):
                if 'SERVICE_NAME:' in line:
                    service_name = line.split(':', 1)[1].strip()
                    all_services.append(service_name)
                    
                    # 检查服务名称是否包含 sangfor 关键字
                    if 'sangfor' in service_name.lower():
                        self.service_names.add(service_name)
                        ColorOutput.success(f"    [名称匹配] 发现服务: {service_name}")
                        self.log(f"发现服务（名称匹配）: {service_name}")

            # 方法2: 检查所有服务的可执行文件路径是否在 Sangfor 目录中
            ColorOutput.info("    [*] 检查服务可执行文件路径...")
            for service_name in all_services:
                output = run_sc_command(['sc', 'qc', service_name], timeout=2)

                if output:
                    for line in output.split('\n'):
                        if 'BINARY_PATH_NAME' in line:
                            path = line.split(':', 1)[1].strip()
                            # 检查路径是否在 Sangfor 目录中
                            for directory in directories:
                                if str(directory).lower() in path.lower():
                                    if service_name not in self.service_names:
                                        self.service_names.add(service_name)
                                        ColorOutput.success(f"    [路径匹配] 发现服务: {service_name}")
                                        self.log(f"发现服务（路径匹配）: {service_name}")
                                    break
                            break

            ColorOutput.success(f"\n[+] 共找到 {len(self.service_names)} 个相关服务")
            self.log(f"共找到 {len(self.service_names)} 个相关服务")

        except Exception as e:
            ColorOutput.error(f"[!] 查找服务时出错: {e}")
            self.log(f"查找服务时出错: {e}", 'ERROR')
            import traceback
            traceback.print_exc()
    
    def find_drivers(self) -> Set[str]:
        """查找 Sangfor 相关的驱动服务"""
        ColorOutput.info("\n[*] 开始查找驱动服务...")
        drivers = set()

        try:
            # 查询所有驱动类型的服务
            result = subprocess.run(
                ['sc', 'query', 'type=', 'driver'],
                capture_output=True,
                encoding='gbk',
                errors='ignore',
                timeout=10
            )

            if not result.stdout:
                return drivers

            # 解析输出
            for line in result.stdout.split('\n'):
                if 'SERVICE_NAME:' in line:
                    service_name = line.split(':', 1)[1].strip()

                    # 检查是否与 Sangfor 相关
                    if 'sangfor' in service_name.lower():
                        drivers.add(service_name)
                        ColorOutput.success(f"    [发现驱动] {service_name}")
                        self.log(f"发现驱动服务: {service_name}")

            if drivers:
                ColorOutput.success(f"\n[+] 共找到 {len(drivers)} 个驱动服务")
            else:
                ColorOutput.info("[*] 未找到驱动服务")

        except Exception as e:
            ColorOutput.error(f"[!] 查找驱动时出错: {e}")
            self.log(f"查找驱动时出错: {e}", 'ERROR')

        return drivers

    def disable_drivers(self, drivers: Set[str]) -> None:
        """禁用驱动服务"""
        if not drivers:
            return

        ColorOutput.info("\n[*] 开始禁用驱动服务...")

        for driver in drivers:
            try:
                # 停止驱动
                ColorOutput.warning(f"    [!] 停止驱动: {driver}")
                subprocess.run(['sc', 'stop', driver], capture_output=True, timeout=5)

                # 禁用驱动
                ColorOutput.warning(f"    [!] 禁用驱动: {driver}")
                result = subprocess.run(
                    ['sc', 'config', driver, 'start=', 'disabled'],
                    capture_output=True,
                    encoding='gbk',
                    errors='ignore',
                    timeout=5
                )

                if result.returncode == 0 or 'SUCCESS' in result.stdout or '成功' in result.stdout:
                    ColorOutput.success(f"    [✓] 驱动 {driver} 已禁用")
                    self.log(f"禁用驱动: {driver}")
            except Exception as e:
                ColorOutput.error(f"[!] 禁用驱动 {driver} 时出错: {e}")
                self.log(f"禁用驱动 {driver} 时出错: {e}", 'ERROR')

    def find_scheduled_tasks(self) -> None:
        """查找 Sangfor 相关的计划任务"""
        ColorOutput.info("\n[*] 开始查找计划任务...")

        try:
            # 使用 schtasks 命令获取所有计划任务
            result = subprocess.run(
                ['schtasks', '/query', '/fo', 'LIST', '/v'],
                capture_output=True,
                encoding='gbk',
                errors='ignore',
                timeout=10
            )

            if not result.stdout:
                ColorOutput.warning("[!] 无法获取计划任务列表")
                return

            # 解析输出，查找与 Sangfor 相关的任务
            lines = result.stdout.split('\n')
            current_task = None

            for line in lines:
                line = line.strip()
                if '任务名:' in line or 'TaskName:' in line:
                    task_name = line.split(':', 1)[1].strip()
                    current_task = task_name

                    # 检查任务名是否包含 sangfor 关键字
                    if 'sangfor' in task_name.lower():
                        self.scheduled_tasks.add(task_name)
                        ColorOutput.success(f"    [名称匹配] 发现计划任务: {task_name}")
                        self.log(f"发现计划任务（名称匹配）: {task_name}")

                elif ('要运行的程序:' in line or 'Task To Run:' in line) and current_task:
                    program = line.split(':', 1)[1].strip()

                    # 检查程序路径是否包含 sangfor 或 exe 文件名
                    if 'sangfor' in program.lower():
                        if current_task not in self.scheduled_tasks:
                            self.scheduled_tasks.add(current_task)
                            ColorOutput.success(f"    [路径匹配] 发现计划任务: {current_task}")
                            self.log(f"发现计划任务（路径匹配）: {current_task}")
                    else:
                        # 检查是否包含我们的 exe 文件
                        for exe_name in self.exe_files:
                            if exe_name.lower() in program.lower():
                                if current_task not in self.scheduled_tasks:
                                    self.scheduled_tasks.add(current_task)
                                    ColorOutput.success(f"    [程序匹配] 发现计划任务: {current_task} -> {exe_name}")
                                    self.log(f"发现计划任务（程序匹配）: {current_task}")
                                break

            ColorOutput.success(f"\n[+] 共找到 {len(self.scheduled_tasks)} 个相关计划任务")
            self.log(f"共找到 {len(self.scheduled_tasks)} 个计划任务")

        except subprocess.TimeoutExpired:
            ColorOutput.error("[!] 查询计划任务超时")
        except Exception as e:
            ColorOutput.error(f"[!] 查找计划任务时出错: {e}")
            self.log(f"查找计划任务时出错: {e}", 'ERROR')

    def disable_scheduled_tasks(self) -> None:
        """禁用所有 Sangfor 相关的计划任务"""
        ColorOutput.info("\n[*] 开始禁用计划任务...")

        disabled_count = 0
        for task_name in self.scheduled_tasks:
            try:
                ColorOutput.warning(f"    [!] 禁用计划任务: {task_name}")
                self.log(f"禁用计划任务: {task_name}")

                # 禁用计划任务
                result = subprocess.run(
                    ['schtasks', '/change', '/tn', task_name, '/disable'],
                    capture_output=True,
                    encoding='gbk',
                    errors='ignore',
                    timeout=5
                )

                if result.returncode == 0 or 'SUCCESS' in result.stdout or '成功' in result.stdout:
                    ColorOutput.success(f"    [✓] 计划任务 {task_name} 已禁用")
                    disabled_count += 1
                    self.total_tasks_disabled += 1
                else:
                    ColorOutput.error(f"    [×] 禁用计划任务 {task_name} 失败")
            except subprocess.TimeoutExpired:
                ColorOutput.error(f"    [!] 禁用计划任务 {task_name} 超时")
            except Exception as e:
                ColorOutput.error(f"[!] 禁用计划任务 {task_name} 时出错: {e}")
                self.log(f"禁用计划任务 {task_name} 时出错: {e}", 'ERROR')

        if disabled_count > 0:
            ColorOutput.success(f"\n[+] 成功禁用 {disabled_count} 个计划任务")
        else:
            ColorOutput.info("[*] 未禁用任何计划任务")

    def kill_processes(self, kill_watchdog_first: bool = True) -> None:
        """终止所有 Sangfor 相关进程

        Args:
            kill_watchdog_first: 是否优先终止守护进程
        """
        if not self.loop_mode:
            ColorOutput.info("\n[*] 开始终止进程...")

        killed_count = 0
        watchdog_killed = 0

        # 优化：将 exe_files 转为小写集合，避免重复转换
        exe_files_lower = {name.lower() for name in self.exe_files}
        watchdog_lower = {name.lower() for name in self.watchdog_processes}

        # 收集所有目标进程，按父子关系排序（父进程优先）
        target_processes = []

        for proc in psutil.process_iter(['pid', 'name', 'ppid']):
            try:
                proc_name = Path(proc.info['name']).stem.lower()
                if proc_name in exe_files_lower:
                    is_watchdog = proc_name in watchdog_lower
                    target_processes.append({
                        'proc': proc,
                        'name': proc.info['name'],
                        'pid': proc.info['pid'],
                        'ppid': proc.info['ppid'],
                        'proc_name': proc_name,
                        'is_watchdog': is_watchdog
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # 如果要优先终止守护进程，分两轮处理
        if kill_watchdog_first and watchdog_lower:
            # 第一轮：优先终止守护进程和服务进程
            if not self.loop_mode:
                ColorOutput.warning("    [*] 第一步：优先终止守护进程和服务...")

            # 按进程树终止（先终止可能是父进程的守护进程）
            watchdog_procs = [p for p in target_processes if p['is_watchdog']]
            # 按PID排序，低PID通常是父进程
            watchdog_procs.sort(key=lambda x: x['pid'])

            for proc_info in watchdog_procs:
                proc = None
                try:
                    proc = proc_info['proc']
                    if proc.is_running():
                        ColorOutput.warning(f"    [!] 终止守护进程: {proc_info['name']} (PID: {proc_info['pid']})")
                        self.log(f"终止守护进程: {proc_info['name']} (PID: {proc_info['pid']})")
                        proc.kill()
                        proc.wait(timeout=2)  # 等待进程真正退出
                        killed_count += 1
                        watchdog_killed += 1
                        self.total_processes_killed += 1
                except psutil.TimeoutExpired:
                    # 强制终止
                    try:
                        if proc:
                            proc.terminate()
                    except:
                        pass
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                except Exception as e:
                    if not self.loop_mode:
                        ColorOutput.error(f"[!] 终止进程时出错: {e}")
                        self.log(f"终止进程时出错: {e}", 'ERROR')

            if watchdog_killed > 0:
                ColorOutput.success(f"    [✓] 已终止 {watchdog_killed} 个守护进程")
                # 等待一下，让守护进程完全退出
                time.sleep(1)
                if not self.loop_mode:
                    ColorOutput.info("    [*] 第二步：终止其他进程...")

        # 第二轮：终止所有其他进程（按PID排序，低PID优先）
        other_procs = [p for p in target_processes if not p['is_watchdog']]
        other_procs.sort(key=lambda x: x['pid'])

        for proc_info in other_procs:
            proc = None
            try:
                proc = proc_info['proc']
                if proc.is_running():
                    ColorOutput.warning(f"    [!] 终止进程: {proc_info['name']} (PID: {proc_info['pid']})")
                    self.log(f"终止进程: {proc_info['name']} (PID: {proc_info['pid']})")
                    proc.kill()
                    proc.wait(timeout=1)
                    killed_count += 1
                    self.total_processes_killed += 1
            except psutil.TimeoutExpired:
                try:
                    if proc:
                        proc.terminate()
                except:
                    pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception as e:
                if not self.loop_mode:
                    ColorOutput.error(f"[!] 终止进程时出错: {e}")
                    self.log(f"终止进程时出错: {e}", 'ERROR')

        if killed_count > 0:
            ColorOutput.success(f"    [✓] 本轮终止 {killed_count} 个进程")
        elif not self.loop_mode:
            ColorOutput.info(f"    [-] 未发现运行中的目标进程")

    def stop_services(self) -> None:
        """停止所有 Sangfor 相关服务"""
        if not self.loop_mode:
            ColorOutput.info("\n[*] 开始停止服务...")

        stopped_count = 0
        for service_name in self.service_names:
            try:
                # 先检查服务状态
                status_output = run_sc_command(['sc', 'query', service_name], timeout=2)

                if not status_output:
                    continue

                # 如果服务正在运行，才尝试停止
                if 'RUNNING' in status_output:
                    ColorOutput.warning(f"    [!] 停止服务: {service_name}")
                    self.log(f"停止服务: {service_name}")

                    stop_output = run_sc_command(['sc', 'stop', service_name], timeout=5)

                    if stop_output and ('已发送停止控制' in stop_output or 'STOP_PENDING' in stop_output):
                        ColorOutput.success(f"    [✓] 服务 {service_name} 已停止")
                        stopped_count += 1
                        self.total_services_stopped += 1
                    else:
                        if not self.loop_mode:
                            ColorOutput.error(f"    [×] 停止服务 {service_name} 失败")
            except Exception as e:
                if not self.loop_mode:
                    ColorOutput.error(f"[!] 停止服务 {service_name} 时出错: {e}")
                    self.log(f"停止服务 {service_name} 时出错: {e}", 'ERROR')

        if stopped_count > 0:
            ColorOutput.success(f"    [✓] 本轮停止 {stopped_count} 个服务")
        elif not self.loop_mode:
            ColorOutput.info(f"    [-] 未发现运行中的目标服务")

    def disable_services_startup(self) -> None:
        """禁用所有 Sangfor 相关服务的自动启动"""
        ColorOutput.info("\n[*] 开始禁用服务自动启动...")

        disabled_count = 0
        for service_name in self.service_names:
            try:
                ColorOutput.warning(f"    [!] 禁用服务: {service_name}")
                self.log(f"禁用服务自动启动: {service_name}")

                # 设置服务启动类型为禁用
                result = subprocess.run(
                    ['sc', 'config', service_name, 'start=', 'disabled'],
                    capture_output=True,
                    encoding='gbk',
                    errors='ignore',
                    timeout=5
                )

                if result.returncode == 0 or 'SUCCESS' in result.stdout or '成功' in result.stdout:
                    ColorOutput.success(f"    [✓] 服务 {service_name} 已设置为禁用")
                    disabled_count += 1
                    self.total_services_disabled += 1
                else:
                    ColorOutput.error(f"    [×] 禁用服务 {service_name} 失败")
            except subprocess.TimeoutExpired:
                ColorOutput.error(f"    [!] 禁用服务 {service_name} 超时")
            except Exception as e:
                ColorOutput.error(f"[!] 禁用服务 {service_name} 时出错: {e}")
                self.log(f"禁用服务 {service_name} 时出错: {e}", 'ERROR')

        if disabled_count > 0:
            ColorOutput.success(f"\n[+] 成功禁用 {disabled_count} 个服务")
        else:
            ColorOutput.info("[*] 未禁用任何服务")

    def run(self) -> None:
        """运行主程序"""
        # 初始化彩色输出
        ColorOutput.init()

        ColorOutput.header("=" * 60)
        ColorOutput.header("Sangfor Killer - 自动终止 Sangfor 相关进程和服务")
        ColorOutput.header("=" * 60)

        # 检查管理员权限
        is_admin = False
        try:
            # Windows 系统
            if sys.platform == 'win32':
                is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore
            else:
                # Unix-like 系统
                is_admin = os.getuid() == 0
        except Exception:
            pass

        if not is_admin:
            ColorOutput.warning("\n[!] 警告: 未以管理员身份运行，可能无法终止某些进程或服务")
            ColorOutput.warning("[!] 建议以管理员身份重新运行此脚本\n")
        else:
            ColorOutput.success("\n[✓] 已获取管理员权限\n")

        # 自动启用日志记录
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = log_dir / f"sangfor_killer_{timestamp}.log"
        ColorOutput.success(f"[✓] 已启用日志记录: {self.log_file}")
        self.log("=== Sangfor Killer 开始运行 ===")

        # 自动启用循环监控模式
        self.loop_mode = True
        ColorOutput.success("[✓] 已启用循环监控模式（按 Ctrl+C 停止）")
        self.log("启用循环监控模式")

        # 自动启用禁用服务功能
        self.disable_services = True
        ColorOutput.success("[✓] 已启用禁用服务自动启动功能")
        ColorOutput.success("[✓] 已启用禁用计划任务功能\n")
        self.log("启用禁用服务和计划任务功能")

        # 1. 查找 Sangfor 目录
        sangfor_dirs = self.find_sangfor_directories()
        
        if not sangfor_dirs:
            ColorOutput.warning("\n[*] 未找到任何 Sangfor 目录，程序退出")
            self.log("未找到任何 Sangfor 目录")
            return
        
        # 2. 收集 .exe 文件
        self.collect_exe_files(sangfor_dirs)
        
        if not self.exe_files:
            ColorOutput.warning("\n[*] 未找到任何 .exe 文件")
            self.log("未找到任何 .exe 文件")

        # 3. 查找服务
        self.find_services(sangfor_dirs)
        
        # 4. 查找驱动服务
        drivers = self.find_drivers()

        # 5. 查找计划任务
        self.find_scheduled_tasks()

        # 6. 分析重启源
        self.analyze_restart_sources()

        # 7. 先禁用所有重启源（循环监控开始前）
        # 禁用驱动
        if drivers:
            self.disable_drivers(drivers)
            self.total_drivers_disabled = len(drivers)

        # 禁用服务
        if self.service_names:
            ColorOutput.info("\n[*] 开始停止服务...")
            self.stop_services()

            if self.disable_services:
                self.disable_services_startup()

        # 禁用计划任务
        if self.scheduled_tasks:
            self.disable_scheduled_tasks()

        # 8. 执行终止操作
        if self.loop_mode:
            # 循环监控模式
            ColorOutput.header("\n" + "=" * 60)
            ColorOutput.header("[*] 开始循环监控...")
            ColorOutput.header("=" * 60)

            iteration = 0
            try:
                while True:
                    iteration += 1
                    ColorOutput.info(f"\n--- 第 {iteration} 轮检测 ({time.strftime('%H:%M:%S')}) ---")

                    # 终止进程
                    if self.exe_files:
                        self.kill_processes()

                    # 停止服务
                    if self.service_names:
                        self.stop_services()
                    
                    print(f"[*] 等待 1 秒后继续...")
                    time.sleep(1)
            except KeyboardInterrupt:
                ColorOutput.warning("\n\n[!] 用户停止循环监控")
                self.log("用户停止循环监控")
        else:
            # 单次执行
            if self.exe_files:
                self.kill_processes()
            
            if self.service_names:
                self.stop_services()

                # 禁用服务
                if self.disable_services:
                    self.disable_services_startup()

            # 禁用计划任务
            if self.scheduled_tasks:
                self.disable_scheduled_tasks()

        # 显示统计摘要
        ColorOutput.header("\n" + "=" * 60)
        ColorOutput.header("[*] 操作统计摘要")
        ColorOutput.header("=" * 60)
        ColorOutput.success(f"总计终止进程: {self.total_processes_killed} 个")
        ColorOutput.success(f"总计停止服务: {self.total_services_stopped} 个")
        if self.total_services_disabled > 0:
            ColorOutput.success(f"总计禁用服务: {self.total_services_disabled} 个")
        if self.total_drivers_disabled > 0:
            ColorOutput.success(f"总计禁用驱动: {self.total_drivers_disabled} 个")
        if self.total_tasks_disabled > 0:
            ColorOutput.success(f"总计禁用计划任务: {self.total_tasks_disabled} 个")

        ColorOutput.header("\n" + "=" * 60)
        ColorOutput.header("[*] 所有操作完成！")
        ColorOutput.header("=" * 60)

        self.log(f"操作完成 - 终止进程: {self.total_processes_killed}, 停止服务: {self.total_services_stopped}, 禁用服务: {self.total_services_disabled}, 禁用驱动: {self.total_drivers_disabled}, 禁用计划任务: {self.total_tasks_disabled}")
        self.log("=== Sangfor Killer 运行结束 ===")


def main():
    """主函数"""
    try:
        killer = SangforKiller()
        killer.run()
    except KeyboardInterrupt:
        ColorOutput.warning("\n\n[!] 用户中断操作")
        sys.exit(1)
    except Exception as e:
        ColorOutput.error(f"\n[!] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
