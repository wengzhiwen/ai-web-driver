"""Placeholder detection, extraction, translation, and replacement."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .models import PlaceholderMatch, ReplacementError, ReplacementStats

PLACEHOLDER_PATTERN = re.compile(r's_([a-zA-Z_][a-zA-Z0-9_]*)(?:\*(\d+))?')

GENDER_TRANSLATION_MAP = {
    'm': '男',
    'f': '女',
    'm,f': '通用',
}


class PlaceholderProcessor:
    """Handles placeholder detection, extraction, translation, and replacement."""

    @staticmethod
    def find_all_placeholders(text: str) -> List[PlaceholderMatch]:
        """Find all placeholders in a text string.

        Args:
            text: The text to search for placeholders.

        Returns:
            List of PlaceholderMatch objects found in the text.
        """
        if not isinstance(text, str):
            return []

        matches = []
        for match in PLACEHOLDER_PATTERN.finditer(text):
            field_name = match.group(1)
            multiplier_str = match.group(2)
            multiplier = int(multiplier_str) if multiplier_str else None
            full_placeholder = match.group(0)

            is_gender = field_name == 'gender'

            matches.append(PlaceholderMatch(
                placeholder=full_placeholder,
                field_name=field_name,
                multiplier=multiplier,
                is_gender_translation=is_gender,
            ))

        return matches

    @staticmethod
    def extract_unique_fields(placeholders: List[PlaceholderMatch]) -> Dict[str, List[PlaceholderMatch]]:
        """Group placeholders by field name.

        Args:
            placeholders: List of PlaceholderMatch objects.

        Returns:
            Dictionary mapping field names to their PlaceholderMatch instances.
        """
        fields: Dict[str, List[PlaceholderMatch]] = {}
        for placeholder in placeholders:
            if placeholder.field_name not in fields:
                fields[placeholder.field_name] = []
            fields[placeholder.field_name].append(placeholder)
        return fields

    @staticmethod
    def translate_gender(value: str) -> str:
        """Translate gender value.

        Args:
            value: The gender value ('m', 'f', or 'm,f').

        Returns:
            Translated gender string.

        Raises:
            ValueError: If the gender value is not recognized.
        """
        if value not in GENDER_TRANSLATION_MAP:
            raise ValueError(f'未知的性别值: {value}')
        return GENDER_TRANSLATION_MAP[value]

    @staticmethod
    def apply_expression(base_value: str, multiplier: int) -> str:
        """Apply expression (multiplication) to a value.

        Args:
            base_value: The base value (should be numeric).
            multiplier: The multiplier to apply.

        Returns:
            The result as a string.

        Raises:
            ValueError: If base_value is not numeric.
        """
        try:
            num = float(base_value)
            result = num * multiplier
            if result == int(result):
                return str(int(result))
            return str(result)
        except ValueError as e:
            raise ValueError(f'无法计算表达式: {base_value} * {multiplier}') from e

    @staticmethod
    def get_replacement_value(
        placeholder: PlaceholderMatch,
        data: Dict[str, Any],
        stats: ReplacementStats,
        data_index: int,
    ) -> Optional[str]:
        """Get the replacement value for a placeholder.

        Args:
            placeholder: The PlaceholderMatch object.
            data: The data dictionary.
            stats: ReplacementStats to record errors.
            data_index: Index of the data item (for error reporting).

        Returns:
            The replacement value, or None if there's an error.
        """
        # 尝试不带 s_ 前缀的字段名，然后尝试带 s_ 前缀的
        field_candidates = [
            placeholder.field_name,
            f's_{placeholder.field_name}',
        ]

        field_value = None
        actual_field = None
        for field in field_candidates:
            if field in data:
                field_value = data[field]
                actual_field = field
                break

        if field_value is None:
            error = ReplacementError(
                error_type='missing_field',
                placeholder=placeholder.placeholder,
                field_name=placeholder.field_name,
                data_index=data_index,
                message=f'数据项中缺失字段: {placeholder.field_name} (尝试过: {", ".join(field_candidates)})',
            )
            stats.errors.append(error)
            return None

        base_value = field_value
        if not isinstance(base_value, str):
            base_value = str(base_value)

        if placeholder.is_gender_translation:
            try:
                return PlaceholderProcessor.translate_gender(base_value)
            except ValueError as e:
                error = ReplacementError(
                    error_type='translation_error',
                    placeholder=placeholder.placeholder,
                    field_name=placeholder.field_name,
                    data_index=data_index,
                    message=str(e),
                )
                stats.errors.append(error)
                return None

        if placeholder.is_expression():
            try:
                return PlaceholderProcessor.apply_expression(base_value, placeholder.multiplier)
            except ValueError as e:
                error = ReplacementError(
                    error_type='expression_error',
                    placeholder=placeholder.placeholder,
                    field_name=placeholder.field_name,
                    data_index=data_index,
                    message=str(e),
                )
                stats.errors.append(error)
                return None

        return base_value

    @staticmethod
    def replace_placeholders_in_text(
        text: str,
        data: Dict[str, Any],
        stats: ReplacementStats,
        data_index: int,
    ) -> Tuple[str, bool]:
        """Replace all placeholders in a text string with values from data.

        Args:
            text: The text containing placeholders.
            data: The data dictionary.
            stats: ReplacementStats to record errors and successes.
            data_index: Index of the data item (for error reporting).

        Returns:
            Tuple of (replaced_text, success_flag).
            success_flag indicates if all replacements succeeded.
        """
        if not isinstance(text, str):
            return text, True

        result = text
        placeholders = PlaceholderProcessor.find_all_placeholders(text)

        if not placeholders:
            return result, True

        all_success = True
        for placeholder in placeholders:
            replacement = PlaceholderProcessor.get_replacement_value(placeholder, data, stats, data_index)

            if replacement is None:
                all_success = False
            else:
                result = result.replace(placeholder.placeholder, replacement)

        remaining_placeholders = PlaceholderProcessor.find_all_placeholders(result)
        if remaining_placeholders:
            for p in remaining_placeholders:
                error = ReplacementError(
                    error_type='unreplaced_placeholder',
                    placeholder=p.placeholder,
                    field_name=p.field_name,
                    data_index=data_index,
                    message=f'替换后仍存在无法处理的占位符: {p.placeholder}',
                )
                stats.errors.append(error)
            all_success = False

        return result, all_success

    @staticmethod
    def replace_placeholders_in_dict(
        obj: Any,
        data: Dict[str, Any],
        stats: ReplacementStats,
        data_index: int,
    ) -> Tuple[Any, bool]:
        """Recursively replace placeholders in a dictionary/list/string.

        Args:
            obj: The object to process (can be dict, list, string, or other).
            data: The data dictionary.
            stats: ReplacementStats to record errors and successes.
            data_index: Index of the data item (for error reporting).

        Returns:
            Tuple of (processed_object, success_flag).
        """
        if isinstance(obj, dict):
            result = {}
            all_success = True
            for key, value in obj.items():
                processed, success = PlaceholderProcessor.replace_placeholders_in_dict(value, data, stats, data_index)
                result[key] = processed
                all_success = all_success and success
            return result, all_success

        if isinstance(obj, list):
            result = []
            all_success = True
            for item in obj:
                processed, success = PlaceholderProcessor.replace_placeholders_in_dict(item, data, stats, data_index)
                result.append(processed)
                all_success = all_success and success
            return result, all_success

        if isinstance(obj, str):
            return PlaceholderProcessor.replace_placeholders_in_text(obj, data, stats, data_index)

        return obj, True
