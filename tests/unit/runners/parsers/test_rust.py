"""Tests for Rust compiler error parser."""

from __future__ import annotations

from maverick.runners.parsers.rust import RustCompilerParser


class TestRustCompilerParser:
    def test_can_parse_rust_error(self):
        """Verify can_parse() returns True for Rust compiler output."""
        output = """error[E0308]: mismatched types
 --> src/main.rs:12:9
  |
12 |     let x: i32 = "hello";
  |            ---   ^^^^^^^ expected `i32`, found `&str`"""
        parser = RustCompilerParser()
        assert parser.can_parse(output) is True

    def test_can_parse_rust_error_without_code(self):
        """Verify can_parse() returns True for errors without error codes."""
        output = """error: could not compile `myproject`
 --> src/lib.rs:10:5
  |
10 |     invalid syntax here
  |     ^^^^^^^^^^^^^^^^^^"""
        parser = RustCompilerParser()
        assert parser.can_parse(output) is True

    def test_can_parse_rust_warning(self):
        """Verify can_parse() returns True for Rust warnings."""
        output = """warning: unused variable: `x`
 --> src/main.rs:5:9
  |
5 |     let x = 42;
  |         ^ help: if this is intentional, prefix it with an underscore: `_x`"""
        parser = RustCompilerParser()
        assert parser.can_parse(output) is True

    def test_cannot_parse_non_rust(self):
        """Verify can_parse() returns False for non-Rust output."""
        outputs = [
            "Traceback (most recent call last):",
            "fatal: not a git repository",
            "npm ERR! missing script: build",
            "some random text with no error markers",
            "BUILD SUCCESSFUL in 2s",
            "Tests passed: 10, failed: 0",
        ]
        parser = RustCompilerParser()
        for output in outputs:
            assert parser.can_parse(output) is False, f"Should not parse: {output}"

    def test_parse_error_with_location(self):
        """Verify parsing errors with file:line:col format."""
        output = """error[E0308]: mismatched types
 --> src/main.rs:12:9
  |
12 |     let x: i32 = "hello";
  |            ---   ^^^^^^^ expected `i32`, found `&str`
  |            |
  |            expected due to this"""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file == "src/main.rs"
        assert errors[0].line == 12
        assert errors[0].column == 9
        assert errors[0].message == "mismatched types"
        assert errors[0].severity == "error"
        assert errors[0].code == "E0308"

    def test_parse_error_without_code(self):
        """Verify parsing errors without error codes."""
        output = """error: aborting due to previous error
 --> src/lib.rs:10:5
  |
10 |     invalid syntax
  |     ^^^^^^^^^^^^^^"""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file == "src/lib.rs"
        assert errors[0].line == 10
        assert errors[0].column == 5
        assert errors[0].message == "aborting due to previous error"
        assert errors[0].severity == "error"
        assert errors[0].code is None

    def test_parse_warning(self):
        """Verify warnings are parsed correctly."""
        output = """warning: unused variable: `x`
 --> src/main.rs:5:9
  |
5 |     let x = 42;
  |         ^ help: if this is intentional, prefix it with an underscore: `_x`"""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file == "src/main.rs"
        assert errors[0].line == 5
        assert errors[0].column == 9
        assert errors[0].message == "unused variable: `x`"
        assert errors[0].severity == "warning"
        assert errors[0].code is None

    def test_parse_warning_with_code(self):
        """Verify warnings with error codes are parsed correctly."""
        output = """warning[E0612]: cannot find value `foo` in this scope
 --> src/lib.rs:20:5
  |
20 |     foo
  |     ^^^ not found in this scope"""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file == "src/lib.rs"
        assert errors[0].line == 20
        assert errors[0].column == 5
        assert errors[0].severity == "warning"
        assert errors[0].code == "E0612"

    def test_parse_multiple_errors(self):
        """Verify multiple errors in single output."""
        output = """error[E0308]: mismatched types
 --> src/main.rs:12:9
  |
12 |     let x: i32 = "hello";
  |            ---   ^^^^^^^ expected `i32`, found `&str`

error[E0425]: cannot find value `y` in this scope
 --> src/main.rs:15:13
  |
15 |     println!("{}", y);
  |             ^ not found in this scope

warning: unused variable: `z`
 --> src/main.rs:8:9
  |
8 |     let z = 100;
  |         ^ help: if this is intentional, prefix it with an underscore: `_z`"""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        assert len(errors) == 3

        # First error
        assert errors[0].file == "src/main.rs"
        assert errors[0].line == 12
        assert errors[0].column == 9
        assert errors[0].severity == "error"
        assert errors[0].code == "E0308"

        # Second error
        assert errors[1].file == "src/main.rs"
        assert errors[1].line == 15
        assert errors[1].column == 13
        assert errors[1].severity == "error"
        assert errors[1].code == "E0425"

        # Warning
        assert errors[2].file == "src/main.rs"
        assert errors[2].line == 8
        assert errors[2].column == 9
        assert errors[2].severity == "warning"
        assert errors[2].code is None

    def test_parse_error_code(self):
        """Verify error codes (E0308 etc) are captured."""
        test_cases = [
            ("error[E0308]:", "E0308"),
            ("error[E0425]:", "E0425"),
            ("error[E0599]:", "E0599"),
            ("error[E1234]:", "E1234"),
        ]

        for error_marker, expected_code in test_cases:
            output = f"""{error_marker} some error message
 --> src/test.rs:1:1
  |
1 | test
  | ^^^^"""
            parser = RustCompilerParser()
            errors = parser.parse(output)

            assert len(errors) == 1
            expected = expected_code
            actual = errors[0].code
            assert actual == expected, f"Expected {expected} for {error_marker}"

    def test_empty_output(self):
        """Verify empty output returns empty list."""
        parser = RustCompilerParser()
        errors = parser.parse("")
        assert errors == []

    def test_parse_output_with_no_errors(self):
        """Verify output without errors returns empty list."""
        output = """   Compiling myproject v0.1.0 (/path/to/project)
    Finished dev [unoptimized + debuginfo] target(s) in 0.50s"""
        parser = RustCompilerParser()
        errors = parser.parse(output)
        assert errors == []

    def test_parse_cargo_error(self):
        """Verify cargo build errors are parsed correctly."""
        output = """   Compiling myproject v0.1.0 (/path/to/project)
error[E0433]: failed to resolve: use of undeclared crate or module `unknown`
 --> src/lib.rs:1:5
  |
1 | use unknown::Module;
  |     ^^^^^^^ use of undeclared crate or module `unknown`

error: aborting due to previous error
 --> src/lib.rs:1:5

For more information about this error, try `rustc --explain E0433`."""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        # Should parse both errors (the main one and the aborting message)
        assert len(errors) == 2
        assert errors[0].code == "E0433"
        assert errors[0].file == "src/lib.rs"
        assert errors[0].line == 1
        assert errors[0].column == 5

    def test_parse_error_with_relative_and_absolute_paths(self):
        """Verify both relative and absolute file paths are parsed."""
        test_cases = [
            ("src/main.rs", "src/main.rs"),
            ("lib/utils/helper.rs", "lib/utils/helper.rs"),
            ("/home/user/project/src/main.rs", "/home/user/project/src/main.rs"),
            ("./src/main.rs", "./src/main.rs"),
        ]

        for input_path, expected_path in test_cases:
            output = f"""error[E0308]: test error
 --> {input_path}:10:5
  |
10 | test
  | ^^^^"""
            parser = RustCompilerParser()
            errors = parser.parse(output)

            assert len(errors) == 1
            assert errors[0].file == expected_path

    def test_parse_complex_multiline_error(self):
        """Verify complex multiline errors with annotations are parsed."""
        # Test complex Rust error with type mismatches
        output = """error[E0308]: mismatched types
  --> src/main.rs:45:18
   |
45 |         let result: Vec<String> = numbers
   |                     -----------   ^^^^^^^
   |                     |
   |                     expected due to this type
   |
   = note: expected struct `Vec<String>`
              found struct `HashMap<i32, String>`
   = help: you can convert a `HashMap` to a `Vec` using `.collect()`"""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert errors[0].file == "src/main.rs"
        assert errors[0].line == 45
        assert errors[0].column == 18
        assert errors[0].message == "mismatched types"
        assert errors[0].code == "E0308"

    def test_parse_error_messages_with_special_characters(self):
        """Verify error messages with special characters are captured."""
        output = """error[E0308]: expected `&str`, found `String`
 --> src/main.rs:10:20
   |
10 |     let x: &str = String::from("test");
   |            ----   ^^^^^^^^^^^^^^^^^^^^ expected `&str`, found `String`"""
        parser = RustCompilerParser()
        errors = parser.parse(output)

        assert len(errors) == 1
        assert "expected `&str`, found `String`" in errors[0].message
