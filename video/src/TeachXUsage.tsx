import React from "react";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/* ── 主题色(与 TeachXDemo 一致) ── */
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
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

/* ── 通用小件 ── */

const FadeIn: React.FC<{
  delay?: number;
  y?: number;
  children: React.ReactNode;
}> = ({ delay = 0, y = 20, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div style={{ opacity: s, transform: `translateY(${(1 - s) * y}px)` }}>
      {children}
    </div>
  );
};

/** 打字机:在 from~to 帧之间把 text 逐字打出 */
const useTyped = (text: string, from: number, to: number) => {
  const frame = useCurrentFrame();
  const n = interpolate(frame, [from, to], [0, text.length], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return text.slice(0, Math.floor(n));
};

/** 底部屏幕字幕 */
const Caption: React.FC<{ text: string; delay?: number }> = ({
  text,
  delay = 15,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div
      style={{
        position: "absolute",
        bottom: 58,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity: s,
      }}
    >
      <div
        style={{
          background: "rgba(23,26,35,.94)",
          border: `1px solid ${C.line}`,
          color: C.text,
          fontSize: 30,
          padding: "12px 40px",
          borderRadius: 40,
        }}
      >
        {text}
      </div>
    </div>
  );
};

/** 风格化浏览器窗口 mockup:红黄绿圆点 + 地址栏 + 内容区 */
const WindowFrame: React.FC<{
  url: string;
  delay?: number;
  children: React.ReactNode;
}> = ({ url, delay = 0, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div
      style={{
        opacity: s,
        transform: `translateY(${(1 - s) * 24}px) scale(${0.97 + s * 0.03})`,
        width: 1460,
        height: 850,
        margin: "0 auto",
        background: C.card,
        border: `1px solid ${C.line}`,
        borderRadius: 16,
        overflow: "hidden",
        boxShadow: "0 30px 80px rgba(0,0,0,.5)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          height: 48,
          background: C.card2,
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "0 20px",
          borderBottom: `1px solid ${C.line}`,
        }}
      >
        {["#ff5f57", "#febc2e", "#28c840"].map((dot) => (
          <div
            key={dot}
            style={{ width: 14, height: 14, borderRadius: 7, background: dot }}
          />
        ))}
        <div
          style={{
            margin: "0 auto",
            background: C.bg,
            borderRadius: 8,
            color: C.muted,
            fontSize: 18,
            fontFamily: MONO,
            padding: "5px 60px",
          }}
        >
          {url}
        </div>
        <div style={{ width: 62 }} />
      </div>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>{children}</div>
    </div>
  );
};

/** 输入框(带打字动画) */
const Field: React.FC<{
  label: string;
  text: string;
  from: number;
  to: number;
  password?: boolean;
}> = ({ label, text, from, to, password }) => {
  const typed = useTyped(text, from, to);
  return (
    <div>
      <div style={{ color: C.muted, fontSize: 20, marginBottom: 8 }}>{label}</div>
      <div
        style={{
          background: C.bg,
          border: `1px solid ${C.line}`,
          borderRadius: 10,
          padding: "12px 18px",
          color: C.text,
          fontSize: 26,
          fontFamily: password ? MONO : FONT,
          minHeight: 34,
        }}
      >
        {password ? "•".repeat(typed.length) : typed}
      </div>
    </div>
  );
};

const Btn: React.FC<{
  label: string;
  delay: number;
  color?: string;
  small?: boolean;
}> = ({ label, delay, color = C.purple, small }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 15 } });
  const pulse = interpolate(frame, [delay + 10, delay + 26], [1, 1.06], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        display: "inline-block",
        opacity: s,
        transform: `scale(${Math.min(s, pulse)})`,
        background: color,
        color: "#fff",
        borderRadius: 10,
        fontSize: small ? 20 : 24,
        fontWeight: 600,
        padding: small ? "8px 22px" : "12px 34px",
      }}
    >
      {label}
    </div>
  );
};

/** 侧栏(聊天/练习页共用) */
const Sidebar: React.FC<{ highlight?: string; badge?: string; badgeDelay?: number }> = ({
  highlight,
  badge,
  badgeDelay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - badgeDelay, fps, config: { damping: 12 } });
  const items = ["💬 会话", "📖 学习记录", "✏️ 练习复习", "🎯 学习目标"];
  return (
    <div
      style={{
        width: 250,
        background: C.card2,
        borderRight: `1px solid ${C.line}`,
        padding: "26px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
    >
      {items.map((item) => (
        <div
          key={item}
          style={{
            color: item === highlight ? C.text : C.muted,
            background: item === highlight ? "rgba(124,92,255,.16)" : "transparent",
            borderRadius: 8,
            padding: "9px 14px",
            fontSize: 22,
          }}
        >
          {item}
          {item === "📖 学习记录" && badge ? (
            <span
              style={{
                marginLeft: 10,
                background: C.red,
                color: "#fff",
                borderRadius: 12,
                fontSize: 16,
                padding: "2px 9px",
                display: "inline-block",
                transform: `scale(${s})`,
              }}
            >
              {badge}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
};

const UserBubble: React.FC<{ text: string; from: number }> = ({ text, from }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - from, fps, config: { damping: 200 } });
  const typed = useTyped(text, from, from + Math.max(12, text.length * 1.2));
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", opacity: s }}>
      <div
        style={{
          background: C.purple,
          color: "#fff",
          borderRadius: "16px 16px 4px 16px",
          padding: "14px 24px",
          fontSize: 26,
          maxWidth: 640,
        }}
      >
        {typed}
      </div>
    </div>
  );
};

const AssistantBubble: React.FC<{ text: string; from: number; to: number }> = ({
  text,
  from,
  to,
}) => {
  const frame = useCurrentFrame();
  const typed = useTyped(text, from, to);
  const done = frame >= to;
  return (
    <div style={{ display: "flex", gap: 16 }}>
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: 12,
          background: C.yellow,
          color: "#1d1d1d",
          fontWeight: 800,
          fontSize: 24,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        T
      </div>
      <div
        style={{
          background: C.card2,
          border: `1px solid ${C.line}`,
          borderRadius: "4px 16px 16px 16px",
          padding: "16px 24px",
          fontSize: 26,
          color: C.text,
          lineHeight: 1.6,
          maxWidth: 900,
        }}
      >
        {typed}
        {!done ? (
          <span
            style={{
              display: "inline-block",
              width: 12,
              height: 28,
              background: C.yellow,
              marginLeft: 6,
              verticalAlign: "middle",
              opacity: Math.floor(frame / 8) % 2 === 0 ? 1 : 0.15,
            }}
          />
        ) : null}
      </div>
    </div>
  );
};

const Card: React.FC<{
  children: React.ReactNode;
  from: number;
  color?: string;
}> = ({ children, from, color = C.line }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - from, fps, config: { damping: 16 } });
  return (
    <div
      style={{
        opacity: s,
        transform: `translateY(${(1 - s) * 16}px)`,
        background: C.card2,
        border: `1px solid ${color}`,
        borderRadius: 12,
        padding: "14px 22px",
      }}
    >
      {children}
    </div>
  );
};

/* ── 镜头 1:标题卡(150 帧) ── */
const TITLE = 150;
const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 18, TITLE - 14, TITLE], [0, 1, 1, 0]);
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
        <div style={{ fontSize: 88, fontWeight: 800, color: C.text }}>
          你的 AI 学习助手
        </div>
        <div style={{ fontSize: 34, color: C.muted, marginTop: 22 }}>
          从提问到掌握,<span style={{ color: C.green, fontWeight: 700 }}>一个闭环</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── 镜头 2:注册 + 首次引导(240 帧) ── */
const ONBOARD = 240;
const OnboardScene: React.FC = () => {
  const frame = useCurrentFrame();
  const onSignup = frame < 108;
  const steps = [
    { label: "学习阶段", value: "大一", at: 118 },
    { label: "学习目标", value: "掌握线性代数", at: 148 },
    { label: "讲解风格", value: "先例子后原理", at: 178 },
  ];
  return (
    <AbsoluteFill
      style={{ background: C.bg, fontFamily: FONT, padding: "70px 0 0" }}
    >
      <WindowFrame url={onSignup ? "teachx.local/register" : "teachx.local/onboarding"}>
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {onSignup ? (
            <div style={{ width: 460, display: "flex", flexDirection: "column", gap: 22 }}>
              <div style={{ fontSize: 38, fontWeight: 700, color: C.text, textAlign: "center" }}>
                创建账号
              </div>
              <Field label="用户名" text="xiaoming" from={25} to={60} />
              <Field label="密码" text="password123" from={62} to={95} password />
              <div style={{ textAlign: "center", marginTop: 6 }}>
                <Btn label="注册并登录" delay={98} />
              </div>
            </div>
          ) : (
            <div style={{ width: 560, display: "flex", flexDirection: "column", gap: 24 }}>
              <div style={{ fontSize: 34, fontWeight: 700, color: C.text }}>
                三步完成首次引导
              </div>
              {steps.map((step) => (
                <FadeIn key={step.label} delay={step.at} y={14}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 18,
                      background: C.card2,
                      border: `1px solid ${C.purple}55`,
                      borderRadius: 12,
                      padding: "16px 24px",
                    }}
                  >
                    <span style={{ color: C.muted, fontSize: 22, width: 120 }}>
                      {step.label}
                    </span>
                    <span style={{ color: C.text, fontSize: 26, fontWeight: 600 }}>
                      {step.value}
                    </span>
                  </div>
                </FadeIn>
              ))}
              <div style={{ textAlign: "center", marginTop: 8 }}>
                <Btn label="完成,进入学习 →" delay={212} color={C.green} />
              </div>
            </div>
          )}
        </div>
      </WindowFrame>
      <Caption text="1 分钟完成首次引导,告诉它你是谁" />
    </AbsoluteFill>
  );
};

/* ── 镜头 3:提问 → 流式回答 + 来源(360 帧) ── */
const CHAT = 360;
const ChatScene: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, padding: "70px 0 0" }}>
    <WindowFrame url="teachx.local/chat">
      <Sidebar highlight="💬 会话" />
      <div
        style={{
          flex: 1,
          padding: "34px 44px",
          display: "flex",
          flexDirection: "column",
          gap: 26,
        }}
      >
        <UserBubble text="什么是特征值?" from={12} />
        <AssistantBubble
          text="特征值是矩阵变换下「方向不变」的缩放倍数:若 Av = λv(v ≠ 0),则 λ 是 A 的特征值,v 是对应的特征向量。比如拉伸变换把向量拉长 2 倍,2 就是它的特征值。"
          from={60}
          to={250}
        />
        <Card from={262} color={`${C.green}66`}>
          <div style={{ color: C.muted, fontSize: 19, marginBottom: 6 }}>
            📎 回答依据
          </div>
          <div style={{ color: C.text, fontSize: 24 }}>
            特征值与特征向量.md · 片段 2
            <span style={{ color: C.green, fontSize: 20, marginLeft: 14 }}>
              来自你的知识库
            </span>
          </div>
        </Card>
      </div>
    </WindowFrame>
    <Caption text="基于你上传的资料回答,每个答案都有出处" />
  </AbsoluteFill>
);

/* ── 镜头 4:工具调用(240 帧) ── */
const TOOL = 240;
const ToolScene: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, padding: "70px 0 0" }}>
    <WindowFrame url="teachx.local/chat">
      <Sidebar highlight="💬 会话" />
      <div
        style={{
          flex: 1,
          padding: "34px 44px",
          display: "flex",
          flexDirection: "column",
          gap: 24,
        }}
      >
        <UserBubble text="帮我算 19 * 23" from={12} />
        <Card from={55} color={`${C.purple}66`}>
          <span style={{ color: C.purple, fontFamily: MONO, fontSize: 23 }}>
            tool_call
          </span>
          <span
            style={{
              color: C.text,
              fontFamily: MONO,
              fontSize: 23,
              marginLeft: 20,
            }}
          >
            calculator {"{ expression: 19 * 23 }"}
          </span>
        </Card>
        <Card from={105} color={`${C.green}66`}>
          <span style={{ color: C.green, fontFamily: MONO, fontSize: 23 }}>
            tool_result
          </span>
          <span
            style={{
              color: C.text,
              fontFamily: MONO,
              fontSize: 26,
              marginLeft: 20,
              fontWeight: 700,
            }}
          >
            437
          </span>
        </Card>
        <AssistantBubble text="19 × 23 = 437。还需要我帮你验算别的题目吗?" from={155} to={215} />
      </div>
    </WindowFrame>
    <Caption text="需要计算时,它会自己调用工具" />
  </AbsoluteFill>
);

/* ── 镜头 5:反馈与错题(210 帧) ── */
const FEEDBACK = 210;
const FeedbackScene: React.FC = () => {
  const frame = useCurrentFrame();
  const pickedUnclear = frame >= 58;
  const noteText = useTyped("我把特征值和特征向量搞混了", 88, 150);
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, padding: "70px 0 0" }}>
      <WindowFrame url="teachx.local/chat">
        <Sidebar highlight="📖 学习记录" badge="+1" badgeDelay={172} />
        <div
          style={{
            flex: 1,
            padding: "34px 44px",
            display: "flex",
            flexDirection: "column",
            gap: 26,
          }}
        >
          <AssistantBubble
            text="特征值和特征向量是成对出现的:特征向量指方向,特征值指这个方向被缩放的倍数。"
            from={0}
            to={1}
          />
          <div style={{ display: "flex", gap: 16 }}>
            {[
              { label: "👍 有帮助", key: "helpful" },
              { label: "🤔 不清楚", key: "unclear" },
              { label: "📝 记录我的误区", key: "mistake" },
            ].map((btn) => {
              const active = pickedUnclear && btn.key === "unclear";
              return (
                <div
                  key={btn.key}
                  style={{
                    border: `1px solid ${active ? C.yellow : C.line}`,
                    background: active ? "rgba(255,176,32,.14)" : C.card2,
                    color: active ? C.yellow : C.muted,
                    borderRadius: 10,
                    padding: "10px 24px",
                    fontSize: 23,
                  }}
                >
                  {btn.label}
                </div>
              );
            })}
          </div>
          <Card from={78}>
            <div style={{ color: C.muted, fontSize: 20, marginBottom: 8 }}>
              说说你的误区
            </div>
            <div style={{ color: C.text, fontSize: 25, minHeight: 36 }}>
              {noteText}
              {frame < 152 ? (
                <span
                  style={{
                    display: "inline-block",
                    width: 11,
                    height: 26,
                    background: C.yellow,
                    marginLeft: 5,
                    verticalAlign: "middle",
                    opacity: Math.floor(frame / 8) % 2 === 0 ? 1 : 0.15,
                  }}
                />
              ) : null}
            </div>
            <div style={{ marginTop: 16 }}>
              <Btn label="保存到错题本" delay={155} small color={C.red} />
            </div>
          </Card>
        </div>
      </WindowFrame>
      <Caption text="没听懂?记进错题本,之后弄懂它" />
    </AbsoluteFill>
  );
};

/* ── 镜头 6:练习与复习(240 帧) ── */
const PRACTICE = 240;
const PracticeScene: React.FC = () => {
  const frame = useCurrentFrame();
  const mastery = interpolate(frame, [172, 218], [8, 35], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const answerText = useTyped("特征向量方向不变,特征值是缩放倍数", 58, 112);
  const ratings = [
    { label: "Again", key: "again" },
    { label: "Hard", key: "hard" },
    { label: "Good", key: "good" },
    { label: "Easy", key: "easy" },
  ];
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, padding: "70px 0 0" }}>
      <WindowFrame url="teachx.local/practice">
        <Sidebar highlight="✏️ 练习复习" />
        <div
          style={{
            flex: 1,
            padding: "34px 44px",
            display: "flex",
            flexDirection: "column",
            gap: 24,
          }}
        >
          <Card from={10}>
            <div style={{ color: C.muted, fontSize: 20, marginBottom: 8 }}>
              练习题 · 来自「线性代数资料」
            </div>
            <div style={{ color: C.text, fontSize: 27, fontWeight: 600 }}>
              用自己的话说说:特征值和特征向量的关系是什么?
            </div>
          </Card>
          <div
            style={{
              background: C.bg,
              border: `1px solid ${C.line}`,
              borderRadius: 10,
              padding: "14px 20px",
              color: C.text,
              fontSize: 25,
              minHeight: 66,
            }}
          >
            {answerText}
            {frame < 114 ? (
              <span
                style={{
                  display: "inline-block",
                  width: 11,
                  height: 26,
                  background: C.yellow,
                  marginLeft: 5,
                  verticalAlign: "middle",
                  opacity: Math.floor(frame / 8) % 2 === 0 ? 1 : 0.15,
                }}
              />
            ) : null}
          </div>
          <div style={{ display: "flex", gap: 16 }}>
            {ratings.map((r) => {
              const active = frame >= 150 && r.key === "good";
              return (
                <div
                  key={r.key}
                  style={{
                    border: `1px solid ${active ? C.green : C.line}`,
                    background: active ? "rgba(62,207,142,.16)" : C.card2,
                    color: active ? C.green : C.muted,
                    borderRadius: 10,
                    padding: "10px 26px",
                    fontSize: 23,
                  }}
                >
                  {r.label}
                </div>
              );
            })}
          </div>
          <Card from={168} color={`${C.green}66`}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 18,
              }}
            >
              <span style={{ color: C.muted, fontSize: 21 }}>知识库掌握度</span>
              <div
                style={{
                  flex: 1,
                  height: 14,
                  background: C.bg,
                  borderRadius: 7,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${mastery}%`,
                    height: "100%",
                    background: `linear-gradient(90deg, ${C.purple}, ${C.green})`,
                  }}
                />
              </div>
              <span
                style={{
                  color: C.text,
                  fontFamily: MONO,
                  fontSize: 26,
                  fontWeight: 700,
                  width: 84,
                  textAlign: "right",
                }}
              >
                {Math.round(mastery)}%
              </span>
            </div>
            <FadeIn delay={222} y={10}>
              <div style={{ color: C.green, fontSize: 22, marginTop: 12 }}>
                🗓 已安排:4 天后复习这道题
              </div>
            </FadeIn>
          </Card>
        </div>
      </WindowFrame>
      <Caption text="从你的资料出题,按遗忘曲线安排复习" />
    </AbsoluteFill>
  );
};

/* ── 镜头 7:学习目标(150 帧) ── */
const GOAL = 150;
const GoalScene: React.FC = () => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [48, 108], [35, 60], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, padding: "70px 0 0" }}>
      <WindowFrame url="teachx.local/profile">
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              width: 900,
              background: C.card2,
              border: `1px solid ${C.line}`,
              borderRadius: 16,
              padding: "40px 48px",
            }}
          >
            <div style={{ color: C.muted, fontSize: 21, marginBottom: 10 }}>
              🎯 当前学习目标 · 进行中
            </div>
            <div style={{ color: C.text, fontSize: 32, fontWeight: 700 }}>
              掌握线性代数并通过期末考试
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 20,
                marginTop: 30,
              }}
            >
              <div
                style={{
                  flex: 1,
                  height: 18,
                  background: C.bg,
                  borderRadius: 9,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${progress}%`,
                    height: "100%",
                    background: `linear-gradient(90deg, ${C.yellow}, ${C.green})`,
                  }}
                />
              </div>
              <span
                style={{
                  color: C.green,
                  fontFamily: MONO,
                  fontSize: 32,
                  fontWeight: 800,
                  width: 100,
                  textAlign: "right",
                }}
              >
                {Math.round(progress)}%
              </span>
            </div>
          </div>
        </div>
      </WindowFrame>
      <Caption text="每一步都算数,目标看得见" />
    </AbsoluteFill>
  );
};

/* ── 镜头 8:学习闭环(210 帧) ── */
const LOOPN = 210;
const LoopScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const nodes = ["提问", "理解", "反馈", "练习", "掌握"];
  const cx = 960;
  const cy = 470;
  const r = 265;
  const draw = interpolate(frame, [95, 165], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{ background: C.bg, fontFamily: FONT, justifyContent: "center" }}
    >
      <FadeIn>
        <div style={{ textAlign: "center", fontSize: 44, fontWeight: 700, color: C.text }}>
          学习形成<b style={{ color: C.green }}>闭环</b>,而不是一次性的问答
        </div>
      </FadeIn>
      <div style={{ position: "relative", height: 800, marginTop: 10 }}>
        <svg
          width="1920"
          height="800"
          viewBox="0 0 1920 800"
          style={{ position: "absolute", inset: 0 }}
        >
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={C.line}
            strokeWidth={3}
          />
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={C.green}
            strokeWidth={5}
            pathLength={100}
            strokeDasharray={`${draw} 100`}
            strokeLinecap="round"
            transform={`rotate(-90 ${cx} ${cy})`}
          />
        </svg>
        {nodes.map((label, i) => {
          const angle = -90 + i * 72;
          const rad = (angle * Math.PI) / 180;
          const x = cx + r * Math.cos(rad);
          const y = cy + r * Math.sin(rad);
          return (
            <div
              key={label}
              style={{
                position: "absolute",
                left: x,
                top: y,
                transform: "translate(-50%, -50%)",
              }}
            >
              <Node label={label} delay={12 + i * 14} color={i === 4 ? C.green : C.purple} />
            </div>
          );
        })}
        <div
          style={{
            position: "absolute",
            left: cx,
            top: cy,
            transform: "translate(-50%, -50%)",
            textAlign: "center",
            opacity: spring({ frame: frame - 168, fps, config: { damping: 200 } }),
          }}
        >
          <div style={{ fontSize: 44, fontWeight: 800, color: C.text }}>TeachX</div>
          <div style={{ fontSize: 20, color: C.muted }}>学习闭环</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Node: React.FC<{ label: string; delay: number; color: string }> = ({
  label,
  delay,
  color,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 13 } });
  return (
    <div
      style={{
        opacity: s,
        transform: `scale(${0.6 + s * 0.4})`,
        background: C.card,
        border: `2px solid ${color}`,
        borderRadius: 40,
        color: C.text,
        fontSize: 28,
        fontWeight: 700,
        padding: "14px 38px",
        boxShadow: `0 0 22px ${color}33`,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </div>
  );
};

/* ── 镜头 9:结尾(150 帧) ── */
const END = 150;
const EndScene: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 18, END - 14, END], [0, 1, 1, 0]);
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
        <div style={{ fontSize: 76, fontWeight: 800, color: C.text }}>TeachX</div>
        <div style={{ fontSize: 28, color: C.muted, marginTop: 18 }}>
          github.com/Baicaicn23/TeachX
        </div>
        <div style={{ marginTop: 34 }}>
          <span
            style={{
              background: C.purple,
              color: "#fff",
              fontSize: 28,
              fontWeight: 700,
              borderRadius: 12,
              padding: "14px 46px",
              display: "inline-block",
            }}
          >
            现在就试试 →
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── 组装:65 秒 = 1950 帧 ── */
export const TeachXUsage: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <Sequence from={0} durationInFrames={TITLE}>
        <TitleScene />
      </Sequence>
      <Sequence from={TITLE} durationInFrames={ONBOARD}>
        <OnboardScene />
      </Sequence>
      <Sequence from={TITLE + ONBOARD} durationInFrames={CHAT}>
        <ChatScene />
      </Sequence>
      <Sequence from={TITLE + ONBOARD + CHAT} durationInFrames={TOOL}>
        <ToolScene />
      </Sequence>
      <Sequence from={TITLE + ONBOARD + CHAT + TOOL} durationInFrames={FEEDBACK}>
        <FeedbackScene />
      </Sequence>
      <Sequence
        from={TITLE + ONBOARD + CHAT + TOOL + FEEDBACK}
        durationInFrames={PRACTICE}
      >
        <PracticeScene />
      </Sequence>
      <Sequence
        from={TITLE + ONBOARD + CHAT + TOOL + FEEDBACK + PRACTICE}
        durationInFrames={GOAL}
      >
        <GoalScene />
      </Sequence>
      <Sequence
        from={TITLE + ONBOARD + CHAT + TOOL + FEEDBACK + PRACTICE + GOAL}
        durationInFrames={LOOPN}
      >
        <LoopScene />
      </Sequence>
      <Sequence
        from={
          TITLE + ONBOARD + CHAT + TOOL + FEEDBACK + PRACTICE + GOAL + LOOPN
        }
        durationInFrames={END}
      >
        <EndScene />
      </Sequence>
    </AbsoluteFill>
  );
};
