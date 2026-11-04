# 发布到 GitHub

本文是给仓库维护者的发布清单，普通用户看 [README](../README.md) 即可。

## 1. 上传源码

本目录已经初始化为 `main` 分支的 git 仓库，并完成了首次提交。只需要创建空的 GitHub 仓库，然后执行（把 `USERNAME` 换成你的 GitHub 用户名）：

```powershell
git remote add origin https://github.com/USERNAME/keytype.git
git push -u origin main
```

如果以后在一个还没有 git 历史的目录中重新开始，再使用：

```powershell
git init -b main
git add .
git commit -m "feat: KeyType 1.0.0"
```

仓库只需要提交源码、测试页、文档和构建脚本。`dist/` 与 `build/` 已在 `.gitignore` 中忽略，不要提交 exe 和 zip。

## 2. 创建 Release

### 方式 A：网页上传

1. 在本地执行 `.\build.cmd`，生成 `dist\KeyType-1.0.0-win64.zip`
2. 打开 GitHub 仓库 → **Releases** → **Draft a new release**
3. Tag 填 `v1.0.0`，标题填 `KeyType 1.0.0`
4. 把 `dist\KeyType-1.0.0-win64.zip` 拖入附件区域
5. 发布

### 方式 B：GitHub CLI

```powershell
gh release create v1.0.0 `
  "dist\KeyType-1.0.0-win64.zip" `
  --title "KeyType 1.0.0" `
  --notes "First release. See CHANGELOG.md."
```

## 3. 使用 Actions 构建

`.github/workflows/windows-build.yml` 会在以下时机运行：

- push 到 `main`
- pull request
- 手动触发（Actions → Windows build → Run workflow）
- push 形如 `v*` 的 tag

在 Actions 运行结果的 **Artifacts** 中下载 `KeyType-Windows`，里面就是打包好的 zip。

如果希望打 tag 时自动创建 Release，可以在 workflow 中追加一个使用
[`softprops/action-gh-release`](https://github.com/softprops/action-gh-release) 的发布 job，
并授予 `contents: write` 权限；当前默认只上传 Artifact，不自动发布。

## 4. 发布前检查

- [ ] `python -m py_compile app.py winapi.py` 通过
- [ ] `.\build.cmd` 成功，zip 中包含 `KeyType.exe`、`_internal` 和「以管理员身份启动.cmd」
- [ ] `git status` 没有 `dist/`、`build/`、日志或本地设置文件
- [ ] README 截图路径正确，Release 中的 zip 文件名与 README 一致
- [ ] 在普通权限和管理员权限下各测试一次
- [ ] 更新 `CHANGELOG.md`

## 5. 版本号

当前版本为 `1.0.0`，散落在：

- `version_info.txt`
- `build.ps1` 中的 zip 文件名 `KeyType-1.0.0-win64.zip`
- `README.md`
- `CHANGELOG.md`

升级版本时一起修改，避免 Release 文件名混乱。

## 6. 仓库设置建议

在 GitHub 仓库首页点 **About** 的齿轮，可以填写：

- Description：`Windows 键盘代打：用 SendInput 绕过网页禁止粘贴，支持全局热键、中文和 Emoji。`
- Website：可留空，或填 Release 页面
- Topics：`windows`、`sendinput`、`clipboard`、`automation`、`python`、`tkinter`、`paste-bypass`

如果有条件，建议在 Releases 里保留至少一个可运行的 zip，并在仓库简介里直接引导用户下载。
