"""
测试需求数据结构和类型定义
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime

class TestType(Enum):
    """测试类型枚举"""
    FUNCTIONAL = "functional"          # 功能测试
    UI = "ui"                         # UI测试
    NAVIGATION = "navigation"         # 导航测试
    CONTENT = "content"              # 内容测试
    PERFORMANCE = "performance"       # 性能测试
    ACCESSIBILITY = "accessibility"  # 可访问性测试
    SECURITY = "security"            # 安全测试
    REGRESSION = "regression"        # 回归测试

class AssertionType(Enum):
    """断言类型枚举"""
    ELEMENT_EXISTS = "element_exists"           # 元素存在
    ELEMENT_NOT_EXISTS = "element_not_exists"   # 元素不存在
    TEXT_EQUALS = "text_equals"                 # 文本相等
    TEXT_CONTAINS = "text_contains"             # 文本包含
    URL_EQUALS = "url_equals"                   # URL相等
    URL_CONTAINS = "url_contains"               # URL包含
    PAGE_TITLE = "page_title"                   # 页面标题
    ELEMENT_COUNT = "element_count"             # 元素数量
    ELEMENT_VISIBLE = "element_visible"         # 元素可见
    ELEMENT_ENABLED = "element_enabled"         # 元素可用

class TestResult(Enum):
    """测试结果枚举"""
    PASSED = "passed"           # 通过
    FAILED = "failed"           # 失败
    ERROR = "error"             # 错误（执行失败）
    SKIPPED = "skipped"         # 跳过
    TIMEOUT = "timeout"         # 超时

@dataclass
class Assertion:
    """断言定义"""
    type: AssertionType
    target: str                 # 断言目标（选择器、文本等）
    expected: Any               # 期望值
    actual: Optional[Any] = None  # 实际值（执行后填充）
    passed: Optional[bool] = None  # 是否通过（执行后填充）
    error_message: Optional[str] = None  # 错误信息

@dataclass
class TestStep:
    """测试步骤"""
    id: str
    description: str
    action: str                 # 操作描述
    expected_result: str        # 期望结果
    assertions: List[Assertion] = None
    executed: bool = False
    result: TestResult = TestResult.SKIPPED
    execution_time: Optional[float] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.assertions is None:
            self.assertions = []

@dataclass
class TestCase:
    """测试用例"""
    id: str
    title: str
    description: str
    test_type: TestType
    priority: str = "medium"    # 优先级：high, medium, low
    tags: List[str] = None
    preconditions: List[str] = None
    steps: List[TestStep] = None
    setup_actions: List[str] = None
    teardown_actions: List[str] = None
    timeout: int = 300          # 超时时间（秒）
    retry_count: int = 3        # 重试次数

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.preconditions is None:
            self.preconditions = []
        if self.steps is None:
            self.steps = []
        if self.setup_actions is None:
            self.setup_actions = []
        if self.teardown_actions is None:
            self.teardown_actions = []

@dataclass
class TestExecution:
    """测试执行记录"""
    test_case: TestCase
    execution_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    result: TestResult = TestResult.SKIPPED
    steps_results: List[TestResult] = None
    total_execution_time: Optional[float] = None
    browser_logs: List[str] = None
    screenshots: List[str] = None
    error_details: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.steps_results is None:
            self.steps_results = []
        if self.browser_logs is None:
            self.browser_logs = []
        if self.screenshots is None:
            self.screenshots = []

@dataclass
class TestSuite:
    """测试套件"""
    name: str
    description: str
    test_cases: List[TestCase]
    created_at: datetime
    updated_at: datetime
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

@dataclass
class TestReport:
    """测试报告"""
    test_suite: TestSuite
    executions: List[TestExecution]
    generated_at: datetime
    summary: Dict[str, Any]

    def get_summary(self) -> Dict[str, Any]:
        """获取测试摘要统计"""
        total = len(self.executions)
        passed = sum(1 for e in self.executions if e.result == TestResult.PASSED)
        failed = sum(1 for e in self.executions if e.result == TestResult.FAILED)
        error = sum(1 for e in self.executions if e.result == TestResult.ERROR)
        skipped = sum(1 for e in self.executions if e.result == TestResult.SKIPPED)
        timeout = sum(1 for e in self.executions if e.result == TestResult.TIMEOUT)

        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "error": error,
            "skipped": skipped,
            "timeout": timeout,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
            "execution_time": sum(e.total_execution_time or 0 for e in self.executions)
        }