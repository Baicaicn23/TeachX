import React from "react";
import {
  AbsoluteFill,
  interpolate,
  OffthreadVideo,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/* ── 主题色 ── */
const C = {
  bg: "#0f1117",
  card: "#171a23",
  line: "#262b3d",
  text: "#e8eaf2",
  muted: "#8b90a5",
  purple: "#7c5cff",
  yellow: "#ffb020",
  green: "#3ecf8e",
};

const FONT = '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif';

/* ── 真实录屏片段 + 底部字幕 ── */
const RealTake: React.FC<{
  src: string;
  playbackRate?: number;
  caption: string;
  captionDelay?: number;
}> = ({ src, playbackRate = 1.5, caption, captionDelay = 20 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - captionDelay, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: "#000", fontFamily: FONT }}>
      <OffthreadVideo
        src={staticFile(src)}
        playbackRate={playbackRate}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
      <div
        style={{
          position: "absolute",
          bottom: 54,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          opacity: s,
        }}
      >
        <div
          style={{
            background: "rgba(15,17,23,.92)",
            border: `1px solid ${C.line}`,
            color: C.text,
            fontSize: 30,
            padding: "12px 40px",
            borderRadius: 40,
            boxShadow: "0 8px 30px rgba(0,0,0,.5)",
          }}
        >
          {caption}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── 标题/结尾卡 ── */
const TitleCard: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 18, duration - 14, duration], [0, 1, 1, 0]);
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, #171a23 0%, ${C.bg} 70%)`,
        justifyContent: "center",
        alignItems: "center",
        fontFamily: FONT,
      }}
    >
      <div style={{ opacity, textAlign: "center" }}>
        <div style={{ fontSize: 88, fontWeight: 800, color: C.text }}>TeachX</div>
        <div style={{ fontSize: 36, color: C.muted, marginTop: 18 }}>
          真实使用演示 ·{" "}
          <span style={{ color: C.purple, fontWeight: 700 }}>从注册到学习闭环</span>
        </div>
        <div style={{ fontSize: 24, color: C.muted, opacity: 0.7, marginTop: 14 }}>
          以下全部为真实运行界面
        </div>
      </div>
    </AbsoluteFill>
  );
};

const EndCard: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 18, duration - 14, duration], [0, 1, 1, 0]);
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, #171a23 0%, ${C.bg} 70%)`,
        justifyContent: "center",
        alignItems: "center",
        fontFamily: FONT,
      }}
    >
      <div style={{ opacity, textAlign: "center" }}>
        <div style={{ fontSize: 72, fontWeight: 800, color: C.text }}>TeachX</div>
        <div style={{ fontSize: 28, color: C.muted, marginTop: 16, lineHeight: 1.8 }}>
          流式问答 · 工具调用 · 错题本 · 练习复习 · 学习目标 · 多模型接入
          <br />
          github.com/Baicaicn23/TeachX
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── 剪辑表:素材、倍速、字幕 ── */
const TAKES: Array<{
  file: string;
  rate: number;
  caption: string;
  sourceSeconds: number;
}> = [
  { file: "take1-login.webm", rate: 1.5, caption: "登录账号,一切从这里开始", sourceSeconds: 6.357 },
  { file: "take2-onboarding.webm", rate: 1.5, caption: "一分钟引导:学习阶段、目标、讲解风格", sourceSeconds: 8.779 },
  { file: "take3-chat-sources.webm", rate: 1.25, caption: "提问后流式回答,基于你的资料并附来源引用", sourceSeconds: 11.843 },
  { file: "take4-calculator.webm", rate: 1.5, caption: "需要计算?它自己会调用计算器工具", sourceSeconds: 11.544 },
  { file: "take5-feedback.webm", rate: 1.4, caption: "标记不清楚、写下误区,自动进错题本", sourceSeconds: 5.975 },
  { file: "take6a-practice-generate.webm", rate: 1.4, caption: "从知识库一键生成回忆练习", sourceSeconds: 4.738 },
  { file: "take6b-practice-answer.webm", rate: 1.4, caption: "作答自评,掌握度和复习计划自动更新", sourceSeconds: 5.594 },
  { file: "take7-profile-goal.webm", rate: 1.4, caption: "调整学习目标进度,每一步都算数", sourceSeconds: 6.219 },
  { file: "take8-records-models.webm", rate: 1.5, caption: "错题记录可回看,还可接入自己的模型", sourceSeconds: 6.849 },
];

const TITLE = 120;
const END = 150;

const sceneFrames = TAKES.map((t) => Math.round((t.sourceSeconds / t.rate) * 30));
const TOTAL = TITLE + sceneFrames.reduce((a, b) => a + b, 0) + END;

/* ── 组装 ── */
export const TeachXReal: React.FC = () => {
  let cursor = TITLE;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Sequence from={0} durationInFrames={TITLE}>
        <TitleCard duration={TITLE} />
      </Sequence>
      {TAKES.map((take, i) => {
        const from = cursor;
        cursor += sceneFrames[i];
        return (
          <Sequence key={take.file} from={from} durationInFrames={sceneFrames[i]}>
            <RealTake
              src={`raw/${take.file}`}
              playbackRate={take.rate}
              caption={take.caption}
            />
          </Sequence>
        );
      })}
      <Sequence from={cursor} durationInFrames={END}>
        <EndCard duration={END} />
      </Sequence>
    </AbsoluteFill>
  );
};

/* 供 Root.tsx 注册使用 */
export const TEACHX_REAL_DURATION = TOTAL;
