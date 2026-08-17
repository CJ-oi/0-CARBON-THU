# 报告邮件发送服务

GitHub Pages 只能发布静态文件，不能安全保存邮件 API 密钥。本目录提供一个可选的 Cloudflare Worker：网页把收件邮箱和报告类型提交给 Worker；Worker 从公开网站读取对应 PDF，再通过 Resend 发送附件。邮箱不会写入 Git 仓库。

部署前复制 `wrangler.toml.example` 为 `wrangler.toml`，填写已经验证的发件域名，然后设置密钥：

```bash
npm install
npx wrangler secret put RESEND_API_KEY
# 可选：启用 Cloudflare Turnstile
npx wrangler secret put TURNSTILE_SECRET_KEY
npm run deploy
```

将部署得到的 Worker 地址写入根目录 `config/runtime.json` 的 `mail_endpoint`，重新构建并发布网站。生产环境建议启用 Turnstile、Cloudflare Rate Limiting 和发件域名的 SPF/DKIM。
