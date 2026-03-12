"""
arena_api/runner.py
Executes student code against test cases in a sandboxed subprocess.
Supports Python only for now (safe exec via subprocess with timeout).
Other languages return a "not supported" result so UI still works.
"""
import subprocess
import sys
import textwrap

TIMEOUT = 5  # seconds max per test case

LANG_RUNNERS = {
    'python': ('python', '.py'),
    'javascript': ('node', '.js'),
}


def run_python(code: str, input_data: str, expected_output: str) -> dict:
    """Run code string as Python, return result dict."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            encoding='utf-8',
        )
        actual = result.stdout.strip()
        expected = expected_output.strip()
        passed = actual == expected
        return {
            'passed': passed,
            'actual': actual,
            'expected': expected,
            'stderr': result.stderr.strip()[:500] if result.stderr else '',
        }
    except subprocess.TimeoutExpired:
        return {'passed': False, 'actual': '', 'expected': expected_output.strip(), 'stderr': 'Time limit exceeded (5s)'}
    except Exception as e:
        return {'passed': False, 'actual': '', 'expected': expected_output.strip(), 'stderr': str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def run_javascript(code: str, input_data: str, expected_output: str) -> dict:
    """Run code string as JavaScript using node, return result dict."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False, encoding='utf-8') as f:
        # We might need to handle inputs. For simple algorithms, assume the code reads from process.stdin or just prints.
        # But for basics, let's just run it.
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ['node', tmp_path],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            encoding='utf-8',
        )
        actual = result.stdout.strip()
        expected = expected_output.strip()
        passed = actual == expected
        return {
            'passed': passed,
            'actual': actual,
            'expected': expected,
            'stderr': result.stderr.strip()[:500] if result.stderr else '',
        }
    except subprocess.TimeoutExpired:
        return {'passed': False, 'actual': '', 'expected': expected_output.strip(), 'stderr': 'Time limit exceeded (5s)'}
    except Exception as e:
        return {'passed': False, 'actual': '', 'expected': expected_output.strip(), 'stderr': str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def run_cpp(code: str, input_data: str, expected_output: str) -> dict:
    """Compile and run C++ code; return result dict."""
    import tempfile, os
    tmp_dir = tempfile.mkdtemp()
    src_path = os.path.join(tmp_dir, 'solution.cpp')
    exe_path = os.path.join(tmp_dir, 'solution')
    try:
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)
        # Compile
        compile_result = subprocess.run(
            ['g++', '-std=c++17', '-O2', '-o', exe_path, src_path],
            capture_output=True, text=True, timeout=15, encoding='utf-8',
        )
        if compile_result.returncode != 0:
            return {
                'passed': False,
                'actual': '',
                'expected': expected_output.strip(),
                'stderr': 'Compilation error:\n' + compile_result.stderr.strip()[:600],
            }
        # Run
        run_result = subprocess.run(
            [exe_path],
            input=input_data,
            capture_output=True, text=True, timeout=TIMEOUT, encoding='utf-8',
        )
        actual = run_result.stdout.strip()
        expected = expected_output.strip()
        return {
            'passed': actual == expected,
            'actual': actual,
            'expected': expected,
            'stderr': run_result.stderr.strip()[:500] if run_result.stderr else '',
        }
    except subprocess.TimeoutExpired:
        return {'passed': False, 'actual': '', 'expected': expected_output.strip(), 'stderr': 'Time limit exceeded (5s)'}
    except FileNotFoundError:
        return {'passed': False, 'actual': '', 'expected': expected_output.strip(), 'stderr': 'g++ compiler not found on server. Ask your admin to install build-essential.'}
    except Exception as e:
        return {'passed': False, 'actual': '', 'expected': expected_output.strip(), 'stderr': str(e)}
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_test_cases(code: str, language: str, test_cases: list) -> dict:
    """
    Run all test cases for a piece of code.
    Returns:
      {
        'all_passed': bool,
        'results': [{ 'index': int, 'passed': bool, 'actual': str, 'expected': str, 'stderr': str }],
      }
    """
    lang_key = language.strip().lower() if language else 'python'

    results = []
    for i, tc in enumerate(test_cases):
        input_data = tc.get('input_data', '')
        expected   = tc.get('output_data', tc.get('expected_output', ''))

        if lang_key in ('python',):
            r = run_python(code, input_data, expected)
        elif lang_key in ('javascript', 'typescript', 'js', 'ts'):
            r = run_javascript(code, input_data, expected)
        elif lang_key in ('c++', 'cpp', 'c plus plus', 'cplusplus'):
            r = run_cpp(code, input_data, expected)
        elif lang_key == 'html':
            # For HTML, we simply check if the expected content is present in the code string.
            # Example: Expected output might be "<h1>" or "<div>".
            actual = "HTML Code Evaluated"
            passed = expected.lower() in code.lower() if expected else True
            r = {
                'passed': passed,
                'actual': actual if passed else "Missing expected elements",
                'expected': expected,
                'stderr': '' if passed else f"Expected to find '{expected}' in your HTML but didn't.",
            }
        else:
            # Language not supported for auto-run — tell student
            r = {
                'passed': False,
                'actual': '',
                'expected': expected,
                'stderr': f'Auto-execution not supported for {language}. Ask your teacher to evaluate manually.',
            }

        results.append({'index': i + 1, 'is_hidden': tc.get('is_hidden', False), **r})

    all_passed = all(r['passed'] for r in results)
    return {'all_passed': all_passed, 'results': results}
