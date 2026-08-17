# 部署说明

## 一、发布到 GitHub Pages

1. 在 GitHub 新建一个公开仓库，例如 `zero-carbon-park-observatory`。
2. 将本目录全部文件推送到仓库 `main` 分支。
3. 打开仓库 `Settings → Pages`，将 `Source` 设为 **GitHub Actions**。
4. 打开 `Actions`，手动运行一次“更新并发布园区碳观察”，或等待首次推送触发。
5. 工作流完成后，Pages 页面会显示公开网址。

仓库中不需要保存 API 密钥。默认采集和报告流程只使用 Python 标准库及公开来源。

## 二、定时更新

`.github/workflows/pages.yml` 每 6 小时触发一次：

1. 读取来源配置；
2. 逐个检查公开页面；
3. 对新记录执行规范 URL 去重和内容哈希；
4. 更新滚动档案与来源健康；
5. 运行核算、项目组合和可行性测试；
6. 生成日报、周报、演示可行性报告和静态网站；
7. 自动截取首页、地图和五项工作界面并生成 PDF；
8. 运行页面质量门禁和浏览器功能验收；
9. 通过全部检查后发布；
10. 将档案和来源健康提交回仓库。

GitHub Actions 的定时任务是周期性更新，不是秒级实时流。政策和园区公开信息本身也通常按日或按周发布，因此每 6 小时检查可满足持续更新需要。

## 三、自定义来源

编辑 `config/sources.json`：

- `start_url`：公开入口页；
- `allowed_domains`：允许跟踪的域名；
- `priority`：P0/P1；
- `enabled`：是否启用；
- `keywords`：全局筛选词。

新来源应先核验：公开访问、内容范围、版权边界、更新频率和稳定性。

## 四、自定义域名

在 `site/` 中增加 `CNAME`，或在 GitHub Pages 设置中填写域名。每次构建会重建 `site/`，建议在 `static/CNAME` 中保存域名，以便自动复制。

## 五、其他静态托管

执行：

```bash
zcpark build --output site --feasibility-input data/assessments/example.json
```

将 `site/` 整体上传至 Cloudflare Pages、Netlify、对象存储静态网站或普通 Web 服务器即可。
