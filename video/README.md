# TeachX 演示视频(Remotion)

用 React 代码驱动动画渲染的 37 秒项目演示片,四幕:开场 → Agent Loop 架构 →
可靠性事件流 → 评测数字 → 结尾。与主项目完全独立,不影响前端构建。

## 渲染成 MP4

```bash
cd video
npm install                       # 首次
npm run render                    # 输出 out/teachx-demo.mp4(1920×1080, 30fps, 37 秒)
```

渲染脚本已指向本机 Chrome(`--browser-executable`),不需要下载无头 Chromium。
在其他机器上把该路径改成对应 Chrome 位置即可。

## 预览调整

```bash
npm run studio                    # 打开 Remotion Studio,逐帧预览、热更新
```

改动画直接编辑 `src/TeachXDemo.tsx`:每个场景是一个 React 组件,时间轴在
`Root.tsx` 的 `durationInFrames` 和 `TeachXDemo.tsx` 各 Scene 的帧数常量
(INTRO / LOOP / EVENTS / METRICS / OUTRO,30 帧 = 1 秒)。

## 设计约定

- 深色主题与项目进度地图一致(`C` 常量)
- 不引外部字体/图片,离线可渲染
- 场景内动画只用 `useCurrentFrame` + `interpolate` + `spring`,不引额外动画库
