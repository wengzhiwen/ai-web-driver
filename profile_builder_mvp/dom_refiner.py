"""Interactive DOM refinement utilities for the profile builder CLI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

LONG_CONTENT_THRESHOLD = 3000
SEGMENT_THRESHOLD = 600
SUMMARY_KEEP_LIMIT = 2
PREVIEW_HEAD_LENGTH = 120
PREVIEW_TAIL_LENGTH = 120
REPEAT_THRESHOLD = 6
DEFAULT_SAMPLE_KEEP = 2
TEXT_PREVIEW_LENGTH = 40

InputFunc = Callable[[str], str]


@dataclass
class DomRefiner:
    """Applies interactive adjustments to a DOM summary tree."""

    root: Dict[str, object]
    interactive: bool
    input_func: InputFunc
    logs: List[str] = field(default_factory=list)

    def process(self) -> Tuple[Dict[str, object], List[str]]:
        if not isinstance(self.root, dict) or not self.interactive:
            return self.root, self.logs
        self._handle_long_content(self.root, "body")
        self._handle_repeated_structures(self.root, "body")
        return self.root, self.logs

    # ---- Long content handling -------------------------------------------------

    def _handle_long_content(self, node: Dict[str, object], path: str) -> None:
        total_len = self._text_length(node)
        if total_len >= LONG_CONTENT_THRESHOLD:
            skip_children = self._process_long_content_node(node, path, total_len)
            if skip_children:
                return
        for child in self._iter_children(node):
            child_path = self._child_path(path, child)
            self._handle_long_content(child, child_path)

    def _process_long_content_node(self, node: Dict[str, object], path: str, total_len: int) -> bool:
        head_preview, tail_preview = self._node_head_tail_preview(node)
        preview_lines = [
            f"发现长内容 {path}（约 {total_len} 字）",
            f"  头部预览：{head_preview}",
            f"  尾部预览：{tail_preview if tail_preview else '(无尾部预览)'}",
        ]
        prompt = "\n".join(preview_lines) + "\n是否压缩为摘要？[Y/n] "
        if not self._ask_yes_no(prompt, default_yes=True):
            self.logs.append(f"长内容 {path} 保留全文，逐段确认")
            self._prune_segments_interactively(node, path)
            return False

        children = list(self._iter_children(node))
        if not children:
            self.logs.append(f"长内容 {path} 缺少子节点，无法压缩")
            return False

        total_segments = len(children)
        keep_limit = self._ask_keep_limit(
            total_segments,
            default=SUMMARY_KEEP_LIMIT,
            prompt=(f"请输入希望保留的段数 (0-{total_segments}，回车默认 {SUMMARY_KEEP_LIMIT})："),
        )

        kept, omitted = self._apply_compression(node, children, keep_limit)
        self.logs.append(f"长内容 {path} 已压缩，保留 {kept} 段，省略 {omitted} 段")

        while omitted > 0 and self._ask_yes_no(
                "是否减少压缩区域，保留更多段？[y/N] ",
                default_yes=False,
        ):
            keep_limit = self._ask_keep_limit(
                total_segments,
                default=min(keep_limit + SUMMARY_KEEP_LIMIT, total_segments),
                prompt=(f"请输入新的保留段数 (当前 {keep_limit}，最大 {total_segments})："),
            )
            if keep_limit <= kept:
                print("保留段数未增加，保持现有压缩结果。")
                continue
            kept, omitted = self._apply_compression(node, children, keep_limit)
            self.logs.append(f"长内容 {path} 调整后保留 {kept} 段，省略 {omitted} 段")

        return True

    def _apply_compression(
        self,
        node: Dict[str, object],
        original_children: List[Dict[str, object]],
        keep_limit: int,
    ) -> Tuple[int, int]:
        keep_limit = max(0, min(keep_limit, len(original_children)))
        kept_children = list(original_children[:keep_limit])
        omitted_count = max(len(original_children) - keep_limit, 0)
        depth = int(node.get("depth", 0)) + 1
        if omitted_count:
            placeholder = {
                "tag": "div",
                "depth": depth,
                "attrs": {
                    "data-trimmed": "true"
                },
                "text": f"[省略 {omitted_count} 段正文]",
            }
            kept_children.append(placeholder)

        node["children"] = kept_children
        return keep_limit, omitted_count

    def _prune_segments_interactively(self, node: Dict[str, object], path: str) -> None:
        children = node.get("children")
        if not isinstance(children, list):
            return

        removal_indices: List[int] = []
        for idx, child in enumerate(children):
            segment_len = self._text_length(child)
            if segment_len < SEGMENT_THRESHOLD:
                continue
            preview = self._node_preview(child)
            prompt = f"是否删除 {path} 段落 #{idx + 1}（约 {segment_len} 字，开头：{preview}）？[y/N/all] "
            decision = self._ask_segment(prompt)
            if decision == "all":
                break
            if decision:
                removal_indices.append(idx)

        if not removal_indices:
            return

        for idx in sorted(removal_indices, reverse=True):
            del children[idx]
            self.logs.append(f"长内容 {path} 手动删除 {len(removal_indices)} 段正文")

    # ---- Repeated structure handling ------------------------------------------

    def _handle_repeated_structures(self, node: Dict[str, object], path: str) -> None:
        while True:
            children = node.get("children")
            if not isinstance(children, list):
                break

            signatures = self._group_repeated_children(children)
            processed_group = False
            for signature, indices in signatures.items():
                count = len(indices)
                if count < REPEAT_THRESHOLD:
                    continue

                samples = self._sample_texts(children, indices)
                sample_str = "，".join(samples) or "(无文本示例)"
                prompt = f"在 {path} 检测到 {count} 条重复结构（示例：{sample_str}），"
                prompt += "仅保留前 2 条可以吗？[Y/n/自定义数量] "
                keep = self._ask_keep_count(prompt, default_keep=DEFAULT_SAMPLE_KEEP)
                if keep is None:
                    self.logs.append(f"重复结构 {path}{signature} 保留全部 {count} 条")
                    continue

                keep = max(0, min(keep, count))
                kept_indices = set(indices[:keep])
                omitted = count - keep
                new_children: List[Dict[str, object]] = []
                placeholder_position: Optional[int] = None
                depth = int(node.get("depth", 0)) + 1

                for idx, child in enumerate(children):
                    if idx in indices:
                        if idx in kept_indices:
                            new_children.append(child)
                        else:
                            if placeholder_position is None:
                                placeholder_position = len(new_children)
                        continue
                    new_children.append(child)

                if omitted > 0:
                    placeholder = {
                        "tag": "div",
                        "depth": depth,
                        "attrs": {
                            "data-trimmed": "true"
                        },
                        "text": f"[其余 {omitted} 项省略]",
                    }
                    insert_at = placeholder_position if placeholder_position is not None else len(new_children)
                    new_children.insert(insert_at, placeholder)

                node["children"] = new_children
                self.logs.append(f"重复结构 {path}{signature} 保留 {keep} 条，省略 {omitted} 条")
                processed_group = True
                break

            if not processed_group:
                break

        for child in self._iter_children(node):
            child_path = self._child_path(path, child)
            self._handle_repeated_structures(child, child_path)

    # ---- Helpers ----------------------------------------------------------------

    def _iter_children(self, node: Dict[str, object]) -> Iterable[Dict[str, object]]:
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    yield child

    def _text_length(self, node: Dict[str, object]) -> int:
        total = len(node.get("text", "") or "")
        for child in self._iter_children(node):
            total += self._text_length(child)
        return total

    def _node_preview(self, node: Dict[str, object]) -> str:
        text = (node.get("text") or "").strip()
        if text:
            return text[:TEXT_PREVIEW_LENGTH]
        for child in self._iter_children(node):
            preview = self._node_preview(child)
            if preview:
                return preview
        return ""

    def _node_head_tail_preview(self, node: Dict[str, object]) -> Tuple[str, str]:
        text = self._collect_text(node)
        if not text:
            return "(无文本)", ""
        normalized = " ".join(text.split())
        if len(normalized) <= PREVIEW_HEAD_LENGTH:
            return normalized, ""
        head = normalized[:PREVIEW_HEAD_LENGTH]
        tail = normalized[-PREVIEW_TAIL_LENGTH:]
        return head, tail

    def _collect_text(self, node: Dict[str, object]) -> str:
        excluded_tags = {"script", "style", "noscript"}
        parts: List[str] = []

        def _walk(current: Dict[str, object]) -> None:
            tag = current.get("tag")
            if isinstance(tag, str) and tag.lower() in excluded_tags:
                return

            text = current.get("text")
            if isinstance(text, str):
                cleaned = text.strip()
                if cleaned:
                    parts.append(cleaned)

            for child in self._iter_children(current):
                _walk(child)

        _walk(node)
        return " ".join(parts)

    def _child_path(self, parent_path: str, child: Dict[str, object]) -> str:
        label = child.get("tag", "node")
        attrs = child.get("attrs") or {}
        node_id = attrs.get("id")
        node_class = attrs.get("class")
        if isinstance(node_id, str) and node_id:
            label += f"#{node_id.strip()}"
        elif isinstance(node_class, str) and node_class:
            first_class = node_class.strip().split()[0]
            if first_class:
                label += f".{first_class}"
        return f"{parent_path} > {label}"

    def _group_repeated_children(self, children: List[Dict[str, object]]) -> Dict[str, List[int]]:
        groups: Dict[str, List[int]] = {}
        for idx, child in enumerate(children):
            signature = self._child_signature(child)
            groups.setdefault(signature, []).append(idx)
        return groups

    def _child_signature(self, child: Dict[str, object]) -> str:
        tag = child.get("tag", "node")
        attrs = child.get("attrs") or {}
        class_name = attrs.get("class")
        if isinstance(class_name, str) and class_name.strip():
            class_key = " ".join(class_name.strip().split()[:2])
        else:
            class_key = ""
        role = attrs.get("role") or ""
        return f"<{tag} class='{class_key}' role='{role}'>"

    def _sample_texts(self, children: List[Dict[str, object]], indices: List[int]) -> List[str]:
        samples: List[str] = []
        for idx in indices[:3]:
            preview = self._node_preview(children[idx])
            if preview:
                samples.append(preview)
        return samples

    # ---- Input helpers ----------------------------------------------------------

    def _ask_yes_no(self, prompt: str, default_yes: bool) -> bool:
        default = "y" if default_yes else "n"
        while True:
            answer = self.input_func(prompt).strip().lower()
            if not answer:
                answer = default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
            print("请输入 y 或 n")

    def _ask_keep_limit(
        self,
        total: int,
        *,
        default: int,
        prompt: str,
    ) -> int:
        while True:
            answer = self.input_func(prompt).strip().lower()
            if not answer:
                return min(default, total)
            if answer.isdigit():
                value = int(answer)
                if 0 <= value <= total:
                    return value
            print(f"请输入 0 到 {total} 的整数")

    def _ask_segment(self, prompt: str) -> Optional[bool | str]:
        while True:
            answer = self.input_func(prompt).strip().lower()
            if answer in {"", "n", "no"}:
                return False
            if answer in {"y", "yes"}:
                return True
            if answer == "all":
                return "all"
            print("请输入 y/n/all")

    def _ask_keep_count(self, prompt: str, default_keep: int) -> Optional[int]:
        while True:
            answer = self.input_func(prompt).strip().lower()
            if answer in {"", "y", "yes"}:
                return default_keep
            if answer in {"n", "no"}:
                return None
            if answer.isdigit():
                return int(answer)
            print("请输入 y/n 或数字")


def refine_dom_summary(
    dom_summary: Dict[str, object],
    *,
    interactive: bool,
    input_func: InputFunc = input,
) -> Tuple[Dict[str, object], List[str]]:
    """Refine the DOM summary optionally in interactive mode."""

    refiner = DomRefiner(dom_summary, interactive=interactive, input_func=input_func)
    return refiner.process()
