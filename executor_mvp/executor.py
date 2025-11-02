"""Core execution logic for the action plan executor MVP."""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .models import ActionPlan, ActionStep, RunResult, StepResult
from .report_generator import TestReportGenerator


@dataclass
# pylint: disable=too-few-public-methods
class ExecutorSettings:
    """Runtime knobs for the executor."""

    headless: bool = True
    default_timeout_ms: int = 10_000
    output_root: Path = Path("results")
    screenshots: str = "on-failure"  # values: none | on-failure | all
    generate_report: bool = True  # Enable LLM-powered test report generation


class Executor:
    """Runs an ActionPlan using Playwright."""

    def __init__(self, settings: Optional[ExecutorSettings] = None) -> None:
        self.settings = settings or ExecutorSettings()
        self.logger = logging.getLogger("executor_mvp")
        self.logger.setLevel(logging.INFO)
        self.report_generator = TestReportGenerator() if self.settings.generate_report else None

    def run(self, plan: ActionPlan, artifacts_dir: Optional[Path] = None) -> RunResult:
        """执行测试计划
        
        Args:
            plan: 测试计划
            artifacts_dir: 可选的结果目录，如果不提供则自动创建
        
        Returns:
            测试执行结果
        """
        run_id = self._build_run_id(plan.test_id)
        if artifacts_dir is None:
        artifacts_dir = self._prepare_artifacts(run_id)
        else:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
        log_handler = self._attach_run_logger(artifacts_dir / "runner.log")
        result = RunResult(
            run_id=run_id,
            test_id=plan.test_id,
            status="passed",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            artifacts_dir=str(artifacts_dir),
        )

        screenshots_dir = artifacts_dir / "steps"
        screenshots_dir.mkdir(exist_ok=True)

        try:
            with self._playwright_context() as page:
                self.logger.info("Starting plan %s", plan.test_id)
                page.set_default_timeout(self.settings.default_timeout_ms)
                for index, step in enumerate(plan.steps, start=1):
                    step_result = self._run_step(
                        page=page,
                        plan=plan,
                        step=step,
                        index=index,
                        screenshots_dir=screenshots_dir,
                    )
                    result.steps.append(step_result)
                    if step_result.status == "failed":
                        result.status = "failed"
                        break
        except Exception as exc:  # pragma: no cover - guard for unexpected errors
            self.logger.exception("Run crashed with unexpected error")
            result.status = "failed"
            result.error = str(exc)
        finally:
            result.finished_at = datetime.utcnow()
            self._write_run_result(artifacts_dir / "run.json", result)

            # Generate LLM-powered test report if enabled
            if self.report_generator:
                try:
                    self.logger.info("Generating test report...")
                    report_path = artifacts_dir / "test_report.md"
                    self.report_generator.generate_report(plan, result, report_path)
                    self.logger.info("Test report generated at %s", report_path)
                except Exception as exc:
                    self.logger.warning("Failed to generate test report: %s", exc)

            if log_handler:
                self.logger.removeHandler(log_handler)
                log_handler.close()

        return result

    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-statements
    def _run_step(
        self,
        page,
        plan: ActionPlan,
        step: ActionStep,
        index: int,
        screenshots_dir: Path,
    ) -> StepResult:
        step_start = datetime.utcnow()
        self.logger.info("Step %s: %s", index, step.t)
        status = "passed"
        error_message: Optional[str] = None
        screenshot_path: Optional[str] = None
        current_url: Optional[str] = None
        page_title: Optional[str] = None
        dom_size: Optional[int] = None

        try:
            if step.t == "goto":
                self._handle_goto(page, plan, step)
            elif step.t == "fill":
                self._handle_fill(page, step)
            elif step.t == "click":
                self._handle_click(page, step)
            elif step.t == "assert":
                self._handle_assert(page, step)
            else:
                raise ValueError(f"Unsupported step type: {step.t}")
        except Exception as exc:
            # click操作失败时，允许重试1次
            if step.t == "click":
                self.logger.warning("Step %s failed: %s, 等待500ms后重试", index, self._format_error(exc))
                try:
                    page.wait_for_timeout(500)
                    self._handle_click(page, step)
                    self.logger.info("Step %s 重试成功", index)
                    status = "passed"
                except Exception as retry_exc:
                    status = "failed"
                    error_message = f"重试后仍失败: {self._format_error(retry_exc)}"
                    self.logger.warning("Step %s 重试失败: %s", index, error_message)
                    if self._should_capture(step_success=False):
                        screenshot_path = str(screenshots_dir / f"{index:02d}.png")
                        try:
                            page.screenshot(path=screenshot_path, full_page=True)
                        except Exception as screenshot_exc:  # pragma: no cover - best effort
                            self.logger.error("Screenshot capture failed: %s", screenshot_exc)
                            screenshot_path = None
            else:
            status = "failed"
            error_message = self._format_error(exc)
            self.logger.warning("Step %s failed: %s", index, error_message)
            if self._should_capture(step_success=False):
                screenshot_path = str(screenshots_dir / f"{index:02d}.png")
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                except Exception as screenshot_exc:  # pragma: no cover - best effort
                    self.logger.error("Screenshot capture failed: %s", screenshot_exc)
                    screenshot_path = None
        else:
            if self._should_capture(step_success=True):
                screenshot_path = str(screenshots_dir / f"{index:02d}.png")
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                except Exception as screenshot_exc:  # pragma: no cover - best effort
                    self.logger.error("Screenshot capture failed: %s", screenshot_exc)
                    screenshot_path = None
        finally:
            step_end = datetime.utcnow()
            current_url, page_title, dom_size = self._gather_page_context(page)

        return StepResult(
            index=index,
            action=step,
            status=status,
            started_at=step_start,
            finished_at=step_end,
            error=error_message,
            screenshot_path=screenshot_path,
            current_url=current_url,
            page_title=page_title,
            dom_size_bytes=dom_size,
        )

    def _handle_goto(self, page, plan: ActionPlan, step: ActionStep) -> None:
        if not step.url:
            raise ValueError("goto step missing 'url'")
        target = step.url.strip()
        if not target:
            raise ValueError("goto step provided empty url")
        if target.startswith("http://") or target.startswith("https://"):
            final_url = target
        else:
            final_url = urljoin(plan.base_url.rstrip("/"), target)
        self.logger.info("Navigating to %s", final_url)
        page.goto(final_url)

    def _handle_fill(self, page, step: ActionStep) -> None:
        if step.value is None:
            raise ValueError("fill step missing 'value'")
        if not step.selector:
            raise ValueError("fill step missing 'selector'")
        locator = page.locator(step.selector).first
        timeout = self.settings.default_timeout_ms
        locator.wait_for(state="visible", timeout=timeout)
        locator.fill(step.value, timeout=timeout)

    def _handle_click(self, page, step: ActionStep) -> None:
        if not step.selector:
            raise ValueError("click step missing 'selector'")
        locator = page.locator(step.selector)
        timeout = self.settings.default_timeout_ms
        locator.first.click(timeout=timeout)
        # 等待JavaScript事件处理完成
        page.wait_for_timeout(200)

    # pylint: disable=too-many-branches
    def _handle_assert(self, page, step: ActionStep) -> None:
        if not step.kind:
            raise ValueError("assert step missing 'kind'")
        if not step.selector:
            raise ValueError("assert step missing 'selector'")
        locator = page.locator(step.selector)
        first = locator.first
        timeout = self.settings.default_timeout_ms

        if step.kind == "visible":
            first.wait_for(state="visible", timeout=timeout)
        elif step.kind == "text_contains":
            expected = step.value
            if expected is None:
                raise ValueError("text_contains assertion requires 'value'")
            text = first.text_content(timeout=timeout) or ""
            if expected not in text:
                raise AssertionError(f"Expected '{expected}' to be contained in '{text.strip()}'")
        elif step.kind == "text_equals":
            expected = step.value
            if expected is None:
                raise ValueError("text_equals assertion requires 'value'")
            text = first.text_content(timeout=timeout) or ""
            if text.strip() != expected:
                raise AssertionError(f"Expected '{expected}' but got '{text.strip()}'")
        elif step.kind == "count_equals":
            expected = self._parse_expected_count(step.value, "count_equals")
            self._wait_for_count_target(first, timeout, expected)
            actual = locator.count()
            if actual != expected:
                raise AssertionError(f"Expected {expected} elements but found {actual} for selector {step.selector}")
        elif step.kind == "count_at_least":
            expected = self._parse_expected_count(step.value, "count_at_least")
            self._wait_for_count_target(first, timeout, expected)
            actual = locator.count()
            if actual < expected:
                raise AssertionError(f"Expected at least {expected} elements but found {actual} for selector {step.selector}")
        else:
            raise ValueError(f"Unsupported assert kind: {step.kind}")

    @staticmethod
    def _parse_expected_count(raw_value: Optional[str], kind: str) -> int:
        if raw_value is None:
            raise ValueError(f"{kind} assertion requires 'value'")
        if isinstance(raw_value, (int, float)):
            expected = int(raw_value)
        else:
            text = str(raw_value).strip()
            if not text:
                raise ValueError(f"{kind} assertion requires numeric 'value'")
            if not text.isdigit():
                raise ValueError(f"{kind} assertion requires integer 'value', got '{text}'")
            expected = int(text)
        if expected < 0:
            raise ValueError(f"{kind} assertion requires non-negative 'value'")
        return expected

    @staticmethod
    def _wait_for_count_target(locator, timeout: int, expected: int) -> None:
        if expected <= 0:
            return
        locator.wait_for(state="visible", timeout=timeout)

    def _prepare_artifacts(self, run_id: str) -> Path:
        root = self.settings.output_root
        root.mkdir(exist_ok=True)
        run_dir = root / run_id
        run_dir.mkdir(exist_ok=True)
        return run_dir

    def _write_run_result(self, path: Path, result: RunResult) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(result.to_dict(), handle, ensure_ascii=False, indent=2)

    def _should_capture(self, step_success: bool) -> bool:
        if self.settings.screenshots == "none":
            return False
        if self.settings.screenshots == "all":
            return True
        return not step_success

    def _gather_page_context(self, page) -> tuple[Optional[str], Optional[str], Optional[int]]:
        current_url: Optional[str] = None
        page_title: Optional[str] = None
        dom_size: Optional[int] = None

        try:
            current_url = page.url
        except Exception as exc:  # pragma: no cover - observational guard
            self.logger.debug("Failed to read page url: %s", exc)
        try:
            page_title = page.title()
        except Exception as exc:  # pragma: no cover - observational guard
            self.logger.debug("Failed to read page title: %s", exc)
        try:
            content = page.content()
        except Exception as exc:  # pragma: no cover - observational guard
            self.logger.debug("Failed to read page content: %s", exc)
        else:
            dom_size = len(content.encode("utf-8"))

        return current_url, page_title, dom_size

    @staticmethod
    def _build_run_id(test_id: str) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        sanitized = test_id.replace(" ", "-")
        return f"{timestamp}_{sanitized}"

    @staticmethod
    def _format_error(exc: Exception) -> str:
        if isinstance(exc, PlaywrightTimeoutError):  # pragma: no cover - depends on runtime
            return "验证失败：未能找到指定的DOM元素"
        return str(exc)

    @contextmanager
    def _playwright_context(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.settings.headless)
            context = browser.new_context()
            page = context.new_page()
            try:
                yield page
            finally:
                context.close()
                browser.close()

    def _attach_run_logger(self, log_path: Path) -> Optional[logging.Handler]:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        return handler
