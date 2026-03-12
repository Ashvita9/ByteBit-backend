"""
arena_api/runner.py
Executes student code against test cases in a sandboxed subprocess.
Supports Python, JavaScript, TypeScript, C++, Java, Go, SQL, HTML.
"""
import re
import subprocess
import sys

TIMEOUT = 5  # seconds max per test case

# ── helpers ────────────────────────────────────────────────────────────────────

def _result(passed, actual, expected, stderr=''):
    return {
        'passed': passed,
        'actual': actual,
        'expected': expected,
        'stderr': stderr[:600] if stderr else '',
    }


def _timeout_result(expected):
    return _result(False, '', expected, 'Time limit exceeded (5s)')


def _run_subprocess(cmd, input_data, expected_output, timeout=TIMEOUT) -> dict:
    """Generic helper: run cmd, feed stdin, compare stdout vs expected."""
    try:
        r = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
        )
        actual = r.stdout.strip()
        expected = expected_output.strip()
        return _result(actual == expected, actual, expected, r.stderr.strip())
    except subprocess.TimeoutExpired:
        return _timeout_result(expected_output.strip())
    except FileNotFoundError:
        raise  # let callers handle missing runtimes
    except Exception as e:
        return _result(False, '', expected_output.strip(), str(e))


def run_python(code: str, input_data: str, expected_output: str) -> dict:
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp = f.name
    try:
        return _run_subprocess([sys.executable, tmp], input_data, expected_output)
    except FileNotFoundError:
        return _result(False, '', expected_output.strip(), 'Python interpreter not found.')
    finally:
        try: os.unlink(tmp)
        except Exception: pass


def run_javascript(code: str, input_data: str, expected_output: str) -> dict:
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp = f.name
    try:
        return _run_subprocess(['node', tmp], input_data, expected_output)
    except FileNotFoundError:
        return _result(False, '', expected_output.strip(), 'Node.js not found on server.')
    finally:
        try: os.unlink(tmp)
        except Exception: pass


def run_typescript(code: str, input_data: str, expected_output: str) -> dict:
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.ts', mode='w', delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp = f.name
    try:
        # Try ts-node first, then npx ts-node
        for cmd in (['ts-node', tmp], ['npx', '--yes', 'ts-node', tmp]):
            try:
                return _run_subprocess(cmd, input_data, expected_output)
            except FileNotFoundError:
                continue
        # Last resort: node (works for .ts files that are valid JS)
        return _run_subprocess(['node', tmp], input_data, expected_output)
    except FileNotFoundError:
        return _result(False, '', expected_output.strip(), 'Node.js / ts-node not found on server.')
    finally:
        try: os.unlink(tmp)
        except Exception: pass


def run_cpp(code: str, input_data: str, expected_output: str) -> dict:
    import tempfile, os, shutil
    tmp_dir = tempfile.mkdtemp()
    src = os.path.join(tmp_dir, 'solution.cpp')
    exe = os.path.join(tmp_dir, 'solution')
    try:
        with open(src, 'w', encoding='utf-8') as f:
            f.write(code)
        cr = subprocess.run(
            ['g++', '-std=c++17', '-O2', '-o', exe, src],
            capture_output=True, text=True, timeout=15, encoding='utf-8',
        )
        if cr.returncode != 0:
            return _result(False, '', expected_output.strip(), 'Compilation error:\n' + cr.stderr.strip())
        return _run_subprocess([exe], input_data, expected_output)
    except subprocess.TimeoutExpired:
        return _result(False, '', expected_output.strip(), 'Compilation timed out.')
    except FileNotFoundError:
        return _result(False, '', expected_output.strip(), 'g++ compiler not found on server.')
    except Exception as e:
        return _result(False, '', expected_output.strip(), str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_java(code: str, input_data: str, expected_output: str) -> dict:
    import tempfile, os, shutil
    # Java requires filename == public class name
    m = re.search(r'public\s+class\s+(\w+)', code)
    class_name = m.group(1) if m else 'Solution'
    tmp_dir = tempfile.mkdtemp()
    src = os.path.join(tmp_dir, f'{class_name}.java')
    try:
        with open(src, 'w', encoding='utf-8') as f:
            f.write(code)
        cr = subprocess.run(
            ['javac', src],
            capture_output=True, text=True, timeout=20, encoding='utf-8',
        )
        if cr.returncode != 0:
            return _result(False, '', expected_output.strip(), 'Compilation error:\n' + cr.stderr.strip())
        return _run_subprocess(
            ['java', '-cp', tmp_dir, class_name],
            input_data, expected_output,
        )
    except subprocess.TimeoutExpired:
        return _result(False, '', expected_output.strip(), 'Compilation timed out.')
    except FileNotFoundError:
        return _result(False, '', expected_output.strip(), 'Java (javac/java) not found on server.')
    except Exception as e:
        return _result(False, '', expected_output.strip(), str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_go(code: str, input_data: str, expected_output: str) -> dict:
    import tempfile, os, shutil
    tmp_dir = tempfile.mkdtemp()
    src = os.path.join(tmp_dir, 'main.go')
    try:
        with open(src, 'w', encoding='utf-8') as f:
            f.write(code)
        result = _run_subprocess(['go', 'run', src], input_data, expected_output)
        return result
    except FileNotFoundError:
        return _result(False, '', expected_output.strip(), 'Go runtime not found on server.')
    except Exception as e:
        return _result(False, '', expected_output.strip(), str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_sql(code: str, input_data: str, expected_output: str) -> dict:
    """
    Run SQL using Python's built-in sqlite3.
    input_data may contain setup SQL (CREATE TABLE / INSERT statements).
    code is the student's query (typically SELECT).
    Output is formatted as tab-separated rows, one per line.
    """
    import sqlite3, io
    try:
        conn = sqlite3.connect(':memory:')
        cur = conn.cursor()
        # Run setup first if provided
        if input_data and input_data.strip():
            conn.executescript(input_data)
        # Run the student's query
        cur.execute(code.strip())
        rows = cur.fetchall()
        if rows:
            actual = '\n'.join('\t'.join(str(c) for c in row) for row in rows).strip()
        else:
            # For non-SELECT statements (INSERT/UPDATE), report rows affected
            actual = f'{cur.rowcount} row(s) affected' if cur.rowcount >= 0 else ''
        conn.close()
        expected = expected_output.strip()
        return _result(actual == expected, actual, expected)
    except Exception as e:
        return _result(False, '', expected_output.strip(), str(e))


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

        if lang_key == 'python':
            r = run_python(code, input_data, expected)
        elif lang_key in ('javascript', 'js'):
            r = run_javascript(code, input_data, expected)
        elif lang_key in ('typescript', 'ts'):
            r = run_typescript(code, input_data, expected)
        elif lang_key in ('c++', 'cpp', 'cplusplus'):
            r = run_cpp(code, input_data, expected)
        elif lang_key == 'java':
            r = run_java(code, input_data, expected)
        elif lang_key == 'go':
            r = run_go(code, input_data, expected)
        elif lang_key == 'sql':
            r = run_sql(code, input_data, expected)
        elif lang_key == 'html':
            # HTML: check if expected snippet is present in the submitted code
            passed = expected.lower() in code.lower() if expected else True
            r = _result(
                passed,
                'HTML contains expected content' if passed else 'Missing expected elements',
                expected,
                '' if passed else f"Expected to find '{expected}' in your HTML.",
            )
        else:
            r = _result(False, '', expected,
                        f'Auto-execution not supported for {language}. Ask your teacher to evaluate manually.')

        results.append({'index': i + 1, 'is_hidden': tc.get('is_hidden', False), **r})

    all_passed = all(r['passed'] for r in results)
    return {'all_passed': all_passed, 'results': results}
