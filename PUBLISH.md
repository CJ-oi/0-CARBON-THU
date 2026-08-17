# 公开发布与更新说明

当前公开仓库：`https://github.com/CJ-oi/zero-carbon-park/`  
当前公开网站：`https://cj-oi.github.io/zero-carbon-park/`

## 一、更新现有仓库

Windows 建议使用 GitHub Desktop：

1. 确认本地仓库没有未提交改动；
2. 备份本地 `zero-carbon-park` 文件夹；
3. 将升级包源码中的全部文件复制到本地仓库根目录；
4. 保留本地 `.git` 文件夹；
5. 在 GitHub Desktop 中提交：`全面升级页面、地图、报告与数据质量规则`；
6. 点击 `Push origin`；
7. 打开 GitHub `Actions`，等待全部步骤变绿；
8. 刷新公开网站。

详细步骤见 `docs/UPGRADE_WINDOWS.md`。

## 二、自动工作流

`.github/workflows/pages.yml` 在以下情况运行：

- 推送到 `main`；
- Actions 页面手动触发；
- 每 6 小时定时检查。

工作流依次执行：

1. 读取公开来源；
2. 相关性筛选、事件归并和来源健康更新；
3. 构建坐标审核表和矢量地图；
4. 运行 Python 测试；
5. 构建页面、日报、周报和可行性报告；
6. 自动截取页面并渲染 PDF；
7. 检查网页、链接、按钮和 JavaScript；
8. 提交增量数据；
9. 发布 GitHub Pages。

质量门禁失败时不会覆盖上一版成功网站。

## 三、报告邮件发送

GitHub Pages 本身不能保存邮件密钥。可选发送服务位于：

```text
services/report-mailer/
```

部署 Cloudflare Worker 和 Resend 后，将 Worker 地址写入 `config/runtime.json` 的 `mail_endpoint`。详细步骤见 `docs/EMAIL_DELIVERY.md`。

## 四、常用修改位置

- 网站名称与说明：`config/site.json`
- 公开来源：`config/sources.json`
- 内容筛选和分类比例：`config/content_policy.json`
- 园区与坐标：`data/park_catalog.csv`
- 数据字段：`data/required_data_fields.csv`
- 减排设施：`data/technology_guidance.csv`
- 国家指标：`data/standard_rules.csv`
- 邮件和仓库地址：`config/runtime.json`

## 五、发布后检查

- 地图边界是否完整；
- 点位是否落在相应省市或国家；
- 动态是否有同题重复或明显无关内容；
- 周报是否包含数据质量摘要和截图；
- 五问工作台按钮是否全部可用；
- 自动减排建议是否与差距结果对应；
- 可行性报告是否可打开、打印和下载；
- 邮件未配置时是否正常打开本机邮件客户端；
- 邮件配置后是否收到 PDF 附件。

## 六、本地验证

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
zcpark build --output site --feasibility-input data/assessments/example.json
python scripts/capture_and_render.py --site site
zcpark validate --site site
node --check static/app.js
node --check services/report-mailer/src/index.js
```
