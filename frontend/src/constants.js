/**
 * 运维笔记知识库 — 共享常量
 * 统一管理中英文文案、分类颜色、图标映射，避免组件间重复定义
 */

/** 分类 → 主题色（用于节点染色、标签指示、分隔线等） */
export const CAT_COLORS = {
  '容器与编排': '#f59e0b',
  'Web与中间件': '#10b981',
  '数据库与存储': '#8b5cf6',
  '监控与可观测性': '#ef4444',
  '网络通信': '#3b82f6',
  '安全防护': '#dc2626',
  'CI/CD与自动化': '#06b6d4',
  '编程与构建': '#ec4899',
  'Linux系统基础': '#22c55e',
  '其他': '#64748b',
  '参考资料(PDF)': '#6b7280',
}

/** 分类 → 光晕色（CAT_COLORS 的提亮版，用于节点光晕渐变和连线高亮着色） */
function _lighten(hex, amt = 0.2) {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.min(255, ((n >> 16) & 0xff) + Math.round(255 * amt))
  const g = Math.min(255, ((n >> 8) & 0xff) + Math.round(255 * amt))
  const b = Math.min(255, (n & 0xff) + Math.round(255 * amt))
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')
}
export const CAT_GLOW = Object.fromEntries(
  Object.entries(CAT_COLORS).map(([k, v]) => [k, _lighten(v, 0.2)])
)

/** 分类 → 图标 emoji（详情面板与分类标题用） */
export const CAT_ICONS = {
  '容器与编排': '🐳',
  'Web与中间件': '🌐',
  '数据库与存储': '🗄️',
  '监控与可观测性': '📊',
  '网络通信': '📡',
  '安全防护': '🔒',
  'CI/CD与自动化': '⚙️',
  '编程与构建': '🔨',
  'Linux系统基础': '🐧',
  '其他': '📦',
  '参考资料(PDF)': '📄',
}

/**
 * 分类 → 关键词映射（与后端 build_core.py 的 CATEGORY_RULES 保持一致）。
 * 用于"分类+标签联动"：一篇笔记的主分类(cat)是单值，但它的 tags 可能命中多个分类的关键词。
 * 筛选某分类时，tags 含该分类关键词的笔记也会出现，实现跨分类发现。
 */
export const CAT_KEYWORDS = {
  '容器与编排': ['docker', 'harbor', 'k8s', 'kubernetes', 'compose', 'registry', '镜像'],
  'Web与中间件': ['nginx', 'tomcat', 'nacos', '中间件', '代理', '负载', '注册中心', 'kafka', 'redis'],
  '数据库与存储': ['mysql', '主从', '备份恢复', 'lvm', '磁盘', '扩容', '存储', 'mount', 'nfs', 'raid', 'rsync', 'minio'],
  '监控与可观测性': ['prometheus', 'zabbix', 'elastic', 'grafana', 'loki', 'tempo', 'otel', '可观测', '链路追踪', '监控', 'logrotate', '日志'],
  '网络通信': ['tcp', '抓包', 'tcpdump', 'wireshark', 'bond', 'nmcli', 'chrony', 'vpn', 'netplan'],
  '安全防护': ['防火墙', 'iptables', 'ssh', 'fail2ban', 'clamav', '漏洞', 'tls', 'ssl', '证书', '自建ca', 'keycloak', '安全'],
  'CI/CD与自动化': ['shell', 'ansible', 'jenkins', 'gitlab', 'ci', '脚本'],
  '编程与构建': ['git', 'maven', 'vue', '编译', '构建', '正则', '文本处理', 'node', 'npm'],
  'Linux系统基础': ['鸟哥', 'rocky', 'linux', 'ubuntu', 'systemd', 'sudo', '启动引导', '文件误删', 'busybox', '踩坑', '学习日记', '学习笔记', 'zsh', '终端', '美化', 'yum源', '软件包', 'sysctl', '内核', '组件升级', 'trash', '回收站', 'mount', '挂载', 'truncate', 'logrotate'],
}

/**
 * 跨分类联动时排除的"通用后缀关键词"。
 * 这些词在 CATEGORY_RULES 里用于初始分类兜底（让"XX学习笔记"归入 Linux系统基础），
 * 但它们不是主题关键词——如果用于跨分类联动，会导致所有含"学习笔记"后缀的笔记
 * 都被关联到 Linux系统基础，过宽。联动时只看实质主题关键词。
 */
const CROSS_CAT_SKIP_KW = new Set(['学习笔记', '学习日记'])

/**
 * 判断一篇笔记是否属于某分类（分类+标签联动）。
 * 主分类匹配，或笔记的 nameTags（仅文件名派生的标签）与该分类关键词有交集，即视为属于。
 * 注意：用 nameTags 而非 tags——tags 包含章节标题派生的标签（沾边就算），
 * nameTags 只含文件名命中的关键词（主题相关才算），避免"提到过"被误判为"属于"。
 * 联动时排除通用后缀关键词（学习笔记/学习日记），避免"XX学习笔记"全被关联到 Linux系统基础。
 * @param {Object} note - 笔记对象，含 cat 和 nameTags 字段
 * @param {string} cat - 分类名
 * @returns {boolean}
 */
export function noteMatchesCat(note, cat) {
  if (!note || !cat) return false
  if (note.cat === cat) return true
  const kws = CAT_KEYWORDS[cat]
  if (!kws) return false
  const nameTags = note.nameTags || []
  return kws.some(k => !CROSS_CAT_SKIP_KW.has(k) && nameTags.includes(k))
}

/**
 * 元文档关键词集 —— 这类笔记在正文/表格里罗列了大量其他笔记文件名，
 * 后端纯文本匹配会把它们全当成 wikilinks，在图谱里形成不合理的超级枢纽。
 * 在图谱/依赖图中清除它们的出向与入向关联，保持为独立节点（仍可被搜索/点击）。
 * /graph 与 /learning 共用此清单，避免两页拓扑表现不一致。
 */
export const META_DOC_KEYWORDS = ['可用性审计报告', '马哥高级参考索引']

/**
 * 判断一篇笔记是否属于元文档（按文件名包含关键词匹配）。
 * @param {Object} note - 笔记对象，含 name 字段
 * @returns {boolean}
 */
export function isMetaDoc(note) {
  if (!note) return false
  const name = note.name || ''
  return META_DOC_KEYWORDS.some(kw => name.includes(kw))
}
