# Sangfor Killer

一个用于自动检测并终止 Sangfor 相关进程、服务和驱动的 Windows 工具。

## 功能特性

- 🔍 自动扫描所有磁盘中的 Sangfor 目录
- 🛑 终止所有 Sangfor 相关进程
- ⚙️ 停止/禁用 Sangfor 服务
- 🚫 禁用 Sangfor 驱动程序
- 📋 禁用计划任务
- 🔄 循环监控（防止进程自动重启）

## 系统要求

- Windows 操作系统
- Python 3.6+
- 管理员权限

## 安装

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/Sangfor-Killer.git
cd Sangfor-Killer
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

### 基础用法

以管理员权限运行：

```bash
python main.py
```

或直接运行 `run_as_admin.bat`

### 禁止守护进程

观察控制台输出，若守护进程无法彻底结束，可以配合火绒【访问控制】-【程序执行控制】-【自定义规则】，限定指定的应用程序执行

## 注意事项

⚠️ **警告**：

- 本工具需要管理员权限运行
- 请确保了解终止这些进程可能产生的影响
- 仅供学习和研究使用，请遵守相关法律法规

