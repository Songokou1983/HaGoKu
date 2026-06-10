0.53.0 记忆导入包
1. HaGoKu 最高准则
通道 = 用户说什么 LLM 看到什么，LLM 判什么用户看到什么。中间没有任何东西。代码和 prompt 都只能说流程（怎么思考），不能说结论（判成什么）。

铁律
零硬编码 — 关键词列表、中文正则、if-elif 中文分支链、_infer_不调LLM → 全禁止
LLM 失败 — 只能 A.raise B._last_understanding_failure C.部分落地 D.拒绝写入。禁止 except 兜底/默认值/缓存降级
提交前自检 — test_doctrine_compliance.py + test_information_arrival.py + 全量 pytest 必须绿
通道十律
意图穿透 | 原话不可销毁 | 多轮记忆 | 工具schema覆盖完备 | 单一权威 | 信息抵达正向断言 | 语义不确定可见化 | 控制通道 | 重推断触发 | 当前优先

自检（每次改LLM交互代码前必答）
LLM 拿到分析目标和数据后能自己判断吗？
能 → 删掉。prompt 说流程，不说结论。
不能（纯运算/IO）→ 代码的活。
常见错误
本能
正确
测试不绿→加规则
查prompt/工具schema
LLM失败→except兜底
raise RuntimeError
看到字段名→dict映射
LLM用工具映射
LLM可能空→默认值
写_last_understanding_failure
操作规则：每次commit+restart后，curl确认:8000/docs和:5173都200再让用户测。
2. 通道修复方法论
诊断先于治疗。 猜 prompt 就是破坏。启用 dump (HAGOKU_DUMP_LLM=1) 看 LLM 收到的完整上下文，找到真正问题再动手。
加规则不如修通道。 LLM 行为异常时，先检查传给 LLM 的信息是否完整、顺序是否正确、有没有重复——修通道而非修 LLM。
代码只是通道。 用户说好就是好，用户说进就进。任何替用户/LLM做决定的代码（意图分类、完成判断、自动推进）最终都会变成 bug。
测试不验证真实 IO 等于没写。 守门测试必须 monkeypatch 截获真实 LLM 调用，用锚点验证。删注入代码→测试 fail，加回→测试 pass，才算真守门。
3. LLM Dump 诊断方法
Why： run.log 只能看 LLM 调了什么工具，看不到完整上下文。通道污染、信息丢失、重复注入在 run.log 里不可见。

How to apply：
遇到 LLM 行为异常（乱选字段、不理解意图、阶段衔接断裂），优先 dump 完整上下文
启动：HAGOKU_DUMP_LLM=1 bash run_dump.sh
Dump 位置：.hagoku/llm_dumps/
看完 dump 中的 system/user/assistant 完整内容再下结论，不准看一行就开始猜
与旧 dump 对比找差异
4. 日志查阅规则
Why： 本 session 多次因看日志只看头尾（head/tail）就下结论，漏掉中间关键信息导致误判。

How to apply：
查日志必须读完完整文件，不准只看 head 或 tail 的几行
如果日志太长，用 range 分段读完
查到 LLM 调用记录后，确认是否有对应的响应记录（同一时间段内）
判断问题前必须确认日志里"有"什么和"没有"什么
