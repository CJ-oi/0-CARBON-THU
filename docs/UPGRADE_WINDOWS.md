# Windows 更新现有 GitHub 网站

适用于仓库：`https://github.com/CJ-oi/zero-carbon-park/`

本次更新采用“覆盖源码、保留本地 `.git`、通过 GitHub Desktop 提交”的方式。更新后，原来的 GitHub Pages 地址保持不变。

## 1. 下载并解压

下载文件：

```text
零碳园区公共数据与实施决策平台_全面升级源码包.zip
```

右键压缩包，选择“全部解压”。解压后应能直接看到以下目录和文件：

```text
.github
config
data
docs
scripts
services
src
static
tests
README.md
pyproject.toml
```

不要把压缩包本身上传到 GitHub，也不要只复制 `site` 目录。

## 2. 备份现有仓库

1. 打开 GitHub Desktop；
2. 选择仓库 `CJ-oi/zero-carbon-park`；
3. 确认顶部没有尚未提交的本地改动；
4. 点击 `Repository → Show in Explorer`；
5. 将整个 `zero-carbon-park` 文件夹复制一份，作为本地备份。

## 3. 覆盖升级文件

1. 打开刚才解压得到的源码目录；
2. 全选其中的文件和文件夹，包括 `.github`；
3. 复制到 GitHub Desktop 当前仓库的本地目录；
4. Windows 询问时选择“替换目标中的文件”；
5. 不要删除仓库根目录中的 `.git` 文件夹。

覆盖完成后，仓库根目录应同时存在：

```text
.git
.github
config
data
docs
scripts
services
src
static
tests
```

## 4. 提交和推送

回到 GitHub Desktop。左侧会显示本次新增和修改的文件。

在左下角填写：

```text
Summary: 全面升级页面、地图、报告与可行性分析
```

然后依次点击：

```text
Commit to main
Push origin
```

不要在 GitHub Actions 尚未运行结束时再次推送其他提交。

## 5. 查看自动构建

打开仓库网页，进入：

```text
Actions → 更新并发布园区碳观察
```

工作流会依次完成：

1. 检查并增量合并公开信息；
2. 执行标题、文号、规范网址和正文指纹去重；
3. 进行相关性筛选、分类校正和来源健康检查；
4. 构建园区数据库、坐标审核表和在线地图；
5. 生成日报、周报和可行性初筛报告；
6. 截取首页、地图和五项工作界面并写入报告；
7. 生成 PDF；
8. 运行 Python 测试、页面质量门禁和浏览器功能验收；
9. 发布 GitHub Pages。

全部步骤变绿后，等待约 1—3 分钟，再打开：

```text
https://cj-oi.github.io/zero-carbon-park/
```

建议按 `Ctrl + F5` 强制刷新，避免浏览器继续使用旧缓存。

## 6. 发布后检查

- 首页是否采用新的紧凑布局；
- 在线地图是否显示真实网络底图，并能缩放和拖动；
- 园区点位是否落在相应省市或国家；
- 网络地图不可用时是否自动显示简化矢量备用图；
- 园区资料卡是否显示经纬度、坐标精度、来源和复核日期；
- 近期动态是否没有同题重复和明显误分类；
- 周报是否包含数据质量、实施主题、机会、约束、补数任务和界面截图；
- 指标核算后是否自动形成减排建议；
- 可行性分析是否显示项目组合、年度路径和三种敏感性情景；
- 报告 HTML、PDF、Markdown 和 JSON 链接是否可以打开；
- 邮件未配置时是否正常打开本机邮件客户端。

## 7. 启用网页直接发送 PDF

网站默认使用本机邮件客户端发送报告链接。要从网页直接向输入邮箱发送 PDF，需要单独部署安全的邮件发送服务。完整步骤见：

```text
docs/EMAIL_DELIVERY.md
```

这一步需要 Cloudflare、Resend 和一个已验证的发件域名。邮件密钥不得写入公开 GitHub 仓库。

## 8. 出错处理

若 Actions 出现红色错误：

1. 点击失败的运行记录；
2. 打开红色步骤；
3. 复制最后 30 行日志；
4. 不要先自行删除数据文件；
5. 保存错误截图和本次提交编号。

地图点位、园区名称、来源或计算问题也可通过仓库中的 Issue 模板提交，并附上正确坐标、正式文件或原始来源。
