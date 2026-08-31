# TerraMap 简体中文汉化版

> [!IMPORTANT]
> 本仓库是 TerraMap 的社区汉化分支，并非 TerraMap 官方仓库，也不由原项目作者维护。

TerraMap 是一款适用于 Terraria 1.4.5 的交互式世界地图查看器。它加载速度快，支持平移、缩放，并可查找方块、矿石、宝箱物品、地牢、NPC 等内容。

## 在线使用

简体中文 Vercel 镜像站：<https://tr.xn--p8rt33c.top/>

无需安装客户端，直接打开镜像站并选择 Terraria 世界文件即可使用。世界文件在浏览器本地处理，不会上传至服务器。

## 汉化说明

本分支在上游项目的简体中文界面翻译基础上，对游戏数据中的英文硬编码名称进行了进一步汉化，包括：

- 物品名称及物品前缀
- 方块名称及贴图变体描述
- 墙体名称
- NPC 名称
- 常用方块集合名称

本汉化为社区维护版本，部分新版本内容、内部占位名称及联动专有名词可能仍保留英文。如发现翻译错误或遗漏，欢迎在本仓库提交 Issue 或 Pull Request。

## 上游项目

- TerraMap 官方网页：<https://terramap.github.io>
- 跨平台原生客户端：<https://terramap.github.io/native.html>
- Windows 客户端（已弃用，不再受支持）：<https://terramap.github.io/windows.html>

## 赞助

## 原生客户端发布流程

以下为上游仓库的英文原文（本汉化分支的发布方式与上游一致）。

The native (Tauri-based) desktop app is built and released by [.github/workflows/native-release.yml](.github/workflows/native-release.yml).

### Bumping the version

- **`package.json`** (`version`) — source of truth for the web app. [vite.config.ts](vite.config.ts) imports it and bakes it into `__APP_VERSION__` at build time. Bump this manually before release.
- **`native/tauri.conf.json`** (`version`) — native app version. For tagged/manual-tag releases this is overwritten automatically from the `native-vX.Y.Z` tag (see below), so it doesn't strictly need bumping first — but keep it in sync so local native dev builds (`npm run native`) show the right version.

### Triggering a release

- **Tagged release**: push a tag matching `native-v*`, e.g.:
  ```
  git tag native-v0.2.0
  git push origin native-v0.2.0
  ```
  This builds, signs, and publishes a GitHub Release named `TerraMap Native App 0.2.0`.
- **Manual dry run**: run the workflow via `workflow_dispatch` in the Actions tab and leave the `tag` input blank. This builds all platform artifacts without setting a version or publishing a release, useful for verifying the build still works.
- **Manual release**: run `workflow_dispatch` with `tag` set to a `native-vX.Y.Z` value to produce a full signed release the same as pushing a tag.

### What the workflow does

1. **test** — runs `npm ci` and `npm test` (lint, typecheck, vitest) on Ubuntu; the build only proceeds if this passes.
2. **build** — runs in a matrix across `mac-arm64`, `mac-x64`, `linux-x64`, and `win-x64`:
   - Sets the version in `native/tauri.conf.json` from the tag (tagged/manual releases only).
   - Imports the Apple signing certificate and builds/notarizes the macOS app (`npx tauri build`).
   - On Linux, additionally builds a Flatpak bundle via `flatpak-builder`.
   - Renames bundle outputs to `TerraMap-{version}-{label}.{ext}` (`.dmg`, `.app.tar.gz`, `.AppImage`, `.deb`, `.rpm`, `.msi`, `-setup.exe`, `.flatpak`) and uploads them as build artifacts. Windows artifacts are uploaded unsigned at this stage.
3. **sign-windows** — submits the unsigned Windows build to [SignPath](https://signpath.io/) for code signing and uploads the signed result.
4. **release** — (tagged/manual-tag runs only) downloads all platform artifacts and publishes a GitHub Release with the install instructions and every bundle attached.

### Prerequisites for signed releases

The following repository secrets/variables must be configured for macOS notarization and Windows signing to succeed:
`APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`, `SIGNPATH_API_TOKEN`, and the SignPath `organization-id`/`project-slug`/`signing-policy-slug`/`artifact-configuration-slug` variables.

### Local development/build

- `npm run native` — run the native app in dev mode (`tauri dev`).
- `npm run native:build` — produce a local unsigned native build for your current platform (`tauri build`).

## Sponsors

<table>
    <tr>
        <td style="width:50px">
            <img src="signpath.png" width="50" height="50">
        </td>
        <td>
            Windows 免费代码签名由 <a href="https://signpath.io/">SignPath.io</a> 提供，证书由 <a href="https://www.signpath.com/solutions/for-open-source-community-foundation">SignPath Foundation</a> 提供。
        </td>
    </tr>
</table>

## 许可证

本项目沿用上游项目的 MIT 许可证，详情请参阅 [LICENSE](LICENSE)。
