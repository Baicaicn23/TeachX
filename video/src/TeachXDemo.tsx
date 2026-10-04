import React from "react";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/* ── 主题色(与项目进度地图一致) ── */
const C = {
  bg: "#0f1117",
  card: "#171a23",
  card2: "#1d2130",
  line: "#262b3d",
  text: "#e8eaf2",
  muted: "#8b90a5",
  purple: "#7c5cff",
  yellow: "#ffb020",
  green: "#3ecf8e",
  red: "#ff6b6b",
};

const FONT = '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif';

/* ── 通用小件 ── */

const FadeIn: React.FC<{
  delay?: number;
  y?: number;
  children: React.ReactNode;
}> = ({ delay = 0, y = 24, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div
      style={{
        opacity: progress,
        transform: `translateY(${(1 - progress) * y}px)`,
      }}
    >
      {children}
    </div>
  );
};

const Box: React.FC<{
  title: string;
  sub?: string;
  color?: string;
  delay?: number;
}> = ({ title, sub, color = C.purple, delay = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 14 } });
  return (
    <div
      style={{
        opacity: s,
        transform: `scale(${0.7 + s * 0.3})`,
        background: C.card,
        border: `2px solid ${color}`,
        borderRadius: 16,
        padding: "22px 30px",
        textAlign: "center",
        boxShadow: `0 0 24px ${color}33`,
        fontFamily: FONT,
      }}
    >
      <div style={{ color: C.text, fontSize: 30, fontWeight: 700 }}>{title}</div>
      {sub ? (
        <div style={{ color: C.muted, fontSize: 18, marginTop: 4 }}>{sub}</div>
      ) : null}
    </div>
  );
};

/* ── 第一幕:开场(0 ~ 3s) ── */
const INTRO = 90;
const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 20, INTRO - 15, INTRO], [0, 1, 1, 0]);
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
        <div
          style={{
            fontSize: 96,
            fontWeight: 800,
            color: C.text,
            letterSpacing: 2,
          }}
        >
          TeachX
        </div>
        <div style={{ fontSize: 36, color: C.muted, marginTop: 18 }}>
          把大模型做成
          <span style={{ color: C.purple, fontWeight: 700 }}>可靠</span>、
          <span style={{ color: C.green, fontWeight: 700 }}>可评测</span>
          的学习助手
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── 第二幕:Agent Loop(3 ~ 14s) ── */
const LOOP = 330;
const AgentLoop: React.FC = () => {
  const frame = useCurrentFrame();

  // 数据包沿管线流动:0→模型,120→工具,240→流回
  const packetA = interpolate(frame, [40, 100], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const packetB = interpolate(frame, [150, 205], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const packetC = interpolate(frame, [240, 300], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const loopGlow = interpolate(frame, [150, 190, 240], [0, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{ background: C.bg, fontFamily: FONT, padding: "90px 110px" }}
    >
      <FadeIn>
        <div style={{ fontSize: 44, fontWeight: 700, color: C.text }}>
          自研 Agent Loop
          <span style={{ color: C.muted, fontSize: 24, marginLeft: 20 }}>
            流式输出 · 多轮工具调用 · 每层可解释
          </span>
        </div>
      </FadeIn>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 26,
          marginTop: 90,
          justifyContent: "center",
        }}
      >
        <Box title="浏览器" sub="WebSocket 流式" color={C.purple} delay={5} />
        <Arrow active={packetC > 0 && packetC < 1} />
        <Box title="FastAPI" sub="回合事件流" color={C.purple} delay={15} />
        <Arrow active={false} />
        <Box title="AgentRuntime" sub="编排 · 幂等 · 超时" color={C.yellow} delay={25} />
        <Arrow active={packetA > 0 && packetA < 1} />
        <Box title="模型" sub="DeepSeek / OpenAI" color={C.green} delay={35} />
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          marginTop: 70,
          position: "relative",
        }}
      >
        <div style={{ opacity: loopGlow }}>
          <Box title="🛠 工具" sub="计算器 · 知识检索" color={C.green} delay={120} />
        </div>
        <div
          style={{
            position: "absolute",
            top: -52,
            color: C.yellow,
            fontSize: 24,
            fontWeight: 600,
            opacity: loopGlow,
          }}
        >
          ↻ 模型请求工具 → 执行 → 结果回填 → 继续推理
        </div>
      </div>

      {/* 数据包 */}
      {[
        { p: packetA, top: 218 },
        { p: packetB, top: 218 },
      ].map(({ p, top }, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: interpolate(p, [0, 1], [400, 1420]),
            top,
            width: 18,
            height: 18,
            borderRadius: 9,
            background: C.yellow,
            boxShadow: `0 0 16px ${C.yellow}`,
            opacity: p > 0 && p < 1 ? 1 : 0,
          }}
        />
      ))}
      <div
        style={{
          position: "absolute",
          left: interpolate(packetC, [0, 1], [1420, 400]),
          top: 218,
          width: 18,
          height: 18,
          borderRadius: 9,
          background: C.purple,
          boxShadow: `0 0 16px ${C.purple}`,
          opacity: packetC > 0 && packetC < 1 ? 1 : 0,
        }}
      />

      <FadeIn delay={285}>
        <div style={{ textAlign: "center", color: C.muted, fontSize: 26 }}>
          结果严格按模型调用顺序返回 —— <span style={{ color: C.green }}>永远不乱序</span>
        </div>
      </FadeIn>
    </AbsoluteFill>
  );
};

const Arrow: React.FC<{ active: boolean }> = ({ active }) => (
  <div
    style={{
      width: 70,
      height: 4,
      background: active ? C.yellow : C.line,
      borderRadius: 2,
      boxShadow: active ? `0 0 12px ${C.yellow}` : "none",
    }}
  />
);

/* ── 第三幕:可靠性事件流(14 ~ 24s) ── */
const EVENTS = 300;
const eventRows: Array<{
  tag: string;
  tagColor: string;
  text: string;
  badge?: string;
  badgeColor?: string;
}> = [
  {
    tag: "tool_call",
    tagColor: C.purple,
    text: 'calculator  {"expression": "7 * 9"}',
  },
  {
    tag: "tool_result",
    tagColor: C.green,
    text: "63  ·  尝试 2 次",
    badge: "临时错误 → 有限退避重试",
    badgeColor: C.yellow,
  },
  {
    tag: "tool_result",
    tagColor: C.green,
    text: "重复请求 → 重放第一次结果",
    badge: "幂等 · 副作用只执行一次",
    badgeColor: C.green,
  },
  {
    tag: "tool_call",
    tagColor: C.purple,
    text: 'send_email  {"api_key": "***"}',
    badge: "敏感参数自动脱敏",
    badgeColor: C.red,
  },
  {
    tag: "error",
    tagColor: C.red,
    text: "turn_timeout · retryable=true",
    badge: "超时诚实失败,可一键重试",
    badgeColor: C.red,
  },
];

const EventStream: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, padding: "90px 140px" }}>
      <FadeIn>
        <div style={{ fontSize: 44, fontWeight: 700, color: C.text }}>
          每次工具调用都<b style={{ color: C.yellow }}>可观察</b>
          <span style={{ color: C.muted, fontSize: 24, marginLeft: 20 }}>
            事件即 trace,持久化可回放
          </span>
        </div>
      </FadeIn>
      <div style={{ marginTop: 60, display: "flex", flexDirection: "column", gap: 26 }}>
        {eventRows.map((row, i) => (
          <FadeIn key={i} delay={40 + i * 42} y={18}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 20,
                background: C.card,
                border: `1px solid ${C.line}`,
                borderRadius: 12,
                padding: "18px 26px",
              }}
            >
              <span
                style={{
                  color: row.tagColor,
                  fontFamily: "monospace",
                  fontSize: 24,
                  fontWeight: 700,
                  width: 220,
                }}
              >
                {row.tag}
              </span>
              <span style={{ color: C.text, fontFamily: "monospace", fontSize: 26 }}>
                {row.text}
              </span>
              {row.badge ? (
                <span
                  style={{
                    marginLeft: "auto",
                    color: row.badgeColor,
                    border: `1px solid ${row.badgeColor}66`,
                    borderRadius: 20,
                    padding: "4px 16px",
                    fontSize: 20,
                    whiteSpace: "nowrap",
                  }}
                >
                  {row.badge}
                </span>
              ) : null}
            </div>
          </FadeIn>
        ))}
      </div>
    </AbsoluteFill>
  );
};

/* ── 第四幕:评测数字(24 ~ 31s) ── */
const METRICS = 210;
const Metric: React.FC<{
  value: string;
  label: string;
  color: string;
  delay: number;
}> = ({ value, label, color, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 12 } });
  return (
    <div
      style={{
        opacity: s,
        transform: `scale(${0.6 + s * 0.4})`,
        textAlign: "center",
        background: C.card,
        border: `2px solid ${color}`,
        borderRadius: 20,
        padding: "46px 56px",
      }}
    >
      <div style={{ fontSize: 84, fontWeight: 800, color, fontFamily: "monospace" }}>
        {value}
      </div>
      <div style={{ fontSize: 26, color: C.muted, marginTop: 8 }}>{label}</div>
    </div>
  );
};

const Metrics: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, padding: "90px 120px" }}>
    <FadeIn>
      <div style={{ fontSize: 44, fontWeight: 700, color: C.text }}>
        不靠感觉,靠<b style={{ color: C.green }}>可复现的分数</b>
        <span style={{ color: C.muted, fontSize: 24, marginLeft: 20 }}>
          一条命令,任何人跑出同样结果
        </span>
      </div>
    </FadeIn>
    <div
      style={{
        display: "flex",
        gap: 40,
        justifyContent: "center",
        marginTop: 80,
      }}
    >
      <Metric value="1.000" label="Hit@3 检索命中率" color={C.green} delay={30} />
      <Metric value="0.688" label="MRR 排序质量" color={C.yellow} delay={55} />
      <Metric value="91 passed" label="自动测试(全程 Mock)" color={C.purple} delay={80} />
    </div>
    <FadeIn delay={130}>
      <div style={{ textAlign: "center", marginTop: 70, color: C.muted, fontSize: 26 }}>
        uv run python -m teachx.evals.run_rag_eval
        <span style={{ marginLeft: 24, color: C.green }}>· 基线退化 → 自动拦截</span>
      </div>
    </FadeIn>
  </AbsoluteFill>
);

/* ── 第五幕:结尾(31 ~ 37s) ── */
const OUTRO = 180;
const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 20, OUTRO - 20, OUTRO], [0, 1, 1, 0]);
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
        <div style={{ fontSize: 64, fontWeight: 800, color: C.text }}>
          TeachX
        </div>
        <div style={{ fontSize: 28, color: C.muted, marginTop: 20, lineHeight: 1.8 }}>
          24 篇中文教程 · 每个功能配面试问答
          <br />
          github.com/Baicaicn23/TeachX
        </div>
        <div style={{ marginTop: 36, display: "flex", gap: 16, justifyContent: "center" }}>
          {["Python 3.12", "FastAPI", "Next.js 16", "SQLite FTS5", "WebSocket"].map(
            (tech) => (
              <span
                key={tech}
                style={{
                  color: C.text,
                  border: `1px solid ${C.line}`,
                  background: C.card,
                  borderRadius: 20,
                  padding: "6px 20px",
                  fontSize: 20,
                }}
              >
                {tech}
              </span>
            )
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── 组装:Sequence 会把子组件的 useCurrentFrame() 切换为幕内本地帧 ── */
export const TeachXDemo: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Sequence from={0} durationInFrames={INTRO}>
        <Intro />
      </Sequence>
      <Sequence from={INTRO} durationInFrames={LOOP}>
        <AgentLoop />
      </Sequence>
      <Sequence from={INTRO + LOOP} durationInFrames={EVENTS}>
        <EventStream />
      </Sequence>
      <Sequence from={INTRO + LOOP + EVENTS} durationInFrames={METRICS}>
        <Metrics />
      </Sequence>
      <Sequence from={INTRO + LOOP + EVENTS + METRICS} durationInFrames={OUTRO}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  );
};
