"""CLI entry for the profile builder MVP."""
from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
import re
from hashlib import sha1
from urllib.parse import unquote, urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency

    def load_dotenv(*_args, **_kwargs):
        return False


from .dom_refiner import refine_dom_summary
from .llm_annotator import LLMAnnotator
from .models import AliasDefinition, AnnotatedPage, AnnotationRequest, FetchOptions
from .page_fetcher import fetch_page
from .profile_merger import merge_page_into_profile

LOG_DIR = Path("log")
SITE_PROFILES_ROOT = Path("site_profiles")
LOGGER = logging.getLogger("profile_builder.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="自动化生成 Site Profile 标定草稿")
    parser.add_argument("--url", required=True, help="目标页面 URL")
    parser.add_argument("--base-url", help="站点的 base URL，用于提示 LLM")
    parser.add_argument("--site-name", help="站点名称，用于提示 LLM 和输出")
    parser.add_argument("--output", help="将本次生成结果写入独立 JSON 文件")
    parser.add_argument("--append-to", help="将结果合并追加到既有 Site Profile 文件中")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="LLM temperature (默认 0.2)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=8,
        help="DOM 抽取的最大深度 (默认 8)",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=1000,
        help="DOM 摘要的最大节点数 (默认 1000)",
    )
    parser.add_argument("--wait-for", help="页面加载后需要等待的 selector")
    parser.add_argument(
        "--timeout",
        type=int,
        default=10_000,
        help="页面加载/等待的超时时间 (毫秒，默认 10000)",
    )
    parser.add_argument(
        "--include-screenshot",
        action="store_true",
        help="抓取时生成页面截图供人工校对",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="禁用 headless，方便调试页面抓取",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅输出到终端，不写入文件")
    parser.add_argument("--interactive", action="store_true", help="开启交互模式")
    parser.add_argument("--debug", action="store_true", help="启用 DEBUG 日志")
    return parser


def _setup_logging(debug: bool) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level)

    file_handler = TimedRotatingFileHandler(
        LOG_DIR / "profile_builder.log",
        when="midnight",
        encoding="utf-8",
        backupCount=7,
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logging.getLogger().addHandler(file_handler)


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc or "page"
    path = unquote(parsed.path or "")
    segments = [segment for segment in path.split("/") if segment]
    raw_slug = "-".join([netloc, *segments])
    if not raw_slug:
        raw_slug = "page"

    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "-", raw_slug)
    sanitized = re.sub(r"-+", "-", sanitized).strip("-") or "page"

    max_length = 80
    if len(sanitized) > max_length:
        digest = sha1(sanitized.encode("utf-8")).hexdigest()[:10]
        prefix = sanitized[:max_length - 11]
        sanitized = f"{prefix}-{digest}"
    return sanitized


def _annotate(dom_result, args, *, is_detail_page: bool, detail_label: Optional[str]) -> AnnotationRequest:
    return AnnotationRequest(
        url=dom_result.url,
        title=dom_result.title,
        dom_summary=dom_result.dom_summary,
        site_name=args.site_name,
        base_url=args.base_url,
        temperature=args.temperature,
        is_detail_page=is_detail_page,
        detail_label=detail_label,
    )


def _single_page_profile(annotated_page) -> Dict[str, object]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload: Dict[str, object] = {
        "version": timestamp,
        "pages": [],
    }
    entry = {
        "id": annotated_page.page_id,
        "name": annotated_page.page_name,
        "url_pattern": annotated_page.url_pattern,
        "version": timestamp,
        "generated_by": "profile_builder_cli",
        "aliases": {
            alias.name: alias.to_profile_dict()
            for alias in annotated_page.aliases
        },
    }
    if annotated_page.summary:
        entry["summary"] = annotated_page.summary
    payload["pages"].append(entry)
    return payload


def _ask_detail_page() -> bool:
    while True:
        answer = input("该页面是否为详情页（需要更抽象的描述）？[y/N] ").strip().lower()
        if not answer:
            return False
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("请输入 y 或 n")


def _abstract_detail_page_name(original: str, fallback: str | None = None) -> str:
    source = original or fallback or "详情页"
    dingbats = "“”\"《》"
    cleaned = source.translate(str.maketrans({char: "" for char in dingbats}))
    cleaned = cleaned.replace("详情页", "").strip()

    separators = ["：", ":", "——", "—", " - ", "--"]
    for sep in separators:
        if sep in cleaned:
            candidate = cleaned.split(sep)[-1].strip()
            if candidate:
                cleaned = candidate

    cleaned = re.sub(r"[\?？!！。.]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)

    if len(cleaned) > 10:
        cleaned = cleaned[:10]
    if not cleaned:
        return "详情页"
    return f"{cleaned}详情页"


def _derive_detail_page_label(url: str, site_name: Optional[str]) -> str:
    parsed = urlparse(url)
    segments = [seg.lower() for seg in parsed.path.split("/") if seg]

    mapping = [
        ("blog", "博客详情页"),
        ("article", "文章详情页"),
        ("news", "新闻详情页"),
        ("product", "产品详情页"),
        ("case", "案例详情页"),
        ("course", "课程详情页"),
        ("doc", "文档详情页"),
    ]

    for key, label in mapping:
        if any(key in segment for segment in segments):
            return label

    if site_name:
        if "博客" in site_name:
            return "博客详情页"
        if "产品" in site_name:
            return "产品详情页"
        if "课程" in site_name:
            return "课程详情页"

    return "详情页"


def _enhance_annotations(page: AnnotatedPage, fetched: FetchedPage) -> list[str]:
    logs: list[str] = []
    existing_names = {alias.name for alias in page.aliases}
    existing_selectors = {alias.selector for alias in page.aliases if alias.selector}

    controls = fetched.controls or []

    search_controls = [control for control in controls if _control_looks_like_search(control)]
    search_inputs = [control for control in search_controls if _control_is_input(control)]
    search_buttons = [control for control in search_controls if _control_is_button(control)]

    def add_alias(name: str, control: Dict[str, Any], description: str, role: str, confidence: float) -> None:
        selector = _control_to_selector(control)
        if not selector:
            return
        if name in existing_names or selector in existing_selectors:
            return
        page.aliases.append(AliasDefinition(
            name=name,
            selector=selector,
            description=description,
            role=role,
            confidence=confidence,
        ), )
        existing_names.add(name)
        existing_selectors.add(selector)
        logs.append(f"新增 {name} -> {selector}")

    if search_inputs:
        add_alias("search.input", search_inputs[0], "搜索区域输入框", "文本输入", 0.85)
    if search_buttons:
        add_alias("search.button", search_buttons[0], "搜索区域提交按钮", "按钮", 0.85)

    return logs


def _control_looks_like_search(control: Dict[str, Any]) -> bool:
    tokens = " ".join(str(control.get(field) or "") for field in ("id", "className", "role", "path", "ariaLabel", "nameAttr", "dataTest")).lower()
    return any(keyword in tokens for keyword in ("search", "lookup", "find"))


def _control_is_input(control: Dict[str, Any]) -> bool:
    tag = (control.get("tag") or "").lower()
    if tag in {"input", "textarea"}:
        return True
    role = (control.get("role") or "").lower()
    return role in {"textbox", "combobox"}


def _control_is_button(control: Dict[str, Any]) -> bool:
    tag = (control.get("tag") or "").lower()
    if tag == "button":
        return True
    role = (control.get("role") or "").lower()
    return role in {"button", "link"}


def _control_to_selector(control: Dict[str, Any]) -> Optional[str]:
    element_id = control.get("id")
    if element_id:
        return f"#{element_id}"
    class_attr = control.get("className")
    tag = (control.get("tag") or "").lower() or "div"
    if isinstance(class_attr, str) and class_attr.strip():
        first = class_attr.strip().split()[0]
        return f"{tag}.{first}"
    data_test = control.get("dataTest")
    if data_test:
        return f"[data-test='{data_test}']"
    name_attr = control.get("nameAttr")
    if name_attr:
        return f"{tag}[name='{name_attr}']"
    aria_label = control.get("ariaLabel")
    if aria_label:
        return f"{tag}[aria-label='{aria_label}']"
    path = control.get("path")
    if path:
        return path
    return None


def _find_nodes(root: Dict[str, Any], predicate) -> list[Dict[str, Any]]:
    matches: list[Dict[str, Any]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict) and predicate(node):
            matches.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return matches


def _find_first_child(root: Dict[str, Any], predicate) -> Optional[Dict[str, Any]]:
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict) and predicate(node):
            return node
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return None


def _match_search_container(node: Dict[str, Any]) -> bool:
    tag = (node.get("tag") or "").lower()
    attrs = node.get("attrs") or {}
    role = (attrs.get("role") or "").lower()
    class_attr = (attrs.get("class") or "").lower()
    id_attr = (attrs.get("id") or "").lower()
    if role == "search":
        return True
    keywords = ["search", "lookup"]
    return any(keyword in class_attr or keyword in id_attr for keyword in keywords)


def _match_input(node: Dict[str, Any]) -> bool:
    tag = (node.get("tag") or "").lower()
    if tag in {"input", "textarea"}:
        return True
    attrs = node.get("attrs") or {}
    role = (attrs.get("role") or "").lower()
    return role in {"textbox", "combobox"}


def _match_button(node: Dict[str, Any]) -> bool:
    tag = (node.get("tag") or "").lower()
    if tag == "button":
        return True
    attrs = node.get("attrs") or {}
    role = (attrs.get("role") or "").lower()
    return role in {"button", "link"} and tag in {"a", "div", "span"}


def _build_selector_path(node: Dict[str, Any]) -> Optional[str]:
    path = node.get("path")
    if isinstance(path, str) and path:
        return path
    attrs = node.get("attrs") or {}
    tag = node.get("tag")
    if not isinstance(tag, str):
        return None
    selector = tag
    node_id = attrs.get("id")
    class_attr = attrs.get("class")
    if isinstance(node_id, str) and node_id:
        selector += f"#{node_id}"
    elif isinstance(class_attr, str) and class_attr:
        first_class = class_attr.strip().split()[0]
        selector += f".{first_class}"
    else:
        role = attrs.get("role")
        if isinstance(role, str) and role:
            selector += f"[role='{role}']"
    return selector


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()

    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.debug)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = SITE_PROFILES_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("启动标定 CLI，URL=%s", args.url)

    options = FetchOptions(
        wait_for=args.wait_for,
        timeout_ms=args.timeout,
        include_screenshot=args.include_screenshot,
    )
    try:
        fetched = fetch_page(
            args.url,
            options=options,
            output_dir=run_dir,
            headless=not args.no_headless,
            max_depth=args.max_depth,
            max_nodes=args.max_nodes,
        )
    except Exception as exc:  # pragma: no cover - 调用 Playwright 产生的具体异常依赖环境
        LOGGER.error("页面抓取失败: %s", exc)
        return 1

    stats = fetched.stats or {}
    actual_depth = stats.get("max_depth", "?")
    actual_nodes = stats.get("node_count", "?")
    print(f"DOM 抽取：深度限制 {args.max_depth} / 实际 {actual_depth}；"
          f" 节点限制 {args.max_nodes} / 实际 {actual_nodes}")

    dom_summary, refine_logs = refine_dom_summary(
        fetched.dom_summary,
        interactive=args.interactive,
    )
    fetched.dom_summary = dom_summary
    if refine_logs:
        for entry in refine_logs:
            LOGGER.info("DOM 调整: %s", entry)

    debug_dir = run_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    if args.interactive:
        refined_snapshot = debug_dir / "dom_summary.refined.json"
        refined_snapshot.write_text(
            json.dumps(fetched.dom_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    is_detail_page = _ask_detail_page()

    detail_label = _derive_detail_page_label(fetched.url, args.site_name) if is_detail_page else None

    annotator = LLMAnnotator()
    request = _annotate(
        fetched,
        args,
        is_detail_page=is_detail_page,
        detail_label=detail_label,
    )
    try:
        annotated_page = annotator.annotate(request)
    except Exception as exc:
        LOGGER.error("LLM 标定失败: %s", exc)
        return 1

    enhancement_logs = _enhance_annotations(annotated_page, fetched)
    for log in enhancement_logs:
        LOGGER.info("标定增强: %s", log)

    if is_detail_page:
        original_name = annotated_page.page_name
        desired_name = request.detail_label or _abstract_detail_page_name(original_name, fetched.title)
        if desired_name != original_name:
            LOGGER.info("详情页名称已抽象: %s -> %s", original_name, desired_name)
            annotated_page.page_name = desired_name

    LOGGER.info("LLM 生成页面标定：id=%s, 别名数=%s", annotated_page.page_id, len(annotated_page.aliases))
    if annotated_page.warnings:
        for warn in annotated_page.warnings:
            LOGGER.warning("LLM 警告: %s", warn)

    if args.dry_run:
        print(json.dumps(_single_page_profile(annotated_page), ensure_ascii=False, indent=2))
        LOGGER.info("dry-run 模式，不写入任何文件")
        return 0

    written_files = []

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _single_page_profile(annotated_page)
        if args.site_name or args.base_url:
            site_section: Dict[str, object] = {}
            if args.site_name:
                site_section["name"] = args.site_name
            if args.base_url:
                site_section["base_url"] = args.base_url
            payload["site"] = site_section
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written_files.append(output_path)

    aggregate_path: Path | None = None
    if args.append_to:
        aggregate_path = Path(args.append_to)
    else:
        if not args.output:
            slug = _slug_from_url(args.url)
            aggregate_path = run_dir / f"{slug}.json"

    if aggregate_path is not None:
        try:
            merge_result = merge_page_into_profile(
                annotated_page,
                output_path=aggregate_path,
                site_name=args.site_name,
            )
        except Exception as exc:
            LOGGER.error("写入/合并 profile 失败: %s", exc)
            return 1
        written_files.append(merge_result.output_path)
        LOGGER.info(
            "profile 已更新: %s (page=%s 新文件=%s)",
            merge_result.output_path,
            merge_result.page_id,
            merge_result.created_new_file,
        )

    print("生成完成：")
    print(f"  页面 ID: {annotated_page.page_id}")
    print(f"  别名数量: {len(annotated_page.aliases)}")
    if annotated_page.warnings:
        print("  警告:")
        for warn in annotated_page.warnings:
            print(f"    - {warn}")
    if written_files:
        print("  写入文件:")
        for path in written_files:
            print(f"    - {path}")
    else:
        print("  本次未写入文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())
