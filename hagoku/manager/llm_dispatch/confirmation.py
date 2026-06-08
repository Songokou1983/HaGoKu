"""用户确认分类 + 字段确认载荷。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

from typing import Any

def _llm_classify_confirmation(self, user_input: str, context: dict) -> dict:
    """LLM 判断用户输入是「确认」还是「纠正」还是「混合（确认+纠正）」。

    返回 {"type": "confirm|correction|mixed", "updates": {col: {chinese_name, business_meaning}}}
    """
    try:
        from hagoku.llm.client import create_raw_client

        columns = [s["column_name"] for s in context["column_semantics"]]

        client = create_raw_client(self.config.llm)
        response = client.chat.completions.create(
            model=self.config.llm.model_quick or self.config.llm.model,
            messages=[
                {"role": "system", "content": (
                    "你是意图分类器。判断用户在字段确认阶段的输入属于：\n"
                    "- confirm: 用户确认字段理解正确，同意继续（如「好」「对的」「没问题」「确认」「可以」）\n"
                    "- correction: 用户纠正字段含义（如「Inc1 是销售额」「渠道错了，应该是来源」）\n"
                    "- mixed: 用户先确认再纠正（如「好，但是 Inc1 应该是收入」）\n\n"
                    "输出纯 JSON:\n"
                    '{"type": "confirm|correction|mixed", '
                    '"updates": {"字段名": {"chinese_name": "...", "business_meaning": "..."}}}'
                )},
                {"role": "user", "content": f"字段列表：{', '.join(columns)}\n用户说：{user_input}"},
            ],
            temperature=0.0,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        import json
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        return json.loads(result_text.strip())
    except Exception as e:
        # F-021 修复：LLM 不可达时必须 raise RuntimeError（铁律 2 路径 A），
        # 不得返回兜底默认值 {"type": "correction", "updates": {}}。
        raise RuntimeError(
            f"_llm_classify_confirmation: LLM 不可达。原始错误: {e}"
        ) from e

def _build_intent_context(self, query: str, parsed_intent: Any) -> str:
    """将解析后的意图构建成 LLM 可用的上下文（无硬编码标签）。"""
    if parsed_intent is None:
        return query

    parts = [query]
    attrs = [
        ("intent_type", "意图"),
        ("target", "目标变量"),
        ("time_range", "时间范围"),
        ("group_by", "分组维度"),
        ("filters", "筛选条件"),
    ]
    for attr, label in attrs:
        v = getattr(parsed_intent, attr, None)
        if v:
            if isinstance(v, list):
                v = "、".join(str(x) for x in v)
            parts.append(f"\n【{label}】：{v}")

    thinking = getattr(parsed_intent, "thinking", "") or ""
    if thinking.strip():
        parts.append(f"\n【LLM 理解】：{thinking.strip()}")

    return "".join(parts)

# ==== CLI 交互模式：全程 LLM 驱动 ====
# 用户确认/纠正/混合意图都由 LLM 判断，代码只做结构化路由和兜底。

def _request_field_confirmation(
    self,
    context: dict,
    project_name: str,
) -> dict | None:
    """
    Scout 识别完字段后，和用户对话确认字段含义。
    全程 LLM 驱动：用户意图由 LLM 分类为 confirm/correction/mixed。
    """
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

        if user_input.lower() in ("cancel", "q", "/cancel"):
            print("\n❌ 已取消")
            return None

        if not user_input:
            continue

        # LLM 判断：确认 / 纠正 / 混合（确认+纠正）
        action = self._llm_classify_confirmation(user_input, context)

        if action["type"] == "confirm":
            # 用户确认，进入最终展示
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
            # 有纠正内容则继续处理
            updates = c_action.get("updates", {})
            if updates:
                self._apply_field_corrections(context, corrections, updates)
        else:
            # correction 或 mixed：先应用纠正，再继续确认循环
            updates = action.get("updates", {})
            if updates:
                self._apply_field_corrections(context, corrections, updates)
            if action["type"] == "mixed":
                # 用户确认+纠正，纠正后展示最终结果再让用户确认
                print("\n📋 更新后的字段理解：")
                for sem in context["column_semantics"]:
                    col = sem["column_name"]
                    desc = context["column_descriptions"].get(col, sem["inferred_type"])
                    print(f"  {col} = {desc}")
                print("\n可以进入数据清洗了吗？")
                # 继续循环等用户确认
                continue

    if corrections:
        print(f"\n📝 保存 {len(corrections)} 个字段...")
        self._save_field_descriptions(project_name, corrections)

    print("\n✅ 进入数据清洗...")
    return context

def _apply_field_corrections(
    self,
    context: dict,
    corrections: dict,
    updates: dict,
) -> None:
    """将 LLM 识别的字段纠正应用到 context 和 corrections 记录中。"""
    for col, info in updates.items():
        corrections[col] = info
        context["column_descriptions"][col] = f"{info['chinese_name']}（{info['business_meaning']}）"
        for s in context["column_semantics"]:
            if s["column_name"] == col:
                s["evidence"] = info["business_meaning"]
                s["needs_user_input"] = False
                # F-053 修复：同步 description / display_name 到 column_semantics，
                # 确保律 5 SSoT 中的字段语义与 column_descriptions 一致。
                s["description"] = info["business_meaning"]
                s["display_name"] = info["chinese_name"]
                break
        print(f"   ✅ {col} = {info['chinese_name']}（{info['business_meaning']}）")


class ConfirmationMixin:
    """Mixin：confirmation 模块级函数注册为 Orchestrator 的方法。"""
    _llm_classify_confirmation = _llm_classify_confirmation
    _build_intent_context = _build_intent_context
    _request_field_confirmation = _request_field_confirmation
    _apply_field_corrections = _apply_field_corrections
