# ⭐ 小星星积分计划（kid-points）

给小朋友做积分统计的 Web 应用，按《小星星积分计划 Morning.xlsx》模板实现：
每日打卡、周积分卡、积分存折、兑换管理、月度图表。

单容器部署：**Flask + SQLite + 服务端渲染 + Chart.js**，镜像内部端口 `80`，通过外部端口映射访问。

## 功能

| 页面 | 说明 |
|---|---|
| 首次使用 | 自动进入初始化页，创建管理员账号和密码 |
| 登录 / 注册 | 管理员可开启或关闭注册 |
| 今日打卡 | 按任务打 √ / 取消，实时计算今日得分与余额 |
| 周视图 | 完整周积分卡：任务 × 周一~周日、本周得分、完成天数、本周结算（期初结余 / 合计可用 / 转入下周）、兑换价目、「本周最棒的一件事」 |
| 积分存折 | 期初余额、收入 / 支出 / 余额流水，每日得分自动生成，支持手动记账 |
| 兑换 | 兑换价目表，余额不足自动禁用；管理员可维护价目 |
| 图表 | 按月展示：每日得分、余额走势、支出构成、各任务完成次数 + 数据表 |
| 说明 | 使用说明与三条红线（来自原 Excel 模板） |
| 管理 | 任务 / 小朋友 / 用户管理、注册开关、密码重置 |

数据模型与 Excel 模板对应：任务（做什么 + 分值）、打卡（√）、存折（期初 + 收入 − 支出）、兑换价目。

## 快速开始（Docker）

```bash
# 方式一：docker run
docker build -t kid-points .
docker run -d --name kid-points -p 8080:80 -v kid-points-data:/data kid-points

# 方式二：docker compose（数据存放在 ./data）
docker compose up -d
```

浏览器打开 `http://localhost:8080`，首次访问创建管理员账号。

- **内部端口**：`80`（容器内 gunicorn 监听）
- **外部端口**：映射处任意，如 `-p 8080:80`
- **数据卷**：`/data`（SQLite 数据库 `points.db` 和会话密钥），务必备份此卷

## 推送到 GitHub 后自动构建镜像

仓库已含 `.github/workflows/docker-publish.yml`，推送到 `main` 分支（或打 `v*` 标签）会自动构建并推送镜像到 Docker Hub。

只需在 GitHub 仓库 **Settings → Secrets and variables → Actions** 配置两个 secret：

| Secret | 说明 |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub 用户名 |
| `DOCKERHUB_TOKEN` | Docker Hub 访问令牌（https://hub.docker.com/settings/security） |

镜像地址为 `<DOCKERHUB_USERNAME>/kid-points`，之后拉取即可：

```bash
docker pull <DOCKERHUB_USERNAME>/kid-points:latest
docker run -d -p 8080:80 -v kid-points-data:/data <DOCKERHUB_USERNAME>/kid-points:latest
```

## 备份与恢复

数据全部在数据卷 `/data` 中：

```bash
# 备份
docker run --rm -v kid-points-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/kid-points-backup.tar.gz -C /data .

# 恢复
docker run --rm -v kid-points-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/kid-points-backup.tar.gz -C /data
```

## 本地开发

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set DATA_DIR=data          # 可选，默认即 ./data
.venv\Scripts\python wsgi.py   # 或 flask --app wsgi run
```

## 目录结构

```
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── wsgi.py                  # gunicorn 入口
├── .github/workflows/       # GitHub Actions 自动构建镜像
└── app/
    ├── __init__.py          # 应用工厂、登录守卫
    ├── db.py                # SQLite schema 与种子数据（来自 Excel 模板）
    ├── auth.py              # 初始化管理员 / 登录 / 注册 / 退出
    ├── views.py             # 打卡、周视图、存折、兑换、图表
    ├── admin.py             # 管理页
    ├── templates/           # Jinja2 模板
    └── static/              # 样式、交互脚本、内置 Chart.js
```
