# Contributing to HaGoK

**感谢你考虑为 HaGoK 贡献！**

但先说一句实话：**这是一个单人维护项目**，不是团队协作仓库。

## 📢 这个项目怎么维护的

- 单分支：`master` 一条线到底，**不开 feature branch**（也不接收 PR）
- 单维护者：所有改动由项目作者 + AI 协作完成
- 公开仓库的目的：**学习、参考、引用**——不是号召众人贡献

## 🐛 怎么提 Issue（欢迎）

**Issue 是这个项目**唯一**接受的贡献形式**。

适合提 Issue 的：
- 🐛 **Bug 报告**（用了下报错了、行为不对）
- 📚 **文档不清楚**（某处读不懂、缺例子）
- 🤔 **架构讨论**（对单 Agent 设计、通道架构有看法）
- 💡 **用例分享**（你用它做了什么、效果如何）

不适合 Issue 的：
- ❌ 大型功能 PR（不被接受，但想法可以讨论）
- ❌ "How to use" 类问题（先看 README + docs/）
- ❌ 与核心架构无关的边角调整

## ❓ 怎么提问（建议先搜）

提 Issue 前请先：
1. 搜 [已有 Issue](https://github.com/Songokou1983/HaGoKu/issues)
2. 读 [README](README.md) + [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
3. 看 [docs/CHANNEL.md](docs/CHANNEL.md) 了解设计哲学
4. 看自己机器上的 `~/.hagoku/hagoku.log` 和 `~/.hagoku/llm_dumps/`（如果报错）

## 🔧 想 fork 自己改？

MIT 协议鼓励你 fork：

```bash
git clone https://github.com/YOUR_NAME/HaGoKu.git
cd HaGoKu
# 随便改，这是你的分支
```

如果你改了觉得好：
- 在 [Discussions](https://github.com/Songokou1983/HaGoKu/discussions) 分享
- 不期望合并回上游，但欢迎讨论

## 💡 我想贡献一个工具/功能

可以**讨论**，不一定合并：

1. 在 Issue 里描述你的想法
2. 维护者会回复是否在路线图内
3. 即使不在路线图内，**你的实现可以成为你自己的 fork**

为什么这么严格？参考 [docs/CHANNEL.md](docs/CHANNEL.md) —「工具三问」原则。
**不是所有好想法都该合并到一个核心仓库**。否则 12 个工具会膨胀到 36 个，
LLM 选择困难。

## 🙏 不接受 PR 但接受什么

- **Issue**（bug 报告、讨论、用例分享）
- **Discussion**（架构辩论、用例展示、问题互助）
- **Star** ⭐（如果觉得有用）
- **引用**（学术论文、博客、个人项目）

---

## 📜 行为准则

- 善意沟通
- 不歧视任何个人或群体
- 批评想法不针对人
- 不发垃圾 Issue（会被关）

---

**再次感谢**——即使只是 star，也是对个人开发者最大的支持 ❤️