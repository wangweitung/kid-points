# ⭐ 小星星积分计划（kid-points）

给小朋友做积分统计的 Web 应用，按《小星星积分计划 Morning.xlsx》模板实现：
每日打卡、周积分卡、积分存折、兑换管理、月度图表。

单容器部署：**Flask + SQLite + 服务端渲染 + Chart.js**，镜像内部端口 `80`，通过外部端口映射访问。
移动端顶栏自适应（≤860px 收起为汉堡菜单，点开下拉面板选页；桌面端保持单行横向导航）。

## 功能

| 页面 | 说明 |
|---|---|
| 首次使用 | 自动进入初始化页，创建管理员账号和密码 |
| 登录 / 注册 | 管理员可开启或关闭注册（默认关闭） |
| 今日打卡 | 按任务打 √ / 取消，实时计算今日得分与余额；顶部可切换小朋友 |
| 周视图 | 完整周积分卡：任务 × 周一~周日（表头为日期 + 星期，今天高亮）、未来日期不可打卡、本周得分、完成天数、本周结算（期初结余 / 本周得分 / 合计可用 / 本周兑换 / 转入下周）、兑换价目、「本周最棒的一件事」 |
| 月视图 | 月历网格（周一~周日）：每格显示当天得分、今天高亮、灰色为未来日期；点某天进入该周积分卡；上月 / 本月 / 下月切换，含余额、本月得分、打卡天数 |
| 积分存折 | 期初余额、收入 / 支出 / 余额流水，每日得分自动生成；手动记账与删除由管理员操作 |
| 兑换 | 兑换价目表，余额不足自动禁用；登记兑换与维护价目均为管理员操作，普通用户只读 |
| 图表 | 按月展示：每日得分、余额走势、支出构成、各任务完成次数 + 数据表；含本月得分 / 本月支出 / 月末余额 / 打卡天数统计卡 |
| 说明 | 使用说明与三条红线（来自原 Excel 模板） |
| 管理 | 任务 / 小朋友管理、用户角色变更与删除、密码重置、注册开关、过去日期修改开关 |

权限：所有页面需登录；打卡所有登录用户可操作，存折手动记账、兑换登记、价目维护、管理页仅管理员。
没有小朋友时会进入引导页，提示先到「管理」页添加。
业务日期一律按北京时间（UTC+8）判定「今天」，与服务器 / 容器时区无关。
打卡默认只能改今天，过去日期不可修改（未来日期始终禁止）；需要补记或纠正时，
管理员在「管理」页开启「过去日期修改」即可，键为 `allow_past_edit`。

数据模型与 Excel 模板对应：任务（做什么 + 分值）、打卡（√）、存折（期初 + 收入 − 支出）、兑换价目、周记（本周最棒的一件事）；
另有 `users`（登录账号）、`settings`（注册开关）两张非模板表。

## 快速开始（Docker）

```bash
# 方式一：docker run
docker build -t kid-points .
docker run -d --name kid-points -p 8080:80 -v kid-points-data:/data kid-points

# 方式二：docker compose（数据存放在 ./data，端口映射 1208）
docker compose up -d
```

浏览器打开 `http://localhost:8080`（方式一）或 `http://localhost:1208`（方式二），首次访问创建管理员账号。

- **内部端口**：`80`（容器内 gunicorn 监听）
- **外部端口**：映射处任意，如 `-p 8080:80`；compose 见 `docker-compose.yml` 的 `1208:80`
- **数据卷**：`/data`（SQLite 数据库 `points.db` 和会话密钥 `secret_key`），务必备份
- **健康检查**：`GET /healthz` 返回 `ok`，Dockerfile 的 `HEALTHCHECK` 依赖它

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

`docker-compose.yml` 已固定 `image: wangweitung/kid-points:latest`，可直接 `docker compose up -d` 拉取，无需本地构建。

## 备份与恢复

数据全部在 `/data` 中。方式一（named volume `kid-points-data`）：

```bash
# 备份
docker run --rm -v kid-points-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/kid-points-backup.tar.gz -C /data .

# 恢复
docker run --rm -v kid-points-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/kid-points-backup.tar.gz -C /data
```

方式二（compose，bind mount 到 `./data`）直接打包目录即可：

```bash
tar czf kid-points-backup.tar.gz -C ./data .
tar xzf kid-points-backup.tar.gz -C ./data
```

## 本地开发

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# DATA_DIR 可选，默认即 ./data
$env:DATA_DIR = "data"

.venv\Scripts\python -m flask --app wsgi run
```

`wsgi.py` 只构造 app 对象供 gunicorn 使用，本身不含 `app.run()`，直接 `python wsgi.py` 不会启动服务。

## 目录结构

```
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── wsgi.py                  # gunicorn 入口（仅 create_app，不监听端口）
├── .github/workflows/       # GitHub Actions 自动构建镜像
├── 小星星积分计划 Morning.xlsx  # 需求与数据模板
└── app/
    ├── __init__.py          # 应用工厂、登录守卫、/healthz
    ├── db.py                # SQLite schema 与种子数据（来自 Excel 模板）
    ├── helpers.py           # 权限装饰器、余额 / 周结算 / 每日得分同步
    ├── auth.py              # 初始化管理员 / 登录 / 注册 / 退出
    ├── views.py             # 打卡、周视图、月视图、存折、兑换、图表
    ├── admin.py             # 管理页
    ├── templates/           # Jinja2 模板（narrow.html 为登录类窄版布局）
    └── static/              # 样式、交互脚本、内置 Chart.js
```
