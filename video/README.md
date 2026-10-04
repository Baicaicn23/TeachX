# TeachX 演示视频(Remotion)

用 React 代码驱动动画渲染的三支演示片,与主项目完全独立,不影响前端构建:

| 合成 | 时长 | 内容 | 输出 |
| --- | --- | --- | --- |
| `TeachXDemo` | 37 秒 | 面向技术观众:Agent Loop 架构 → 可靠性事件流 → 评测数字 | `out/teachx-demo.mp4` |
| `TeachXUsage` | 65 秒 | 面向普通用户:注册引导 → 流式问答与来源 → 工具计算 → 错题 → 练习复习 → 目标 → 学习闭环 | `out/teachx-usage.mp4` |
| `TeachXReal` | 57 秒 | **真实运行界面实录**:登录 → 引导 → 流式问答与来源 → 计算器 → 错题 → 练习 → 目标 → 记录与模型页,九段屏幕录制 + 字幕 + 1.25~1.5 倍速 | `out/teachx-real-demo.mp4` |

`TeachXReal` 的素材是 `public/raw/` 下的九段真实操作 WebM 录屏(浏览器自动化
驱动真实前后端录制,`showCursor` 带虚拟光标);改完成片重渲即可,无需重录。
`TeachXUsage` 用"风格化浏览器窗口 mockup"模拟界面(红黄绿圆点窗口框 + 简化页面),
打字机效果模拟流式回答,九个镜头带底部字幕,完整脚本见
[使用流程视频提示词.md](使用流程视频提示词.md)。

## 渲染成 MP4

```bash
cd video
npm install                                  # 首次
npm run render                               # TeachXDemo → out/teachx-demo.mp4
npx remotion render src/index.ts TeachXUsage out/teachx-usage.mp4 \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
npx remotion render src/index.ts TeachXReal out/teachx-real-demo.mp4 \
  --browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

渲染脚本已指向本机 Chrome(`--browser-executable`),不需要下载无头 Chromium。
在其他机器上把该路径改成对应 Chrome 位置即可。

## 预览调整

```bash
npm run studio                    # 打开 Remotion Studio,逐帧预览、热更新
```

改动画直接编辑 `src/TeachXDemo.tsx` 或 `src/TeachXUsage.tsx`:每个场景是一个
React 组件,时间轴在各 Scene 的帧数常量(30 帧 = 1 秒),总时长在
`Root.tsx` 的 `durationInFrames`。

## 设计约定

- 深色主题与项目进度地图一致(`C` 常量)
- 不引外部字体/图片,离线可渲染
- 场景切换一律用 `<Sequence>`(它会把子组件的 `useCurrentFrame()` 切到幕内
  本地帧——自写帧门控拿到的会是全局帧,动画会全部"停在结束状态",这是踩过的坑)
- 场景内动画只用 `useCurrentFrame` + `interpolate` + `spring`,不引额外动画库
