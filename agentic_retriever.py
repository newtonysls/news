"""Agentic Retriever prototype with transparent navigation and markdown KB ingestion."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import re


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def tokenize(text: str) -> List[str]:
    """A small tokenizer for Chinese/English mixed text."""
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def overlap_score(query: str, text: str) -> float:
    """Jaccard overlap score on token sets."""
    q = set(tokenize(query))
    t = set(tokenize(text))
    if not q or not t:
        return 0.0
    inter = len(q & t)
    union = len(q | t)
    return inter / union if union else 0.0


@dataclass
class DocNode:
    node_id: str
    title: str
    content: str
    neighbors: List[str] = field(default_factory=list)
    source: str = ""


@dataclass
class TrajectorySummary:
    pattern: str
    first_hop: str
    successful_path: List[str]
    rationale: str


class RetrievalMemory:
    """Stores retrieval experience summaries (no model training required)."""

    def __init__(self):
        self._items: List[TrajectorySummary] = []

    def add(self, summary: TrajectorySummary) -> None:
        self._items.append(summary)

    def suggest(self, query: str, threshold: float = 0.15) -> Optional[TrajectorySummary]:
        if not self._items:
            return None
        ranked = sorted(
            self._items,
            key=lambda item: overlap_score(query, item.pattern),
            reverse=True,
        )
        best = ranked[0]
        return best if overlap_score(query, best.pattern) >= threshold else None


class KnowledgeNavigator:
    """Exposes transparent navigation primitives for the retriever agent."""

    def __init__(self, nodes: Sequence[DocNode]):
        if not nodes:
            raise ValueError("KnowledgeNavigator requires at least one node")
        self.nodes: Dict[str, DocNode] = {n.node_id: n for n in nodes}

    def inspect(self, node_id: str) -> DocNode:
        if node_id not in self.nodes:
            raise KeyError(f"Unknown node_id={node_id}")
        return self.nodes[node_id]

    def jump_candidates(self, hint: str, top_k: int = 3) -> List[Tuple[str, float]]:
        scored = []
        for node in self.nodes.values():
            text = f"{node.title} {node.content}"
            scored.append((node.node_id, overlap_score(hint, text)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


class AgenticRetriever:
    """Retriever with explicit navigation + iterative memory reuse.

    Loop:
    1) Try memory-based shortcut path from past trajectories.
    2) If no suitable memory, do transparent exploration on graph.
    3) Summarize successful trajectory for future similar queries.
    """

    def __init__(self, navigator: KnowledgeNavigator, memory: Optional[RetrievalMemory] = None):
        self.navigator = navigator
        self.memory = memory or RetrievalMemory()

    def retrieve(self, query: str, max_steps: int = 5) -> Dict[str, object]:
        visited: List[str] = []
        reasoning: List[str] = []

        prior = self.memory.suggest(query)
        if prior is not None:
            reasoning.append(
                f"Reuse memory pattern='{prior.pattern}', jump to first_hop={prior.first_hop}"
            )
            path = prior.successful_path[: max_steps + 1]
            last_node: Optional[DocNode] = None
            for node_id in path:
                node = self.navigator.inspect(node_id)
                last_node = node
                visited.append(node.node_id)
                if overlap_score(query, node.content) >= 0.2:
                    reasoning.append(f"Found likely answer at {node.node_id} by memory shortcut")
                    return {
                        "answer_node": node,
                        "visited": visited,
                        "reasoning": reasoning,
                        "used_memory": True,
                    }
            if last_node is not None:
                reasoning.append("Memory shortcut executed; no better node found, return last hop")
                return {
                    "answer_node": last_node,
                    "visited": visited,
                    "reasoning": reasoning,
                    "used_memory": True,
                }

        jump = self.navigator.jump_candidates(query, top_k=1)
        if not jump:
            return {"answer_node": None, "visited": visited, "reasoning": ["No candidates"]}

        current_id = jump[0][0]
        reasoning.append(f"Cold start jump to {current_id}")

        best_node = self.navigator.inspect(current_id)
        best_score = overlap_score(query, f"{best_node.title} {best_node.content}")

        for _ in range(max_steps):
            node = self.navigator.inspect(current_id)
            visited.append(node.node_id)

            local_best_id = node.node_id
            local_best_score = overlap_score(query, f"{node.title} {node.content}")

            for nxt in node.neighbors:
                neighbor = self.navigator.inspect(nxt)
                sc = overlap_score(query, f"{neighbor.title} {neighbor.content}")
                if sc > local_best_score:
                    local_best_score = sc
                    local_best_id = nxt

            if local_best_score <= best_score or local_best_id == current_id:
                reasoning.append("Stop expansion: no better neighbor found")
                break

            current_id = local_best_id
            best_node = self.navigator.inspect(current_id)
            best_score = local_best_score
            reasoning.append(f"Move to better neighbor {current_id}, score={best_score:.3f}")

        if visited:
            self.memory.add(
                TrajectorySummary(
                    pattern=" ".join(tokenize(query)[:8]),
                    first_hop=visited[0],
                    successful_path=visited,
                    rationale="Auto summary from successful exploration",
                )
            )

        return {
            "answer_node": best_node,
            "visited": visited,
            "reasoning": reasoning,
            "used_memory": False,
        }


def parse_markdown_file(path: Path) -> List[DocNode]:
    """Parse one markdown file into heading-based knowledge nodes."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    sections: List[Tuple[str, List[str]]] = []
    current_title = path.stem
    current_content: List[str] = []

    for raw_line in lines:
        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            if current_content:
                sections.append((current_title, current_content))
            current_title = heading_match.group(2).strip()
            current_content = []
        else:
            current_content.append(raw_line)

    if current_content:
        sections.append((current_title, current_content))

    nodes: List[DocNode] = []
    for idx, (title, content_lines) in enumerate(sections):
        node_id = f"{path.stem}::{idx}"
        content = "\n".join(content_lines).strip()
        nodes.append(
            DocNode(
                node_id=node_id,
                title=title or f"{path.stem}-{idx}",
                content=content,
                source=str(path),
            )
        )

    for idx in range(len(nodes)):
        neighbors: List[str] = []
        if idx > 0:
            neighbors.append(nodes[idx - 1].node_id)
        if idx + 1 < len(nodes):
            neighbors.append(nodes[idx + 1].node_id)
        nodes[idx].neighbors = neighbors

    return nodes


def load_markdown_knowledge_base(paths: Sequence[str]) -> List[DocNode]:
    """Load markdown files/directories as knowledge-base nodes."""
    files: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.glob("*.md")))
        elif p.is_file() and p.suffix.lower() == ".md":
            files.append(p)

    unique_files = list(dict.fromkeys(files))
    all_nodes: List[DocNode] = []
    for md_file in unique_files:
        parsed = parse_markdown_file(md_file)
        all_nodes.extend(parsed)

    if not all_nodes:
        raise ValueError("No markdown nodes loaded. Check --kb path(s).")
    return all_nodes


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Agentic Retriever over markdown knowledge base")
    parser.add_argument("query", nargs="?", default="agentic retriever 如何降低检索时延")
    parser.add_argument(
        "--kb",
        nargs="+",
        default=["README.md", "AGENTIC_RETRIEVER_DESIGN.md"],
        help="Markdown files or directories as knowledge base",
    )
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--runs", type=int, default=2, help="Repeat query to observe memory reuse")
    args = parser.parse_args()

    nodes = load_markdown_knowledge_base(args.kb)
    retriever = AgenticRetriever(KnowledgeNavigator(nodes))

    print(f"Loaded nodes: {len(nodes)} from {args.kb}")
    for run_idx in range(1, args.runs + 1):
        result = retriever.retrieve(args.query, max_steps=args.max_steps)
        answer_node = result["answer_node"]
        print(f"\n=== Run {run_idx} ===")
        print(f"used_memory: {result['used_memory']}")
        print(f"visited_path: {' -> '.join(result['visited'])}")
        print("reasoning:")
        for step in result["reasoning"]:
            print(f"- {step}")

        if answer_node is None:
            print("answer: <none>")
        else:
            snippet = answer_node.content.replace("\n", " ")[:120]
            print(
                f"answer_node: {answer_node.node_id} | title={answer_node.title} | "
                f"source={answer_node.source}"
            )
            print(f"answer_snippet: {snippet}")


if __name__ == "__main__":
    run_cli()
