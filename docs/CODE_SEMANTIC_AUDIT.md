# 代码语义理解审计报告

> **审计范围**：HaGoKu 代码库中所有"代码层代替 LLM 做语义理解"的模式
> **审计日期**：2026-05-25
> **原则**：代码应只做结构化通道（数据透传、格式转换、路由分发），语义理解全部交由 LLM 完成

---

## 修复原则：为什么代码不能代替 LLM 做语义理解

### 当前问题根源

用户反馈：**"字段理解，在分析目标时已录入分析每个店铺的收入增长趋势，结果字段理解出来的结果，参与分析的字段都是错的。而且错的离谱，我告诉他应该是哪个也毫无反应。我可以猜出 LLM 根本没有收到有效信息"**

这个问题的直接原因是：**用户对字段理解的纠正信息，从未抵达 LLM**。

具体链条：
1. 用户在 Refinement 阶段说"Inc1 不是收入，是销售额" → 进入 `RefinementParser.parse()`
2. `RefinementParser` 是一个**纯正则引擎**，它用 6 条硬编码正则（`ALLOWED_PATTERNS`）去匹配用户输入
3. 用户的措辞不匹配任何正则 → 被归入 `unknown` → 生成一条模板引导文案返回给用户
4. LLM **从未收到**用户的纠正信息
5. 所以 LLM 也不知道字段理解有误，后续分析自然用错字段

### 架构原则：MCP 设计准则

HaGoKu 是一个 **Agent 编排系统**，LLM 是唯一具备自然语言理解能力的组件。代码层的角色是：

| 层 | 允许做什么 | 禁止做什么 |
|----|-----------|-----------|
| **代码层** (Python) | 数据结构变换（dict → dataclass）<br>JSON Schema 定义与解析<br>数值范围校验（p ∈ [0,1]）<br>UI 状态路由（基于枚举值）<br>退出口令匹配（固定词汇）<br>数据透传与管道搭建 | 从用户自然语言中提取语义<br>用关键词/正则判断用户意图<br>判断 LLM 产出是否"有内容"<br>在 LLM 不可达时替换 LLM 的语义角色 |
| **LLM 层** | 理解用户意图<br>提取结构化参数<br>生成自然语言文案<br>判断置信度与是否需要确认<br>字段语义推断 | 做数值精度计算<br>执行确定性规则（如过滤非法值） |

### 为什么要修复

1. **完整性（Completeness）**：用户的所有自然语言输入必须经过 LLM。任何绕过 LLM 的正则/关键词匹配都是信息丢失点，直接导致"LLM 没收有效信息"。

2. **鲁棒性（Robustness）**：用户措辞千变万化。「只看一线城市」「筛一下付费的」「切到 ROI 看看」——正则永远覆盖不全。LLM 天然具备对自然语言变体的容忍度。

3. **可维护性（Maintainability）**：每次新增业务类型（新指标名、新维度名、新意图类型）如果都要改代码正则/关键词列表，维护成本线性增长。LLM 通过 system prompt 即可适配。

4. **一致性（Consistency）**：项目中已有正确的参考实现——`ScoutAgent._infer_all_semantics()` 全程通过 `submit_field_inference` 工具让 LLM 做字段语义判断。`RefinementParser` 和 CLI 确认逻辑应遵循同样模式。

5. **用户体验（UX）**：当用户说"好，但是 Inc1 应该是收入"时，代码如果先匹配到"好"就当作确认，后面的纠正信息就丢失了。只有 LLM 能正确解析这种混合意图（确认 + 纠正）。

### 修复目标

将所有"代码代替 LLM 做语义理解"的模式，改造为 **LLM function calling / tool use** 模式：
- 用户自然语言 → 直接传给 LLM
- LLM 调用结构化工具（如 `submit_refinement`、`submit_field_correction`）产出的 JSON
- 代码只解析 JSON、做路由分发、更新状态

---

## 目录

1. [🔴 高严重度](#1--高严重度)
   - [1.1 RefinementParser — 纯正则引擎做语义解析](#11-refinementparser--纯正则引擎做语义解析)
   - [1.2 CLI 字段确认 — 关键词匹配判断用户意图](#12-cli-字段确认--关键词匹配判断用户意图)
   - [1.3 Scout 字段确认消息 — LLM 失败后代码直接拼接文案](#13-scout-字段确认消息--llm-失败后代码直接拼接文案)
2. [🟡 中严重度](#2--中严重度)
   - [2.1 TYPE_ECHO_SUFFIXES — 代码判断 LLM 产出是否有业务含义](#21-type_echo_suffixes--代码判断-llm-产出是否有业务含义)
   - [2.2 _generate_phase_message 兜底分支 — 代码拼接用户消息](#22-_generate_phase_message-兜底分支--代码拼接用户消息)
   - [2.3 _describe_intent — 硬编码 intent_type 映射表](#23-_describe_intent--硬编码-intent_type-映射表)
3. [🟢 低严重度](#3--低严重度)
   - [3.1 guardrails/parsers.py — 统计量提取正则](#31-guardrailsparserspy--统计量提取正则)
   - [3.2 respond() action 路由 — 前端枚举按钮](#32-respond-action-路由--前端枚举按钮)
   - [3.3 ws_handler.py 文本透传通道](#33-ws_handlerpy-文本透传通道)
4. [✅ 已修复项](#4--已修复项)
5. [修复优先级矩阵](#5--修复优先级矩阵)

---

## 1. 🔴 高严重度

### 1.1 RefinementParser — 纯正则引擎做语义解析

**文件**：`hagoku/manager/refinement.py`（全文件 272 行）

**问题描述**：

`RefinementParser` 是整个 refinement（用户反馈/调整指令）处理的核心入口。它完全通过硬编码正则表达式来理解用户的自然语言，**LLM 从未接收这些用户输入**。

具体问题点：

#### 1.1.1 `ALLOWED_PATTERNS`（第 69-77 行）— 6 条正则白名单

```python
ALLOWED_PATTERNS: list[tuple[str, str]] = [
    ("filter", r"只看|只看|只看"),
    ("exclude", r"排除|去掉|不要|不含|不包括|除了"),
    ("switch_target", r"换成|改为|改用|换.*指标|改.*指标|换.*目标|换成.*的"),
    ("simplify", r"太长了|太啰嗦|简单点|简洁点|精简|简短|只要|只留|简洁"),
    ("more_detail", r"详细点|展开|多说点|更详细|更完整|展开说"),
    ("explain", r"为什么|怎么得出的|怎么知道的|依据是什么|解释一下|怎么算的"),
]
```

**风险**：
- 用户说"帮我筛选出付费用户"→ `filter` 正则只能匹配到"付费"但 `DIMENSION_KEYWORDS` 中"付费"也是维度关键词，但正则未必能正确提取 filter_value
- 用户说"能不能不看 A 渠道的"→ "不看"不在正则中，会归入 `unknown`
- 用户说"把指标从销售额切到利润率"→ "切到"不在 `switch_target` 正则中
- 新用户用词习惯（如"筛一下"、"换下指标"、"太冗长了"）完全无法匹配

#### 1.1.2 `DIMENSION_KEYWORDS` / `TARGET_KEYWORDS`（第 80-93 行）— 硬编码关键词列表

```python
DIMENSION_KEYWORDS = [
    "渠道", "地区", "产品", "城市", "省份", "性别", "年龄段",
    "用户", "客群", "来源", "平台", "设备",
    "付费", "免费", "新用户", "老用户",
    "PC", "App", "H5", "web", "小程序",
]

TARGET_KEYWORDS = [
    "ROI", "roas", "ROAS", "CTR", "ctr", "CVR", "cvr",
    "转化率", "点击率", "点击", "曝光",
    "销量", "销售额", "GMV", "gmv", "收入", "利润", "成本", "客单价",
    "留存率", "流失率", " churn", "激活率", "注册率",
    "活跃", "新增", "访问", "PV", "UV",
]
```

**风险**：
- 用户数据中有 "ROI" 列但代码中没有 `"roi"` 小写形式（只有 `"ROI"` 和 `"roas"`），用户输入 "切换到 roi 指标" 将无法匹配
- 用户说"只看一线城市"→ "一线城市"不在 `DIMENSION_KEYWORDS` 中，`_extract_filter_details` 完全失败
- 任何不在白名单中的维度或指标都无法被识别

#### 1.1.3 `BLOCKED_PATTERNS`（第 100-109 行）— 4 条正则黑名单

```python
BLOCKED_PATTERNS: list[tuple[str, str]] = [
    ("new_direction", r"分析.*趋势|看看.*变化|再看下.*|再看看|再跑.*|再算.*|再查.*|再加.*|补充.*|加上.*|算一下.*|分析下.*|跑下.*|再看一下"),
    ("regenerate", r"重新生成|再来一遍|重新跑|重新分析|从头开始|再来一次"),
    ("speculate", r"原因是什么|可能是因为|应该是.*导致|估计.*原因|猜测|推测|可能.*导致|大概是.*原因"),
    ("explore", r"还有什么|还有什么发现|还应该看什么|还应该分析什么|有没有.*遗漏|还有没有.*问题"),
]
```

**说明**：此处的拦截逻辑**属于设计决策**（防止用户在 Refine 阶段提出新分析），且正则覆盖面较广。但仍有漏网风险：用户说"我想另外跑一个 A/B 测试"不会被拦截，因为不匹配任何 `BLOCKED_PATTERNS`。

#### 1.1.4 `_extract_details` 方法（第 196-258 行）— 正则提取参数

```python
def _extract_filter_details(self, feedback: str, intent: RefinementIntent) -> None:
    for dim in DIMENSION_KEYWORDS:
        if dim in feedback:
            intent.filter_column = dim
            match = re.search(rf"{dim}[是为是]\s*(\S+)", feedback)
            ...
```

直接从正则 match group 中提取 filter_value，且正则 `r"{dim}[是为是]\s*(\S+)"` 只能匹配到空格前的第一个词，无法处理多词值。

#### 修复方案

**目标**：将 `RefinementParser.parse()` 改为 LLM function calling 模式，对标 `ScoutAgent._infer_all_semantics()` 的设计。

**步骤**：

1. **在 `hagoku/agents/types.py` 中新增 `RefinementIntent` 的 JSON Schema 定义**：

```python
def build_submit_refinement_schema() -> dict:
    """构建 submit_refinement 工具的 JSON Schema"""
    return {
        "type": "object",
        "properties": {
            "refine_type": {
                "type": "string",
                "enum": ["filter", "switch_target", "simplify", "more_detail", "explain",
                         "new_direction", "regenerate", "speculate", "explore", "exit", "unknown"],
                "description": "用户调整意图的类型"
            },
            "filter_column": {"type": "string", "description": "要筛选的维度名称"},
            "filter_value": {"type": "string", "description": "筛选值"},
            "filter_exclude": {"type": "boolean", "description": "是否排除"},
            "new_target": {"type": "string", "description": "要切换的目标指标名称"},
            "verbosity": {"type": "string", "enum": ["simpler", "more_detailed"]},
            "explain_target": {"type": "string", "description": "要解释的结论主题"},
            "guidance": {"type": "string", "description": "当 refine_type 为 blocked/unknown 时，给用户的引导建议"},
            "thinking": {"type": "string", "description": "LLM 对用户意图的判断依据"}
        },
        "required": ["refine_type"]
    }
```

2. **重写 `RefinementParser.parse()` 方法**：

```python
class RefinementParser:
    """解析用户的 refinement 指令（LLM 驱动，零硬编码正则）"""
    
    def parse(self, feedback: str, context: dict[str, Any] | None = None) -> RefinementIntent:
        if not feedback or not feedback.strip():
            return RefinementIntent(raw_input=feedback, confidence="high")
        
        f = feedback.strip()
        
        # 保留退出口令的快速路径（避免不必要的 LLM 调用）
        if self._is_exit(f):
            return RefinementIntent(raw_input=f, refine_type="exit", confidence="high")
        
        # 核心改动：全部走 LLM function calling
        try:
            return self._parse_via_llm(f, context)
        except Exception:
            # LLM 不可达时的兜底（保留现有 unknown 引导逻辑）
            return self._build_unknown_intent(f)
    
    def _parse_via_llm(self, feedback: str, context: dict[str, Any] | None) -> RefinementIntent:
        from hagoku.config import LLMConfig
        from hagoku.llm.client import create_raw_client
        
        config = LLMConfig()
        client = create_raw_client(config)
        
        schema = build_submit_refinement_schema()
        submit_tool = {
            "type": "function",
            "function": {
                "name": "submit_refinement",
                "description": "提交对用户调整指令的理解结果",
                "parameters": schema,
            }
        }
        
        # 构建上下文（已有分析的列名、指标名等，帮助 LLM 理解用户指的什么）
        ctx_text = ""
        if context:
            target = context.get("target", "")
            features = context.get("features", [])
            if target:
                ctx_text += f"当前目标变量: {target}\n"
            if features:
                ctx_text += f"可用特征变量: {', '.join(features)}\n"
        
        system_prompt = (
            "你是数据分析助手，负责理解用户在当前分析基础上的调整意图。\n"
            "用户可能在要求：筛选数据、切换指标、调整报告详略、解释结论、退出分析，\n"
            "也可能提出超出当前分析范围的新要求。\n\n"
            "你需要调用 submit_refinement 工具来提交你的理解。\n"
            "如果用户要求的是新分析方向（而非在当前分析上调整），"
            "refine_type 设为 'new_direction' 并提供 guidance。"
        )
        
        response = client.chat.completions.create(
            model=config.model_quick or config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{ctx_text}\n用户输入：{feedback}"},
            ],
            temperature=0.0,
            max_tokens=512,
            tools=[submit_tool],
            tool_choice={"type": "function", "function": {"name": "submit_refinement"}},
        )
        
        import json
        args = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        
        return RefinementIntent(
            raw_input=feedback,
            refine_type=args.get("refine_type", "unknown"),
            filter_column=args.get("filter_column"),
            filter_value=args.get("filter_value"),
            filter_exclude=bool(args.get("filter_exclude", False)),
            new_target=args.get("new_target"),
            verbosity=args.get("verbosity"),
            explain_target=args.get("explain_target"),
            guidance=args.get("guidance"),
            confidence="medium",
        )
    
    def _is_exit(self, feedback: str) -> bool:
        # 保留退出口令快速路径
        exit_words = ["退出", "exit", "quit", "done", "stop", "q", "算了", "保存", "结束", "再见"]
        return feedback in exit_words or feedback.lower() in exit_words
    
    def _build_unknown_intent(self, feedback: str) -> RefinementIntent:
        """LLM 不可达时的最小兜底"""
        return RefinementIntent(
            raw_input=feedback,
            refine_type="unknown",
            confidence="low",
            guidance=(
                "💡 我支持以下调整：\n"
                "   • 「只看XX」— 缩小数据范围\n"
                "   • 「换成XX指标」— 换分析指标\n"
                "   • 「简单点/详细点」— 调整报告详略\n"
                "   • 「为什么」— 解释已有结论\n"
                "   输入「退出」可结束并保存当前报告"
            ),
        )
```

3. **删除**以下不再需要的代码：
   - `ALLOWED_PATTERNS` 列表
   - `DIMENSION_KEYWORDS` 列表
   - `TARGET_KEYWORDS` 列表
   - `BLOCKED_PATTERNS` 列表（可在 system prompt 中用自然语言描述禁止的行为）
   - `_build_blocked_intent()` 方法
   - `_extract_details()` 方法
   - `_extract_filter_details()` 方法
   - `_extract_target_details()` 方法
   - `_extract_explain_details()` 方法

**预期效果**：
- 用户说"帮我只看一线城市"→ LLM 理解 `refine_type=filter, filter_column=城市, filter_value=一线`
- 用户说"切到 ROI 看看"→ LLM 理解 `refine_type=switch_target, new_target=ROI`
- 用户说"能不能给我重新跑一下加了年龄的"→ LLM 理解这是新分析方向，返回 `refine_type=new_direction` + 引导文案
- 任何正则无法覆盖的措辞都能被 LLM 理解

---

### 1.2 CLI 字段确认 — 关键词匹配判断用户意图

**文件**：`hagoku/manager/orchestrator.py`，`_request_field_confirmation()` 方法（第 2755-2825 行）

**问题描述**：

CLI 交互模式下，当用户确认字段理解时，代码直接用硬编码关键词集合判断用户的确认意图：

```python
# 第 2793 行
if user_input.lower() in ("好", "是", "ok", "继续", "next", "y", "yes"):
    # 用户确认了，展示最终字段理解
    ...

# 第 2801 行
if confirm.lower() in ("好", "是", "ok", "y", "yes", ""):
    # 二次确认通过
    break
```

**风险**：
- 虽然注释标明"仅用于 CLI 降级模式"，但如果 CLI 路径仍在使用，用户输入"没错"、"对的"、"正确的"、"理解了"等自然确认表达都不会被识别
- 用户输入"好，但是 Inc1 应该是收入而非销售额"——先被 `in ("好", ...)` 匹配为"确认"，后面的纠正信息被丢弃

**修复方案**：

将 `_request_field_confirmation()` 中的确认判断也走 LLM（已有 `_llm_understand_field_update()` 方法，稍作扩展即可）。

```python
def _request_field_confirmation(
    self,
    context: dict,
    project_name: str,
) -> dict | None:
    """Scout 识别完字段后，和用户对话确认字段含义。全程 LLM 驱动。"""
    print("\n" + "=" * 60)
    print("📋 字段理解")
    print("=" * 60)

    # 展示 Scout 识别出的所有字段
    print("\n我看到了这些字段：")
    for sem in context["column_semantics"]:
        col = sem["column_name"]
        desc = context["column_descriptions"].get(col, sem["inferred_type"])
        print(f"  {col} → {desc}")

    print("\n有不对的，纠正我。直接说就行")
    print("  比如：Inc1 是销售额，不是收入")
    print()

    corrections: dict[str, dict[str, str]] = {}

    while True:
        user_input = input("➜ ").strip()

        if user_input.lower() in ("cancel", "q", "取消"):
            print("\n❌ 已取消")
            return None

        if not user_input:
            continue

        # LLM 判断：是确认、纠正、还是混合
        action = self._llm_classify_confirmation(user_input, context)
        
        if action["type"] == "confirm":
            # 用户确认
            print("\n📋 最终字段理解：")
            for sem in context["column_semantics"]:
                col = sem["column_name"]
                desc = context["column_descriptions"].get(col, sem["inferred_type"])
                print(f"  {col} = {desc}")
            print("\n我准备进入数据清洗阶段，可以吗？")
            confirm = input("➜ (回车确认，或继续纠正) ").strip()
            if not confirm:
                break
            c_action = self._llm_classify_confirmation(confirm, context)
            if c_action["type"] == "confirm":
                break
            else:
                user_input = confirm  # 继续处理
                continue

        elif action["type"] == "correction":
            # 纯纠正：更新字段
            updates = action.get("updates", {})
            for col, info in updates.items():
                corrections[col] = info
                context["column_descriptions"][col] = f"{info['chinese_name']}（{info['business_meaning']}）"
                for s in context["column_semantics"]:
                    if s["column_name"] == col:
                        s["evidence"] = info['business_meaning']
                        break
                print(f"   ✅ {col} = {info['chinese_name']}（{info['business_meaning']}）")

        elif action["type"] == "mixed":
            # 先确认再纠正："好，但是 Inc1 应该是收入"
            updates = action.get("updates", {})
            for col, info in updates.items():
                corrections[col] = info
                context["column_descriptions"][col] = f"{info['chinese_name']}（{info['business_meaning']}）"
            # 纠正后继续展示，等用户再次确认
            print("\n📋 更新后的字段理解：")
            for sem in context["column_semantics"]:
                col = sem["column_name"]
                desc = context["column_descriptions"].get(col, sem["inferred_type"])
                print(f"  {col} = {desc}")
            print("\n可以进入数据清洗了吗？")

    # 保存
    if corrections:
        print(f"\n📝 保存 {len(corrections)} 个字段...")
        self._save_field_descriptions(project_name, corrections)

    print("\n✅ 进入数据清洗...")
    return context


def _llm_classify_confirmation(self, user_input: str, context: dict) -> dict:
    """LLM 判断用户输入是「确认」还是「纠正」还是「混合（确认+纠正）」。"""
    try:
        from ..llm.client import create_raw_client
        client = create_raw_client(self.config.llm)
        
        columns = [s["column_name"] for s in context["column_semantics"]]
        
        response = client.chat.completions.create(
            model=self.config.llm.model_quick or self.config.llm.model,
            messages=[
                {"role": "system", "content": (
                    "你是意图分类器。判断用户输入属于：\n"
                    "- confirm: 用户确认字段理解正确（如「好」「对的」「没问题」「确认」）\n"
                    "- correction: 用户纠正字段含义（如「Inc1 是销售额」「渠道错了」）\n"
                    "- mixed: 用户先确认再纠正（如「好，但是 Inc1 应该是收入」）\n"
                    "输出 JSON: {\"type\": \"confirm|correction|mixed\", \"updates\": {字段名: {\"chinese_name\": \"...\", \"business_meaning\": \"...\"}}}"
                )},
                {"role": "user", "content": f"字段列表：{', '.join(columns)}\n用户说：{user_input}"},
            ],
            temperature=0.0,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        import json
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        # 路径 1：LLM 不可达 → 抛出 RuntimeError，让用户看到
        raise RuntimeError(
            f"LLM 意图分类失败：LLM 不可达，请检查 API 配置。原始错误: {e}"
        ) from e
```

---

### 1.3 Scout 字段确认消息 — LLM 失败后代码直接拼接文案

**文件**：`hagoku/manager/orchestrator.py`，`_generate_phase_message()` 方法（第 2574-2663 行）

**问题描述**：

当 LLM 不可达时，代码用硬编码文案生成用户消息（第 2650-2663 行）：

```python
except Exception:
    # LLM 不可达时返回兜底
    if phase == "cleaning_strategy":
        n_ops = len(operations) if operations else 0
        quality_labels = {"good": "数据质量良好", ...}
        q = quality_labels.get(data_quality, data_quality)
        return f"{q}，计划执行 {n_ops} 个清洗操作。这个方案可以吗？"
```

**风险**：
- 这些硬编码文案是纯数据拼接而非 LLM 判断，虽然避免了语义错误，但生成的文案质量差且可能不合时宜
- 如果 LLM 不可达是整个系统的持续状态（而非偶发），用户会反复收到这些干巴巴的字符串

**修复方案**：

此问题的处理**不是去掉兜底（必须有兜底）**，而是：
1. 将兜底消息的生成也交给 LLM 的一个更轻量/更稳定的模型（如 `model_quick`）来尝试
2. 仅在两个 LLM 都不可达时，才用最简单的数据列表方式呈现（不做语义归因）

```python
def _generate_phase_message(self, phase, *, operations=None, ...):
    # ... 现有 LLM 调用逻辑 ...
    try:
        response = client.chat.completions.create(...)
        return response.choices[0].message.content.strip()
    except Exception:
        # 一级回退：尝试用 model_quick
        try:
            quick_client = create_raw_client(self.config.llm)
            response = quick_client.chat.completions.create(
                model=self.config.llm.model_quick or self.config.llm.model,
                messages=[...],
                temperature=0.3,
                max_tokens=200,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            # 二级回退：纯数据呈现，不做语义归因
            return self._build_fallback_data_message(phase, operations, ...)

def _build_fallback_data_message(self, phase, operations, ...):
    """LLM 完全不可达时的纯数据兜底（零语义归因）。"""
    if phase == "cleaning_strategy":
        n_ops = len(operations) if operations else 0
        if n_ops == 0:
            return "未检测到需要清洗的问题。"
        lines = [f"共 {n_ops} 个清洗操作："]
        for op in (operations or [])[:6]:
            lines.append(f"  • {op.get('column', '?')}: {op.get('reason', '')}")
        lines.append("请确认是否按此方案清洗。")
        return "\n".join(lines)
    # ...
```

---

## 2. 🟡 中严重度

### 2.1 TYPE_ECHO_SUFFIXES — 代码判断 LLM 产出是否有业务含义

**文件**：`hagoku/agents/scout/agent.py`，第 48-92 行

**问题描述**：

```python
_TYPE_ECHO_SUFFIXES: tuple[str, ...] = (
    "分类型", "数值型", "时间型", "文本型", "布尔型", "标识符", "未知类型",
)

def _description_is_user_facing_meaningful(col: str, desc: str) -> bool:
    """判断描述是否具有业务含义（非「列名（类型）」占位）。"""
    d = (desc or "").strip()
    c = (col or "").strip()
    if not d or d == c:
        return False
    for suf in _TYPE_ECHO_SUFFIXES:
        for o, cl in (("（", "）"), ("(", ")")):
            if d == f"{c}{o}{suf}{cl}":
                return False
    return True
```

**问题**：代码在判断 LLM 产出的字段描述是否"有业务含义"。比如 LLM 输出 `Inc1（数值型）` 被认为无含义，`Inc1：店铺收入金额` 被认为有含义。这个判断应该由 LLM 自己在 `submit_field_inference` 的 `needs_user_input` 字段中表达，而非代码做正则匹配。

**风险**：
- 如果 LLM 产出了 `店铺编号（标识符）`（包含业务含义但后缀是类型标签），会被误判为无含义
- 如果未来新增类型（如"货币型"、"百分比型"），需要修改代码

**修复方案**：

删除 `_description_is_user_facing_meaningful()` 方法和 `_TYPE_ECHO_SUFFIXES`，改为在 `submit_field_inference` 的 system prompt 中要求 LLM 在 `needs_user_input` 字段明确表达是否需要用户确认。

**具体修改**（`scout/agent.py` 第 870-875 行）：

```diff
-        # 3. 无 LLM 描述的列：标记 needs_user_input=True
-        for sem in context["column_semantics"]:
-            col = sem["column_name"]
-            raw = str(context["column_descriptions"].get(col, "") or "").strip()
-            if not raw or raw == col:
-                context.setdefault("column_display_names", {})[col] = col
-                sem["needs_user_input"] = True
+        # 3. 信任 LLM 的判断：needs_user_input 已在 _infer_all_semantics 中由 LLM 设置
+        # 不再由代码做二次判断。如果 LLM 未设置 needs_user_input，默认为 False（高置信度）。
```

同时在 `scout/prompt.md` 中强化 system prompt：

```markdown
## 字段推断规则

对于每个字段，你需要明确设置 `needs_user_input`：
- **true**：你无法确定该字段的业务含义，或置信度 < 0.7，需要用户确认
- **false**：你已经可以确定业务含义，无需用户确认

`description` 字段必须是纯业务含义描述，不要包含类型标签。
如「店铺编号」而非「店铺编号（标识符）」。
```

---

### 2.2 _generate_phase_message 兜底分支 — 代码拼接用户消息

已在 [1.3](#13-scout-字段确认消息--llm-失败后代码直接拼接文案) 中详细分析。

---

### 2.3 _describe_intent — 硬编码 intent_type 映射表

**文件**：`hagoku/manager/orchestrator.py`，第 2685-2687 行

**问题描述**：

```python
kind = {"comparison": "对比差异", "causation": "找原因", "correlation": "看关系",
        "trend": "看趋势", "diagnostic": "诊断问题"}.get(base, "探索规律")
```

**问题**：字典中缺少某些已在 `query_parser.py` 中定义的 intent_type（如 `growth_rate`、`roi_analysis` 等），如果 LLM 的 `thinking` 字段为空，这些类型会fallback到"探索规律"。

**风险**：低。因为实际上优先使用 LLM 的 `thinking` 字段（第 2671-2673 行），映射表只在 `thinking` 为空时才用。

**修复方案**：

保持现有结构，但补全映射表与 `query_parser.py` 一致，或者直接删除映射表并在 `thinking` 为空时让 LLM 生成 thinking：

```python
def _describe_intent(self, parsed_intent: Any) -> str:
    if parsed_intent is None:
        return "探索一下这份数据有什么规律"
    
    thinking = getattr(parsed_intent, "thinking", "") or ""
    if thinking.strip():
        return thinking.strip()
    
    # 兜底：补全所有 intent_type 的映射
    kind_map = {
        "comparison": "对比差异", "causation": "找原因",
        "correlation": "看关系", "trend": "看趋势",
        "diagnostic": "诊断问题", "roi_analysis": "看投入产出",
        "ltv_analysis": "看用户生命周期价值", "cac_analysis": "看获客成本",
        "funnel_conversion": "看转化漏斗", "attribution": "看归因",
        "investment_decision": "看投资决策", "cohort_analysis": "看人群分层",
        "growth_rate": "看增长率",
    }
    base = getattr(parsed_intent, "intent_type", "exploration") or "exploration"
    kind = kind_map.get(base, "探索规律")
    
    parts = []
    if getattr(parsed_intent, "target", None):
        parts.append(f"关注「{parsed_intent.target}」")
    # ...
    return f"{kind}，{'，'.join(parts)}" if parts else f"{kind}"
```

---

## 3. 🟢 低严重度

### 3.1 guardrails/parsers.py — 统计量提取正则

**文件**：`hagoku/guardrails/parsers.py`（全文件 261 行）

**问题描述**：从 LLM 自由文本中用正则提取 p 值、效应量、置信区间等统计量。

**分析**：这些是**结构化提取**而非语义理解。LLM 产出的统计结论中包含数值，代码需要将它们提取出来做合理性校验（如检查 p ∈ [0,1]、p 与 CI 一致性等）。这属于"增强 LLM 输出可靠性"而非"代替 LLM 做语义判断"。

**风险**：如果 LLM 产出的 p 值格式与正则不匹配（如 "p value equals 0.042"），提取会失败，导致合理性校验缺失。

**修复方案**：不移除，但可以在 `validate_analysis_output` 中增加一个 LLM fallback：如果正则提取全部失败，再让 LLM 用 JSON 结构化输出统计量。

---

### 3.2 respond() action 路由 — 前端枚举按钮

**文件**：`hagoku/manager/orchestrator.py`，第 2938-2961 行

```python
if action in ("进入清洗", "继续"):
    return {"status": "ready_for_cleaning", ...}
elif action in ("重新理解字段", "重新开始"):
    return {"status": "restart_scout", ...}
```

**分析**：这些 `action` 值来自前端 UI 按钮点击，不是用户的自由文本输入。属于 UI 路由逻辑，不涉及语义理解。不需要修改。

---

### 3.3 ws_handler.py 文本透传通道

**文件**：`hagoku/api/ws_handler.py`，第 261-262 行

```python
user_text = payload.get("text", payload.get("user_input", ""))
```

**分析**：WS 处理器是纯透传通道，将前端传来的用户输入原样传给 orchestrator。不改动用户文本，不做语义判断。不需要修改。

---

## 4. ✅ 已修复项

以下问题已在之前的 commit 中修复：

### 4.1 `_GATE_SUPPLEMENT_RE` 语义正则

**文件**：`hagoku/manager/orchestrator.py`
**修复方式**：删除了 `_GATE_SUPPLEMENT_RE` 正则，用户补充信息不再被误判为 UI 闸门确认。

### 4.2 `_is_gate_confirm` 判定逻辑

**文件**：`hagoku/manager/orchestrator.py`
**修复方式**：默认返回 `False`，仅在精确匹配 UI 确认短语时返回 `True`，避免自然语言被误判为确认。

---

## 5. 修复优先级矩阵

| 优先级 | 项目 | 影响范围 | 修复难度 | 预计工时 |
|--------|------|----------|----------|----------|
| P0 | RefinementParser LLM 化 | 所有 refinement 交互 | 中 | 4-6h |
| P1 | CLI 确认判断 LLM 化 | CLI 模式字段确认 | 低 | 2-3h |
| P2 | TYPE_ECHO_SUFFIXES 删除 | Scout 字段描述判断 | 低 | 1-2h |
| P3 | _describe_intent 映射补全 | 意图描述文案 | 极低 | 0.5h |
| P4 | _generate_phase_message 双层回退 | LLM 不可达时消息 | 低 | 1-2h |
| P5 | guardrails/parsers 统计量提取增强 | 统计校验可靠性 | 低 | 1-2h |

---

## 附录：审计方法论

本审计遵循以下原则：

1. **语义理解 = LLM 专属**：任何尝试从自然语言文本中提取意图、分类、路由的操作，必须经过 LLM。
2. **代码 = 结构化通道**：代码可以做 JSON 解析、字段映射、数值校验、格式转换等结构性操作。
3. **允许的代码操作**：
   - 数据结构变换（dict → dataclass）
   - 数值范围校验（p ∈ [0,1]）
   - JSON Schema 定义与解析
   - UI 状态路由（基于枚举值，非自然语言）
   - 退出口令匹配（固定词汇，非语义判断）
4. **禁止的代码操作**：
   - 从用户自然语言中用正则提取语义
   - 用关键词列表判断用户意图
   - 判断 LLM 产出的描述是否"有业务含义"
   - 在 LLM 不可达时用模板字符串模拟 LLM 的输出