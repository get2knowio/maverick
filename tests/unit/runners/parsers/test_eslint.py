"""Tests for ESLint JSON parser."""

from __future__ import annotations

from maverick.runners.parsers.eslint import ESLintJSONParser


class TestESLintJSONParser:
    def test_can_parse_eslint_json(self):
        """Verify can_parse() returns True for valid ESLint JSON output."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'x' is defined but never used",
        "line": 1,
        "column": 7
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        assert parser.can_parse(output) is True

    def test_can_parse_empty_results(self):
        """Verify can_parse() returns True for empty ESLint results array."""
        output = "[]"
        parser = ESLintJSONParser()
        assert parser.can_parse(output) is True

    def test_cannot_parse_non_json(self):
        """Verify can_parse() returns False for plain text output."""
        output = "This is not JSON output"
        parser = ESLintJSONParser()
        assert parser.can_parse(output) is False

    def test_cannot_parse_invalid_json(self):
        """Verify can_parse() returns False for malformed JSON."""
        output = '{"invalid": json,}'
        parser = ESLintJSONParser()
        assert parser.can_parse(output) is False

    def test_cannot_parse_wrong_format(self):
        """Verify can_parse() returns False for JSON without filePath keys."""
        output = '[{"foo": "bar"}]'
        parser = ESLintJSONParser()
        assert parser.can_parse(output) is False

    def test_parse_single_error(self):
        """Verify parsing a single ESLint error with all fields."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'x' is defined but never used",
        "line": 10,
        "column": 7
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file == "/path/to/file.js"
        assert errors[0].line == 10
        assert errors[0].column == 7
        assert errors[0].message == "'x' is defined but never used"
        assert errors[0].severity == "error"
        assert errors[0].code == "no-unused-vars"

    def test_parse_warning(self):
        """Verify warnings are parsed with correct severity."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-console",
        "severity": 1,
        "message": "Unexpected console statement",
        "line": 5,
        "column": 3
      }
    ],
    "errorCount": 0,
    "warningCount": 1
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].severity == "warning"
        assert errors[0].code == "no-console"
        assert errors[0].line == 5

    def test_parse_multiple_messages_in_file(self):
        """Verify multiple errors in a single file are all parsed."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'x' is defined but never used",
        "line": 10,
        "column": 7
      },
      {
        "ruleId": "no-console",
        "severity": 1,
        "message": "Unexpected console statement",
        "line": 15,
        "column": 3
      },
      {
        "ruleId": "semi",
        "severity": 2,
        "message": "Missing semicolon",
        "line": 20,
        "column": 15
      }
    ],
    "errorCount": 2,
    "warningCount": 1
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 3
        assert errors[0].line == 10
        assert errors[0].severity == "error"
        assert errors[1].line == 15
        assert errors[1].severity == "warning"
        assert errors[2].line == 20
        assert errors[2].severity == "error"

    def test_parse_multiple_files(self):
        """Verify errors from multiple files are all parsed."""
        output = """[
  {
    "filePath": "/path/to/file1.js",
    "messages": [
      {
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'x' is defined but never used",
        "line": 10,
        "column": 7
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  },
  {
    "filePath": "/path/to/file2.js",
    "messages": [
      {
        "ruleId": "no-console",
        "severity": 1,
        "message": "Unexpected console statement",
        "line": 5,
        "column": 3
      }
    ],
    "errorCount": 0,
    "warningCount": 1
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 2
        assert errors[0].file == "/path/to/file1.js"
        assert errors[0].severity == "error"
        assert errors[1].file == "/path/to/file2.js"
        assert errors[1].severity == "warning"

    def test_parse_empty_results(self):
        """Verify empty results array returns empty list."""
        output = "[]"
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 0
        assert errors == []

    def test_parse_file_with_no_messages(self):
        """Verify files with empty messages array produce no errors."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [],
    "errorCount": 0,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 0

    def test_parse_with_rule_id(self):
        """Verify rule IDs are captured correctly."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-undef",
        "severity": 2,
        "message": "'someVar' is not defined",
        "line": 1,
        "column": 1
      },
      {
        "ruleId": "quotes",
        "severity": 2,
        "message": "Strings must use single quotes",
        "line": 2,
        "column": 10
      }
    ],
    "errorCount": 2,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 2
        assert errors[0].code == "no-undef"
        assert errors[1].code == "quotes"

    def test_parse_without_column(self):
        """Verify parsing works when column is missing."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'x' is defined but never used",
        "line": 10
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].column is None
        assert errors[0].line == 10

    def test_parse_without_rule_id(self):
        """Verify parsing works when ruleId is missing."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "severity": 2,
        "message": "Parsing error",
        "line": 1,
        "column": 1
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].code is None
        assert errors[0].message == "Parsing error"

    def test_parse_invalid_json_returns_empty_list(self):
        """Verify parse() gracefully handles invalid JSON."""
        output = "This is not valid JSON"
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert errors == []

    def test_parse_missing_line_defaults_to_one(self):
        """Verify missing line number defaults to 1."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'x' is defined but never used"
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].line == 1

    def test_parse_missing_message_defaults(self):
        """Verify missing message field gets default value."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "some-rule",
        "severity": 2,
        "line": 5
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].message == "Unknown error"

    def test_parse_severity_other_than_1_or_2(self):
        """Verify non-standard severity values default to warning."""
        output = """[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "some-rule",
        "severity": 0,
        "message": "Some message",
        "line": 5
      }
    ],
    "errorCount": 0,
    "warningCount": 0
  }
]"""
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].severity == "warning"

    def test_parse_with_whitespace(self):
        """Verify parsing works with extra whitespace."""
        output = """

[
  {
    "filePath": "/path/to/file.js",
    "messages": [
      {
        "ruleId": "no-unused-vars",
        "severity": 2,
        "message": "'x' is defined but never used",
        "line": 1,
        "column": 7
      }
    ],
    "errorCount": 1,
    "warningCount": 0
  }
]

        """
        parser = ESLintJSONParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file == "/path/to/file.js"
