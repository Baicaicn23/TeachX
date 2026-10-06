import {
  BookOpenCheck,
  Brain,
  Cable,
  Database,
  House,
  Settings,
  type LucideIcon,
} from 'lucide-react'

import type { Capability } from '@/lib/capability-routes'

export interface NavEntry {
  href: string
  label: string
  icon: LucideIcon
  tooltipKey?: string
  defaultCollapsed?: boolean
  /** Model capability this feature needs; locked when the user lacks it. */
  requires?: Capability
}

/**
 * The workspace features, in the order they ship in.
 *
 * This is the *default* arrangement, not the rendered one — a learner can
 * reorder these and fold the ones they don't use into "More"
 * (``lib/sidebar-layout.ts``). Adding an entry here places it for everyone,
 * including people who have already arranged their sidebar: it arrives next to
 * the neighbour it follows below rather than at the bottom of their list.
 */
export const PRIMARY_NAV: NavEntry[] = [
  { href: '/chat', label: 'Home', icon: House, tooltipKey: 'Home tooltip', requires: 'llm' },
  {
    // 学生主线:学科知识库是"平时的沉淀罐",一等入口,紧挨主页。
    href: '/knowledge-bases',
    label: '知识库',
    icon: Database,
    tooltipKey: '按学科浏览你沉淀的题目与资料,支持上传、预览。',
    requires: 'llm',
  },
  {
    href: '/learning-records',
    label: 'Learning records',
    icon: BookOpenCheck,
    tooltipKey: 'Review tutor feedback and your saved misunderstandings.',
    requires: 'llm',
  },
  {
    href: '/practice',
    label: 'Practice',
    icon: Brain,
    tooltipKey: 'Turn your materials into recall practice and scheduled review.',
    requires: 'llm',
  },
  {
    href: '/model-connections',
    label: 'Model connections',
    icon: Cable,
    tooltipKey: 'Connect DeepSeek, OpenAI, or another OpenAI-compatible model platform.',
    requires: 'llm',
  },
]
// TeachX 边界说明:继承自上游前端的 /partners、/space、/kanban、/co-writer、
// /agents、/learning 六个入口不是本产品的功能,已从导航移除;路由仍保留,
// 仅供学习前端代码时对照。

export const SECONDARY_NAV: NavEntry[] = [{ href: '/settings', label: 'Settings', icon: Settings }]

export const DEFAULT_COLLAPSED_NAV = PRIMARY_NAV.filter(entry => entry.defaultCollapsed).map(
  entry => entry.href
)

export const PRIMARY_NAV_HREFS = PRIMARY_NAV.map(entry => entry.href)

export const NAV_BY_HREF = new Map(
  [...PRIMARY_NAV, ...SECONDARY_NAV].map(entry => [entry.href, entry])
)

export function isNavActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`)
}
