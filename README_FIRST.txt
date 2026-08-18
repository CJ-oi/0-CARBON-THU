零碳园区网站文字与PDF下载修复包（Windows兼容版）

本压缩包已重新打包，内部路径全部使用ASCII文件名，避免Windows解压后显示为空或乱码。

用途：
1. 删除公开页面中的邮件发送入口；
2. 报告中心改为直接下载PDF；
3. 删除“无悔”等不适合公开展示的表述；
4. 保留本地矢量地图，不再依赖在线地图瓦片；
5. 删除邮件部署工作流与邮件服务目录。

使用方法：
1. 解压本压缩包；
2. 将解压后看到的 .github、config、data、docs、outputs、scripts、site、src、static、tests 等内容复制到本地 0-CARBON-THU 仓库根目录；
3. 选择“替换目标中的文件”；
4. 在仓库根目录右键运行 apply_patch.ps1（若系统阻止，可手动删除下列旧文件）；
5. 在 GitHub Desktop 中 Commit to main，然后 Push origin；
6. 等待主网站工作流全部变绿，再 Ctrl+F5 刷新网页。

需删除的旧邮件文件：
- .github/workflows/deploy-mailer.yml
- services/report-mailer/
- docs/EMAIL_DELIVERY.md
- static/docs/email-setup.html
- site/docs/email-setup.html

校验信息见 PATCH_MANIFEST.txt。
