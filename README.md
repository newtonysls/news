# 每周News（[点击这里获取最新咨询](https://github.com/newtonysls/news/edit/main/first.html)）
> 这里有什么？这里获取多个领域的最新发生的重大的事情，包括AI、医疗、政治、经济、游戏、新闻、体育、物理、造车等等。同时也会不定期的分享一些额外的穿插知识...
> 为什么干这事？强迫自己去学习各方面的知识的同时，带来更多的信息分享，减少信息差。
> 内容呈现的方式？包括文字、图片、视频、声音等等载体，最大程度的呈现有效内容给各位

## Agentic Retriever 原型

仓库提供了一个可运行的 `Agentic Retriever` 原型，支持：

1. 非黑盒、可解释的检索导航（可以显式查看知识库任意位置并迭代决策）。
2. 基于总结与记忆的路径复用（减少后续同类问题的检索时延）。
3. **Markdown 文档作为知识库入口**（可直接解析 `.md` 文件/目录）。

相关文件：

- `AGENTIC_RETRIEVER_DESIGN.md`：完整设计说明。
- `agentic_retriever.py`：最小可运行原型（含 CLI 测试）。

## 快速运行

默认使用 `README.md` 与 `AGENTIC_RETRIEVER_DESIGN.md` 作为知识库：

```bash
python3 agentic_retriever.py
```

指定 query 与知识库路径：

```bash
python3 agentic_retriever.py "如何让agent复用历史检索路径" --kb README.md AGENTIC_RETRIEVER_DESIGN.md
```

查看检索路径与迭代效果（重复运行同一 query）：

```bash
python3 agentic_retriever.py "如何降低后续检索时延" --kb . --runs 2
```

输出会显示：

- `used_memory`：是否复用了历史路径经验。
- `visited_path`：Agentic Retriever 的显式检索路径。
- `reasoning`：每一步动作与停止原因。
