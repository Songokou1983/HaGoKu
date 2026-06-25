import { useState, type ReactNode } from "react";
import {
  Target,
  Pencil,
  Filter,
  CheckCircle,
  Lightbulb,
  Search,
  Sparkles,
  BarChart3,
  FileText,
  ChevronDown,
  ChevronRight,
  Info,
  Keyboard,
  Terminal,
} from "lucide-react";
import { PanelHeader } from "../components/PanelHeader";

const STAGE_LABELS: Record<string, string> = {
  scout: "理解字段", cleaner: "评估清洗", analyst: "跑统计", reporter: "写报告",
};

// ── 类型定义 ──────────────────────────────────────────────────────
interface FastCommand {
  id: string;
  cmd: string;
  label: string;
  icon: ReactNode;
  color: string;
  description: string;
  usage: string;
  examples: string[];
  stage: string;
}

interface StageRefCommands {
  agent: string;
  stage: string;
  stageIcon: ReactNode;
  stageColor: string;
  commands: StageCmdItem[];
}

interface StageCmdItem {
  cmd: string;
  desc: string;
  examples: string[];
}

interface FAQItem {
  q: string;
  a: string;
}

// ── 命令卡 ────────────────────────────────────────────────────────
const FAST_COMMANDS: FastCommand[] = [
  {
    id: "goal",
    cmd: "/goal",
    label: "补充分析目的",
    icon: <Target size={16} />,
    color: "text-app-accent",
    description: "修正/补充分析目的。LLM 会重新理解目标并在后续阶段中整合新的分析目的。",
    usage: "/goal <自然语言描述的分析目的>",
    examples: [
      "/goal 我要分析每个店铺收入的增长趋势",
      "/goal 帮助我对比不同地区的客户转化率",
      "/goal 我想找出影响用户流失的关键因素",
    ],
    stage: "理解字段 / 全局",
  },
  {
    id: "rename",
    cmd: "/rename",
    label: "字段重命名",
    icon: <Pencil size={16} />,
    color: "text-app-warning",
    description: "一次性重命名多个字段。LLM 会在当前阶段立即更新字段表格。",
    usage: "/rename 旧名 → 新名 [, 旧名 → 新名 ...]",
    examples: [
      "/rename Period → 周次",
      "/rename inc1 → 店铺收入, inc2 → 店铺积分",
      "/rename bos1 → 店铺费用1, bos2 → 店铺费用2, bos3 → 店铺费用3",
    ],
    stage: "理解字段",
  },
  {
    id: "use",
    cmd: "/use",
    label: "指定分析字段",
    icon: <Filter size={16} />,
    color: "text-app-success",
    description: "限定参与分析的字段范围。LLM 会将未列出的字段标记为不参与分析。",
    usage: "/use 字段1, 字段2, 字段3, ...",
    examples: [
      "/use 店铺, 收入, 日期",
      "/use Period, inc1, bos1, bos2",
    ],
    stage: "理解字段",
  },
  {
    id: "confirm",
    cmd: "/confirm",
    label: "确认通过",
    icon: <CheckCircle size={16} />,
    color: "text-app-text-muted",
    description:
      "放行当前暂停点，等效于「确认继续」按钮。适用于所有阶段的暂停点（闸门、字段表、清洗表、分析表）。",
    usage: "/confirm",
    examples: ["/confirm"],
    stage: "全阶段",
  },
  {
    id: "how",
    cmd: "/how",
    label: "查询如何做某事",
    icon: <Lightbulb size={16} />,
    color: "text-app-accent",
    description:
      "在任何阶段询问 LLM「如何操作」。LLM 会给出实操建议并告知对应的命令或输入格式。",
    usage: "/how <想做的事情>",
    examples: [
      "/how 怎么做 ab 测试分析",
      "/how 如何重新定义目标变量",
      "/how 怎么让分析只关注某几个字段",
    ],
    stage: "全阶段",
  },
];

// ── 分阶段命令指引 ────────────────────────────────────────────────
const STAGE_REF_COMMANDS: StageRefCommands[] = [
  {
    agent: "Scout",
    stage: "字段识别与对齐",
    stageIcon: <Search size={15} />,
    stageColor: "text-app-accent",
    commands: [
      {
        cmd: "/goal 分析目的说明",
        desc: "补充完整的分析意图（维度 + 指标 + 目标）。LLM 会据此重新识别字段角色，主动推断 target/feature。",
        examples: [
          "分析每个店铺收入的增长趋势",
          "对比各地区的客户转化率和客单价差异",
          "找出影响用户流失的关键因素（从用户属性和行为中推断）",
        ],
      },
      {
        cmd: "/rename 旧名 → 新名",
        desc: "给字段起中文名，LLM 会在字段表格中更新「中文名称」列，便于后续沟通。支持一次性重命名多个字段。",
        examples: [
          "Period → 周次",
          "inc1 → 店铺收入, inc2 → 店铺积分",
        ],
      },
      {
        cmd: "/use 字段列表",
        desc: "限定参与分析的字段。LLM 会将未列出的字段标记为 ignore，避免分析无关列。",
        examples: [
          "店铺, 收入, 日期",
          "Period, inc1, bos1, bos2, bos3",
        ],
      },
      {
        cmd: "/confirm",
        desc: "字段对齐完成，进入清洗阶段。",
        examples: [],
      },
      {
        cmd: "/how 如何操作",
        desc: "在字段阶段询问操作方式。例如询问如何重命名字段、如何指定目标变量等。",
        examples: [
          "怎么重新设定目标变量",
          "如何让 LLM 只分析某几列",
        ],
      },
    ],
  },
  {
    agent: "Cleaner",
    stage: "数据清洗确认",
    stageIcon: <Sparkles size={15} />,
    stageColor: "text-app-success",
    commands: [
      {
        cmd: "/confirm",
        desc: "确认清洗结果无误，进入分析阶段。",
        examples: [],
      },
      {
        cmd: "/how 如何调整",
        desc: "询问如何修改清洗策略、指定某列不参与清洗等。",
        examples: [
          "如何要求不要删掉空值行，改用均值填充",
          "怎么让收入列不做 Winsorize 处理",
        ],
      },
      {
        cmd: "/rename 旧名 → 新名",
        desc: "在清洗阶段发现名称问题可随时重命名字段。",
        examples: [],
      },
    ],
  },
  {
    agent: "Analyst",
    stage: "分析结果确认",
    stageIcon: <BarChart3 size={15} />,
    stageColor: "text-app-warning",
    commands: [
      {
        cmd: "/confirm",
        desc: "分析结果确认无误，进入报告生成阶段。",
        examples: [],
      },
      {
        cmd: "/goal 补充分析需求",
        desc: "追加新的分析方向。LLM 会基于新目的补充分析的统计检验。",
        examples: [
          "再做一下收入与客流量的相关性分析",
          "把店铺按收入高低分组做对比",
        ],
      },
      {
        cmd: "/how 如何操作",
        desc: "询问如何追加分析、如何要求特定统计检验。",
        examples: [
          "如何要求 LLM 做额外的假设检验",
          "怎么让分析按收入中位数分组",
        ],
      },
    ],
  },
  {
    agent: "Reporter",
    stage: "报告生成",
    stageIcon: <FileText size={15} />,
    stageColor: "text-app-text-muted",
    commands: [
      {
        cmd: "/confirm",
        desc: "闸门确认，进入下一阶段。",
        examples: [],
      },
    ],
  },
];

// ── FAQ ───────────────────────────────────────────────────────────
const FAQ_ITEMS: FAQItem[] = [
  {
    q: "命令会硬编码执行吗？",
    a: "不会。命令是给 LLM 的自然语言补充，不是代码指令。LLM 会理解命令内容并更新内部上下文，通过 function calling 机制自动执行对应操作。",
  },
  {
    q: "命令和直接说话有什么区别？",
    a: "效果相同。命令是快捷格式，帮你结构化地表达意图，提升与 LLM 的交互效率。直接用自然语言也能达到同样效果。",
  },
  {
    q: "一个消息能用多个命令吗？",
    a: "可以。一条消息内可以组合多个命令，LLM 会顺序处理。例如：/rename inc1 → 店铺收入 /goal 分析收入的增长趋势。",
  },
  {
    q: "命令在哪个阶段可用？",
    a: "/goal、/confirm、/how 全阶段可用。/rename 和 /use 主要在理解字段阶段使用，但 /rename 在其他阶段也可用。",
  },
  {
    q: "输入命令后，LLM 还会问我问题吗？",
    a: "会。命令输入后，LLM 可能还有需要确认的细节，会像处理普通对话一样继续追问。命令不会跳过 LLM 的确认环节。",
  },
];

// ── 子组件 ──────────────────────────────────────────────────────

function FastCommandCard({ cmd }: { cmd: FastCommand }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-app-border rounded-lg overflow-hidden bg-app-bg-secondary">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left
          hover:bg-app-bg-tertiary transition-colors duration-150 cursor-pointer"
      >
        <span className={cmd.color}>{cmd.icon}</span>
        <code className="text-ui-sm font-mono font-semibold text-app-accent">{cmd.cmd}</code>
        <span className="text-ui-sm font-medium text-app-text flex-1">{cmd.label}</span>
        <span className="text-ui-xs text-app-text-muted">{cmd.stage}</span>
        {expanded ? (
          <ChevronDown size={14} className="text-app-text-muted shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-app-text-muted shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-app-border px-3 py-2.5 space-y-2">
          <p className="text-ui-xs text-app-text-muted leading-snug">{cmd.description}</p>
          <div className="bg-app-bg-tertiary rounded px-2 py-1.5">
            <code className="text-ui-xs font-mono text-app-accent">{cmd.usage}</code>
          </div>
          <div className="space-y-1">
            {cmd.examples.map((ex, i) => (
              <code
                key={i}
                className="block px-2 py-1 rounded bg-app-bg-tertiary text-app-accent font-mono text-ui-xs leading-snug"
              >
                {ex}
              </code>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StageRefCard({ stage }: { stage: StageRefCommands }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-app-border rounded-lg overflow-hidden bg-app-bg-secondary">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left
          hover:bg-app-bg-tertiary transition-colors duration-150 cursor-pointer"
      >
        <span className={stage.stageColor}>{stage.stageIcon}</span>
        <span className="text-ui-sm font-medium text-app-text flex-1">
          {STAGE_LABELS[stage.agent.toLowerCase()] || stage.agent}
        </span>
        <span className="text-ui-xs text-app-text-muted">{stage.stage}</span>
        {expanded ? (
          <ChevronDown size={14} className="text-app-text-muted shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-app-text-muted shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-app-border space-y-3 p-3">
          {stage.commands.map((cmd, i) => (
            <div key={i}>
              <div className="flex items-center gap-1.5 mb-1">
                <code className="text-ui-xs font-mono font-semibold text-app-accent">
                  {cmd.cmd}
                </code>
              </div>
              <p className="text-ui-xs text-app-text-muted leading-snug">{cmd.desc}</p>
              {cmd.examples.length > 0 && (
                <div className="mt-1.5 space-y-1">
                  {cmd.examples.map((ex, j) => (
                    <code
                      key={j}
                      className="block px-2 py-1 rounded bg-app-bg-tertiary text-app-accent font-mono text-ui-xs leading-snug"
                    >
                      {ex}
                    </code>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FAQCard({ items }: { items: FAQItem[] }) {
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());

  const toggleItem = (idx: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  return (
    <div className="border border-app-border rounded-lg overflow-hidden bg-app-bg-secondary">
      {items.map((item, i) => (
        <div key={i} className="border-b border-app-border last:border-b-0">
          <button
            onClick={() => toggleItem(i)}
            className="w-full flex items-center gap-2 px-3 py-2 text-left
              hover:bg-app-bg-tertiary transition-colors duration-150 cursor-pointer"
          >
            <span className="text-ui-xs font-medium text-app-text flex-1">{item.q}</span>
            {expandedItems.has(i) ? (
              <ChevronDown size={14} className="text-app-text-muted shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-app-text-muted shrink-0" />
            )}
          </button>
          {expandedItems.has(i) && (
            <div className="px-3 pb-2.5">
              <p className="text-ui-xs text-app-text-muted leading-snug">{item.a}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── 主面板 ──────────────────────────────────────────────────────
export default function CommandsPanel() {
  return (
    <div className="h-full flex flex-col overflow-hidden">
      <PanelHeader title="命令速查表">
        <span className="text-ui-xs font-normal tracking-normal normal-case text-app-text-muted">
          快捷命令 + 分阶段交互指引
        </span>
      </PanelHeader>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">
        {/* 快速命令 */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Terminal size={14} className="text-app-accent" />
            <span className="text-ui-sm font-medium text-app-text">命令速查</span>
          </div>
          <div className="space-y-2">
            {FAST_COMMANDS.map((cmd) => (
              <FastCommandCard key={cmd.id} cmd={cmd} />
            ))}
          </div>
        </div>

        {/* 分阶段命令指引 */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Keyboard size={14} className="text-app-success" />
            <span className="text-ui-sm font-medium text-app-text">各关注点可用命令</span>
          </div>
          <div className="space-y-2">
            {STAGE_REF_COMMANDS.map((stage) => (
              <StageRefCard key={stage.agent} stage={stage} />
            ))}
          </div>
        </div>

        {/* FAQ */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Info size={14} className="text-app-accent" />
            <span className="text-ui-sm font-medium text-app-text">常见问题</span>
          </div>
          <FAQCard items={FAQ_ITEMS} />
        </div>
      </div>
    </div>
  );
}