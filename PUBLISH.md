# 开源发布说明

本目录为 **TenderCrawler 开源发布快照**，可直接作为 GitHub 仓库根目录推送。

## 与开发目录的差异

| 项 | 处理 |
|----|------|
| `output/` | 仅保留 `.gitkeep`，不含本地抓取数据 |
| `openclaw.config.example.json5` | 路径已替换为占位符 `C:/Users/me/TenderCrawler` |
| `.gitignore` | 已修正：`templates/` 保留，`output/*` 与调试文件排除 |
| 个人路径 / 用户名 | 已移除 |
| `_detail.html`、`*.code-workspace` | 未包含 |
| 逆向参考脚本（`des.js`、`_probe*.py` 等） | 未包含 |

## 推送到 GitHub

```bash
cd release/opensource
git init
git add .
git commit -m "Initial open-source release"
git remote add origin https://github.com/YOUR_USER/TenderCrawler.git
git branch -M main
git push -u origin main
```

## 许可证

MIT License，见 `LICENSE`。如需更换许可证，请修改该文件及 README 中的说明。
