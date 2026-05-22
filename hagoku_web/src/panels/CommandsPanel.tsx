import { useState, type ReactNode } from "react";
import {
  Search,
  Sparkles,
  BarChart3,
  FileText,
  PlayCircle,
  ChevronDown,
  ChevronRight,
  Info,
  Zap,
  PenLine,
  RefreshCw,
  Anchor,
} from "lucide-react";
import { PanelHeader } from "../components/PanelHeader";

// ── 交互命令指引数据 ────────────────────────────────────────────
interface CmdGuide {
  id: string;
  stage: string;
  stageIcon: ReactNode;
  stageColor: string;
  title: string;
  sections: CmdSection[];
}

interface CmdSection {
  label: string;
  items: CmdItem[];
}

interface CmdItem {
  example: string;
  desc: string;
}

const COMMAND_GUIDES: CmdGuide[] = [
  {
    id: "scout",
    stage: "Scout · 字段理解",
    stageIcon: <Search size={15} />,
    stageColor: "text-app-accent",
    title: "阶段 1：字段识别与纠错",
    sections: [
      {
        label: "纠正字段角色（最常用）",
        items: [
          {
            example: "收入 = target",
            desc: "把「收入」设为目标变量（你要预测/分析的指标）",
          },
          {
            example: "日期 = feature",
            desc: "把「日期」设为特征（用于分组/趋势的列）",
          },
          {
            example: "店铺名 = identifier",
            desc: "把「店铺名」设为标识列（分组维度，不参与数值计算）",
          },
          {
            example: "customer_id = identifier",
            desc: "把 customer_id 标记为标识列，避免被误当特征分析",
          },
        ],
      },
      {
        label: "补充分析目的（触发 LLM 重新识别）",
        items: [
          {
            example: "我要分析每个店铺收入的增长趋势",
            desc: "说明完整分析意图：维度（店铺）+ 指标（收入）+ 目标（增长趋势）",
          },
          {
            example: "帮我分析各地区的销售额差异",
            desc: "明确告知你要比较的分组维度和关心的指标",
          },
          {
            example: "收入是核心指标，请确认它被标记为 target",
            desc: "直接要求 LLM 确认特定字段的处理方式",
          },
        ],
      },
      {
        label: "指定字段参与分析",
        items: [
          {
            example: "只用：店铺, 收入, 日期",
            desc: "明确限定要分析的字段范围，忽略其他列",
          },
          {
            example: "去掉 ID 列，其他全用",
            desc: "排除不需要的字段，其余全部参与分析",
          },
        ],
      },
    ],
  },
  {
    id: "cleaner",
    stage: "Cleaner · 清洗核对",
    stageIcon: <Sparkles size={15} />,
    stageColor: "text-app-success",
    title: "阶段 2：数据清洗确认",
    sections: [
      {
        label: "确认清洗操作",
        items: [
          {
            example: "确认继续",
            desc: "直接确认清洗结果，进入下一阶段",
          },
          {
            example: "确认继续，但请把异常值改成用中位数填充",
            desc: "先确认，同时补充新的清洗要求",
          },
        ],
      },
      {
        label: "质疑清洗策略",
        items: [
          {
            example: "不要把空值删掉，用均值填充",
            desc: "纠正 LLM 的清洗决策",
          },
          {
            example: "收入列不要 Winsorize，保留原始分布",
            desc: "指定某些列不参与特定清洗操作",
          },
        ],
      },
    ],
  },
  {
    id: "analyst",
    stage: "Analyst · 统计分析",
    stageIcon: <BarChart3 size={15} />,
    stageColor: "text-app-warning",
    title: "阶段 3：分析结果核对",
    sections: [
      {
        label: "确认结果",
        items: [
          {
            example: "确认继续，生成报告",
            desc: "分析结果无误，直接进入报告生成",
          },
        ],
      },
      {
        label: "补充分析需求",
        items: [
          {
            example: "再做一下收入与客流量的相关性分析",
            desc: "追加新的分析任务",
          },
          {
            example: "把店铺按收入分组，比较高收入和低收入的差异",
            desc: "要求对数据重新分组后分析",
          },
        ],
      },
    ],
  },
  {
    id: "reporter",
    stage: "Reporter · 报告生成",
    stageIcon: <FileText size={15} />,
    stageColor: "text-app-text-muted",
    title: "阶段 4：报告",
    sections: [
      {
        label: "闸门确认",
        items: [
          {
            example: "确认继续",
            desc: "点击「确认继续」按钮，进入下一阶段（清洗/分析/报告）",
          },
          {
            example: "还有补充",
            desc: "点击「还有补充」按钮，回到字段表继续调整",
          },
        ],
      },
    ],
  },
];

// ── 输入技巧速查 ────────────────────────────────────────────────
interface TipCard {
  icon: ReactNode;
  title: string;
  desc: string;
  examples: string[];
}

const QUICK_TIPS: TipCard[] = [
  {
    icon: <PenLine size={16} />,
    title: "用 = 号纠正字段",
    desc: "LLM 对等号赋值语法响应最稳定，优先使用此格式纠正字段角色。",
    examples: ["收入 = target", "日期 = feature", "店铺名 = identifier"],
  },
  {
    icon: <RefreshCw size={16} />,
    title: "补充分析目的",
    desc: "LLM 初始可能未识别你的完整意图。用自然语言补充分析目的，它会重新理解。",
    examples: [
      "分析每个店铺收入的增长趋势",
      "帮我做各省份销售额的对比",
    ],
  },
  {
    icon: <Anchor size={16} />,
    title: "限定分析范围",
    desc: "如果字段过多，直接指定你关心的列，避免 LLM 分析无关字段。",
    examples: ["只用：店铺, 收入, 日期", "去掉 customer_id 和备注"],
  },
  {
    icon: <Zap size={16} />,
    title: "质疑并追加",
    desc: "你可以在确认的同时追加新的要求，LLM 会一并处理。",
    examples: [
      "确认继续，但再追加一个各店铺收入排名的分析",
      "确认，但先把收入 < 0 的异常行删掉",
    ],
  },
];

// ── 组件 ────────────────────────────────────────────────────────
function ExpandableSection({
  label,
  items,
  defaultOpen = false,
}: {
  label: string;
  items: CmdItem[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-app-border last:border-b-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 px-3 py-2 text-left text-ui-xs font-medium
          text-app-text hover:bg-app-bg-tertiary transition-colors duration-150 cursor-pointer"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {label}
      </button>
      {open && (
        <div className="px-3 pb-2.5 space-y-1.5">
          {items.map((item, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-ui-xs"
            >
              <code className="shrink-0 mt-px px-1.5 py-0.5 rounded bg-app-bg-tertiary text-app-accent font-mono text-ui-xs leading-snug">
                {item.example}
              </code>
              <span className="text-app-text-muted leading-snug pt-0.5">
                {item.desc}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StageGuideCard({ guide }: { guide: CmdGuide }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-app-border rounded-lg overflow-hidden bg-app-bg-secondary">
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left
          hover:bg-app-bg-tertiary transition-colors duration-150 cursor-pointer"
      >
        <span className={guide.stageColor}>{guide.stageIcon}</span>
        <span className="text-ui-sm font-medium text-app-text flex-1">{guide.title}</span>
        {expanded ? <ChevronDown size={14} className="text-app-text-muted" /> : <ChevronRight size={14} className="text-app-text-muted" />}
      </button>

      {expanded && (
        <div className="border-t border-app-border">
          {guide.sections.map((sec, si) => (
            <ExpandableSection key={si} label={sec.label} items={sec.items} defaultOpen={si === 0} />
          ))}
        </div>
      )}
    </div>
  );
}

function QuickTipCard({ tip }: { tip: TipCard }) {
  return (
    <div className="border border-app-border rounded-lg p-3 bg-app-bg-secondary space-y-2">
      <div className="flex items-center gap-1.5">
        <span className="text-app-accent">{tip.icon}</span>
        <span className="text-ui-sm font-medium text-app-text">{tip.title}</span>
      </div>
      <p className="text-ui-xs text-app-text-muted leading-snug">{tip.desc}</p>
      <div className="space-y-1">
        {tip.examples.map((ex, i) => (
          <code
            key={i}
            className="block px-2 py-1 rounded bg-app-bg-tertiary text-app-accent font-mono text-ui-xs leading-snug"
          >
            {ex}
          </code>
        ))}
      </div>
    </div>
  );
}

// ── 主面板 ──────────────────────────────────────────────────────
export default function CommandsPanel() {
  return (
    <div className="h-full flex flex-col overflow-hidden">
      <PanelHeader title="命令指引">
        <span className="text-ui-xs font-normal tracking-normal normal-case text-app-text-muted">
          分析页面交互命令参考
        </span>
      </PanelHeader>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {/* 快速提示 */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Info size={14} className="text-app-accent" />
            <span className="text-ui-sm font-medium text-app-text">输入技巧速查</span>
          </div>
          <div className="grid grid-cols-1 gap-2">
            {QUICK_TIPS.map((tip, i) => (
              <QuickTipCard key={i} tip={tip} />
            ))}
          </div>
        </div>

        {/* 分阶段指引 */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <PlayCircle size={14} className="text-app-success" />
            <span className="text-ui-sm font-medium text-app-text">分阶段交互指引</span>
          </div>
          <div className="space-y-2">
            {COMMAND_GUIDES.map((guide) => (
              <StageGuideCard key={guide.id} guide={guide} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}