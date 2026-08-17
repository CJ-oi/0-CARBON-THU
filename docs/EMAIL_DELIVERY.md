# 报告邮件发送配置

## 1. 为什么需要单独的发送服务

GitHub Pages 只能发布静态网页，不能安全保存邮件服务密钥。网站中的邮箱输入框因此分为两种工作方式：

- 未配置发送服务：打开本机默认邮件客户端，并自动填写收件人、主题和报告链接；
- 已配置发送服务：网页将报告类型和收件邮箱发送给 Cloudflare Worker，由 Worker 从公开网站读取最新 PDF，再通过 Resend 发送附件。

邮箱不会写入 GitHub 仓库，网站也不会建立订阅名单。

## 2. 准备事项

1. 一个 Cloudflare 账号；
2. 一个 Resend 账号；
3. 一个已验证的发件域名，建议使用项目单位或个人拥有的域名；
4. 已发布的网站地址，例如 `https://cj-oi.github.io/zero-carbon-park/`。

## 3. 部署 Cloudflare Worker

在仓库根目录打开 PowerShell：

```powershell
cd services\report-mailer
npm install
Copy-Item wrangler.toml.example wrangler.toml
```

编辑 `wrangler.toml`：

```toml
[vars]
SITE_URL = "https://cj-oi.github.io/zero-carbon-park/"
ALLOWED_ORIGIN = "https://cj-oi.github.io"
REPORT_FROM = "园区碳观察 <reports@你的已验证域名>"
```

登录 Cloudflare 并写入 Resend 密钥：

```powershell
npx wrangler login
npx wrangler secret put RESEND_API_KEY
npm run deploy
```

部署完成后会得到类似：

```text
https://park-report-mailer.你的子域.workers.dev
```

## 4. 将发送端点写入网站

编辑 `config/runtime.json`：

```json
{
  "site_url": "https://cj-oi.github.io/zero-carbon-park/",
  "repository_url": "https://github.com/CJ-oi/zero-carbon-park/",
  "issues_url": "https://github.com/CJ-oi/zero-carbon-park/issues/new/choose",
  "mail_endpoint": "https://park-report-mailer.你的子域.workers.dev",
  "turnstile_site_key": "",
  "mail_mode": "worker"
}
```

提交并推送后，GitHub Actions 会重建网站。网页的“发送报告”按钮将直接调用 Worker。

## 5. 安全建议

- 不要把 `RESEND_API_KEY` 写入仓库；
- 发件域名应配置 SPF、DKIM；
- 正式公开前建议启用 Cloudflare Turnstile 和 Rate Limiting；
- Worker 只允许来自指定 GitHub Pages 源站的 POST 请求；
- 可行性报告的网页即时测算摘要只用于邮件正文，Worker 会进行长度限制和 HTML 转义；
- PDF 始终从公开网站固定路径读取，不接受用户提供的任意文件地址。

## 6. 验收

1. 打开 Worker 地址，GET 请求应返回 `{"ok":true}`；
2. 在网站中输入邮箱并勾选本次发送授权；
3. 选择周报或可行性报告；
4. 点击“发送报告”；
5. 收件箱应收到 PDF 附件，垃圾邮件目录也应检查；
6. 可行性报告邮件应包含当前网页测算摘要和在线报告链接。

## 7. 也可以从 GitHub Actions 部署

仓库提供 `.github/workflows/deploy-mailer.yml`。首次使用前：

1. 在 Cloudflare 创建 API Token，并授予 Workers Scripts 编辑权限；
2. 在 GitHub 仓库 `Settings → Secrets and variables → Actions` 中添加：
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
3. 将 `services/report-mailer/wrangler.toml` 中的 `REPORT_FROM` 改成已在 Resend 验证的发件地址；
4. 通过 Wrangler 或 Cloudflare 控制台为 Worker 添加密钥 `RESEND_API_KEY`；
5. 在 GitHub `Actions → 部署报告邮件发送服务 → Run workflow` 手动部署。

部署完成后仍需把 Worker 地址写入 `config/runtime.json` 的 `mail_endpoint`。只有这一步完成，公开网页才会直接发送附件；否则网页继续使用安全的本机邮件客户端回退方式。
