# NPM Meta - Nginx Proxy Manager 增强工具

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 项目简介

**NPM Meta** 是一个为 [Nginx Proxy Manager](https://nginxproxymanager.com/) 设计的增强型管理工具，解决了 NPM 原生界面不支持**备注**和**标签**的痛点。

### ✨ 主要功能

- 📝 **备注管理**：为每个端口转发添加详细备注说明
- 🔗 **快捷链接**：支持添加文档地址、在线测试、代码仓库等快捷链接
- 🔢 **端口自增**：新增转发时自动计算下一个可用端口
- 🔐 **统一登录**：使用 NPM 账号登录，无需额外注册
- 💾 **本地存储**：备注数据存储在本地 SQLite 数据库

## 🖼️ 界面预览

系统提供简洁美观的 Web 管理界面：

- 清晰展示所有端口转发规则
- 一键复制访问地址
- 快速跳转到相关文档

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/CoderXiaopang/Nginx-Proxy-Manager-Enhance.git
cd Nginx-Proxy-Manager-Enhance
```

### 2. 安装依赖

```bash
pip install flask requests
```

### 3. 配置环境变量

复制环境变量示例文件并修改：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置你的 NPM 服务器地址：

```ini
# Nginx Proxy Manager 服务器地址
NPM_HOST=your-npm-server:81
```

### 4. 启动服务

```bash
python app.py
```

访问 `http://localhost:5001` 即可使用。

## 📁 项目结构

```
npm-meta/
├── app.py              # Flask 主应用
├── templates/
│   ├── loginh.html     # 登录页面
│   └── memang.html     # 管理页面
├── .env.example        # 环境变量示例
├── .gitignore          # Git 忽略文件
└── README.md           # 项目说明
```

## ⚙️ 配置说明

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `NPM_HOST` | NPM 服务器地址（含端口） | `192.168.1.100:81` |

## 🔧 技术栈

- **后端**：Python 3.8+ / Flask
- **前端**：原生 HTML/CSS/JavaScript
- **数据库**：SQLite（轻量级，无需安装）
- **API**：对接 Nginx Proxy Manager REST API

## 📄 API 接口

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | `/api/login` | 用户登录 |
| POST | `/api/logout` | 用户登出 |
| GET | `/api/streams` | 获取转发列表 |
| POST | `/api/streams` | 创建新转发 |
| DELETE | `/api/streams/<id>` | 删除转发 |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📜 License

MIT License
