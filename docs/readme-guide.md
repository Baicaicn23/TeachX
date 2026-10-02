# README maintenance guide

> 本文件只负责 `README.md` 的结构和维护。通用文档规范、面向基础读者的写作规则
> 和交付检查表，请先阅读 [`documentation-guide.md`](documentation-guide.md)。

This guide records the README standard used by TeachX. It is based on a
structural review of three high-signal open-source projects:

- [Dify](https://github.com/langgenius/dify): product platform README
- [Open WebUI](https://github.com/open-webui/open-webui): web application README
- [Generative AI for Beginners](https://github.com/microsoft/generative-ai-for-beginners): educational project README

We borrow structure and communication principles, not wording.

## What high-scoring READMEs do well

### Dify: product value first

Dify opens with a visual identity, one clear positioning statement, immediate
links to the product, and a short path to self-hosting. It then explains key
capabilities in user-facing terms and separates advanced setup, contribution,
community, security, and license concerns.

**Lesson:** A visitor should understand what the product is before seeing its
implementation details.

### Open WebUI: show, then install

Open WebUI pairs the value proposition with a visible product demo, a concise
feature inventory, and several clearly separated installation paths. It also
anticipates common connection problems and provides troubleshooting directly in
the README.

**Lesson:** Show evidence that the product works, then remove friction from the
first successful run.

### Generative AI for Beginners: define the audience

The Microsoft course explains its intended audience, learning outcome, lesson
structure, required environment, and lesson catalog. The README works as a
course map rather than a feature list.

**Lesson:** For educational content, tell readers what they will be able to do,
not only what files the repository contains.

## The TeachX README standard

Keep the first screen focused on five things:

1. Project name and visual identity.
2. One sentence explaining what the project is.
3. A small number of truthful status or technology badges.
4. The current milestone in plain language.
5. A path to a demo, screenshot, or quick start.

The preferred section order is:

```text
Hero
Short positioning statement
Current status
Why TeachX
Architecture
Quick start
Real model configuration
What works today
Project structure
Quality checks
Roadmap
Upstream relationship
License
```

## Writing rules

- Lead with user outcomes, not class names.
- Prefer "streams turns and calls tools" over "implements `AgentRuntime`".
- Every feature claim must be runnable or explicitly marked as planned.
- Keep status language honest. Do not present planned work as complete.
- Put advanced configuration in `docs/` after the README is already useful.
- Use screenshots or diagrams when they reduce explanation time.
- Keep badges limited to meaningful signals such as status, version, CI, and
  license.
- Avoid marketing claims that cannot be demonstrated.
- Never include API keys, private URLs, or local machine paths.
- Link to deeper documentation instead of turning the README into a manual.
- Preserve attribution and license information.

## Update policy

README changes are required after a **large completed milestone**, specifically
when one of these changes lands:

- A new user-visible product capability.
- A new model provider, database, or deployment model.
- A change to installation or startup commands.
- A public API or architecture change that affects contributors.
- A release, demo, or portfolio-ready milestone.

README changes are not required for:

- Small bug fixes.
- Internal refactors.
- Test-only changes.
- Copy, spacing, or comment changes.
- Dependency patch upgrades that do not affect setup or capabilities.

## Completion checklist

Before updating the README after a milestone:

- [ ] The milestone is runnable and demonstrable.
- [ ] Relevant tests and builds pass.
- [ ] Current status and roadmap agree with the code.
- [ ] Quick-start commands were checked.
- [ ] New capabilities are described as user outcomes.
- [ ] Screenshots or diagrams are updated when presentation changed.
- [ ] No secrets or machine-specific paths are present.
- [ ] Upstream attribution and license remain accurate.## 语言规则

- 主 `README.md` 使用中文。
- Python 包名、API、命令、协议字段和技术专有名词保留英文。
- 不为追求形式而翻译代码相关名称，避免降低可搜索性和可执行性。
- 如果未来需要英文版本，使用独立的 `README.en.md`，不要让同一文件承担两种语言。
