"""Data-driven compilation pipeline for ActionPlan generation."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import DataDrivenResult, DataItem, DataSet, ReplacementStats
from .placeholder_processor import PlaceholderProcessor

# pylint: disable=too-many-arguments,too-few-public-methods,too-many-positional-arguments

logger = logging.getLogger(__name__)


class DataSetLoader:
    """Handles loading and parsing of data sets."""

    @staticmethod
    def load_from_file(filepath: Path) -> Dict[str, object]:
        """Load dataset from a JSON file.

        Args:
            filepath: Path to the dataset JSON file.

        Returns:
            Parsed JSON data.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def extract_category(raw_data: Dict[str, object], category: str) -> DataSet:
        """Extract a specific category from dataset.

        Args:
            raw_data: The parsed dataset JSON.
            category: The category key to extract.

        Returns:
            DataSet object with the extracted items.

        Raises:
            KeyError: If the category is not found in the data.
            ValueError: If the category structure is invalid.
        """
        if 'data' not in raw_data or 'categories' not in raw_data['data']:
            raise ValueError('数据集格式不符合预期: 缺少 data.categories 字段')

        categories = raw_data['data']['categories']
        target_category = None

        for cat in categories:
            if cat.get('category_key') == category:
                target_category = cat
                break

        if target_category is None:
            raise KeyError(f'未找到类别: {category}')

        items_raw = target_category.get('items', [])
        items = [DataItem(index=i, data=item) for i, item in enumerate(items_raw)]

        return DataSet(category=category, items=items, raw=raw_data)


class DataDrivenCompiler:
    """Compiles ActionPlan templates into data-driven test cases."""

    def __init__(self):
        self.placeholder_processor = PlaceholderProcessor()

    def compile(
        self,
        template_plan: Dict[str, object],
        test_id_base: str,
        base_url: str,
        dataset: DataSet,
    ) -> DataDrivenResult:
        """Compile template ActionPlan into data-driven test cases.

        Args:
            template_plan: The template ActionPlan with placeholders.
            test_id_base: Base test ID for generating unique IDs.
            base_url: The base URL for tests.
            dataset: DataSet with items to drive compilation.

        Returns:
            DataDrivenResult containing all generated cases and statistics.
        """
        result = DataDrivenResult(
            template_plan=template_plan,
            test_id_base=test_id_base,
            base_url=base_url,
        )

        stats = ReplacementStats(total_items=len(dataset.items))

        for data_item in dataset.items:
            case_plan, success = self._compile_single_case(template_plan, test_id_base, data_item.index, data_item.data, stats)

            if success:
                result.cases.append(case_plan)
                stats.successful_items += 1
            else:
                stats.failed_items += 1

        result.stats = stats
        return result

    def _compile_single_case(
        self,
        template_plan: Dict[str, object],
        test_id_base: str,
        data_index: int,
        data: Dict[str, Any],
        stats: ReplacementStats,
    ) -> tuple[Optional[Dict[str, object]], bool]:
        """Compile a single test case from template and data item.

        Args:
            template_plan: The template ActionPlan.
            test_id_base: Base test ID.
            data_index: Index of the data item.
            data: The data dictionary for this item.
            stats: ReplacementStats to accumulate errors.

        Returns:
            Tuple of (compiled_case, success_flag).
        """
        plan_copy = json.loads(json.dumps(template_plan))

        replaced_plan, success = PlaceholderProcessor.replace_placeholders_in_dict(
            plan_copy, data, stats, data_index
        )

        if success and isinstance(replaced_plan, dict):
            self._update_meta_info(replaced_plan, test_id_base, data_index)

        return replaced_plan if success else None, success

    @staticmethod
    def _update_meta_info(plan: Dict[str, object], test_id_base: str, data_index: int) -> None:
        """Update meta information in the compiled plan.

        Args:
            plan: The compiled ActionPlan.
            test_id_base: Base test ID.
            data_index: Index of the data item.
        """
        if 'meta' not in plan:
            plan['meta'] = {}

        meta = plan['meta']
        if not isinstance(meta, dict):
            meta = {}
            plan['meta'] = meta

        test_id = meta.get('testId', test_id_base)
        meta['testId'] = f'{test_id}_{data_index + 1:03d}'
        meta['dataSource'] = f'dataset#{data_index}'


class CompilationOutputWriter:
    """Handles writing compilation results to disk."""

    @staticmethod
    def write_results(
        result: DataDrivenResult,
        output_root: Path,
        plan_name: Optional[str] = None,
        case_name: Optional[str] = None,
    ) -> tuple[Path, Path]:
        """Write compilation results to disk.

        Args:
            result: The DataDrivenResult object.
            output_root: Root directory for output.
            plan_name: Optional custom plan directory name.
            case_name: Optional custom case name prefix.

        Returns:
            Tuple of (plan_dir, case_dir).
        """
        timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        if plan_name is None:
            plan_name = f'{timestamp}_data_driven_plan'

        plan_dir = output_root / plan_name
        plan_dir.mkdir(parents=True, exist_ok=True)

        case_dir = plan_dir / 'cases'
        case_dir.mkdir(parents=True, exist_ok=True)

        if case_name is None:
            case_name = 'case'

        CompilationOutputWriter._write_template(result.template_plan, plan_dir)
        CompilationOutputWriter._write_stats(result.stats, plan_dir)
        CompilationOutputWriter._write_cases(result.cases, case_dir, case_name)

        result.plan_dir = plan_dir
        result.case_dir = case_dir

        return plan_dir, case_dir

    @staticmethod
    def _write_template(template: Dict[str, object], plan_dir: Path) -> Path:
        """Write template ActionPlan to file.

        Args:
            template: The template ActionPlan.
            plan_dir: Directory to write to.

        Returns:
            Path to written file.
        """
        template_path = plan_dir / 'action_plan_template.json'
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        logger.info(f'模板已保存: {template_path}')
        return template_path

    @staticmethod
    def _write_stats(stats: ReplacementStats, plan_dir: Path) -> Path:
        """Write statistics to file.

        Args:
            stats: The ReplacementStats object.
            plan_dir: Directory to write to.

        Returns:
            Path to written file.
        """
        stats_data = {
            'total_items': stats.total_items,
            'successful_items': stats.successful_items,
            'failed_items': stats.failed_items,
            'error_summary': stats.get_error_summary(),
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }

        stats_path = plan_dir / 'stats.json'
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats_data, f, ensure_ascii=False, indent=2)
        logger.info(f'统计信息已保存: {stats_path}')
        return stats_path

    @staticmethod
    def _write_cases(cases: List[Dict[str, object]], case_dir: Path, case_name: str) -> List[Path]:
        """Write compiled test cases to files.

        Args:
            cases: List of compiled ActionPlans.
            case_dir: Directory to write cases to.
            case_name: Prefix for case filenames.

        Returns:
            List of written file paths.
        """
        written_paths = []
        timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

        for i, case in enumerate(cases):
            filename = f'{case_name}_{i + 1:03d}_{timestamp}.json'
            filepath = case_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(case, f, ensure_ascii=False, indent=2)
            written_paths.append(filepath)

        logger.info(f'共输出 {len(written_paths)} 个测试用例到: {case_dir}')
        return written_paths


class CompilationErrorReporter:
    """Generates detailed error reports."""

    @staticmethod
    def generate_error_report(stats: ReplacementStats) -> Dict[str, object]:
        """Generate a detailed error report.

        Args:
            stats: The ReplacementStats object.

        Returns:
            Dictionary containing error details.
        """
        errors_by_type: Dict[str, List[Dict[str, object]]] = {}

        for error in stats.errors:
            if error.error_type not in errors_by_type:
                errors_by_type[error.error_type] = []

            errors_by_type[error.error_type].append({
                'placeholder': error.placeholder,
                'field_name': error.field_name,
                'data_index': error.data_index,
                'message': error.message,
            })

        return {
            'total_errors': len(stats.errors),
            'by_type': errors_by_type,
            'summary': stats.get_error_summary(),
        }

    @staticmethod
    def write_error_report(stats: ReplacementStats, plan_dir: Path) -> Optional[Path]:
        """Write detailed error report to file.

        Args:
            stats: The ReplacementStats object.
            plan_dir: Directory to write to.

        Returns:
            Path to written file, or None if no errors.
        """
        if not stats.errors:
            return None

        report = CompilationErrorReporter.generate_error_report(stats)
        errors_path = plan_dir / 'errors.json'

        with open(errors_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.warning(f'错误报告已保存: {errors_path}')
        return errors_path

    @staticmethod
    def print_summary(stats: ReplacementStats) -> None:
        """Print a summary of replacement statistics.

        Args:
            stats: The ReplacementStats object.
        """
        print('\n' + '=' * 60)
        print('数据驱动编译统计摘要')
        print('=' * 60)
        print(f'总数据项: {stats.total_items}')
        print(f'成功替换: {stats.successful_items}')
        print(f'失败替换: {stats.failed_items}')

        error_summary = stats.get_error_summary()
        if error_summary:
            print('\n错误统计:')
            for error_type, count in sorted(error_summary.items()):
                print(f'  {error_type}: {count}')
        else:
            print('\n无错误')

        print('=' * 60 + '\n')
