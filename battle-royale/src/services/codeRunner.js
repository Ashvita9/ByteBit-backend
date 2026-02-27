/**
 * codeRunner.js — Sandboxed code execution for Battle Royale matches.
 *
 * Runs user code inside a child process with a strict timeout.
 * Compares stdout against expected outputs for each test case.
 */

const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const config = require('../config');

/**
 * Run user code against an array of test cases.
 *
 * @param {string}   code       – Source code submitted by the user
 * @param {string}   language   – 'Python' | 'JavaScript' | 'C++' | 'Java'
 * @param {Array<{input_data: string, output_data: string}>} testCases
 * @returns {Promise<{ passed: boolean, output: string, passedCount: number, totalCount: number }>}
 */
async function runCode(code, language, testCases) {
    const results = [];
    let allPassed = true;

    for (const tc of testCases) {
        try {
            const result = await executeOnce(code, language, tc.input_data);
            const expected = tc.output_data.trim();
            const got = result.stdout.trim();

            if (got !== expected) {
                allPassed = false;
                results.push(`❌ Expected: ${expected} | Got: ${got}`);
            } else {
                results.push(`✅ Passed`);
            }
        } catch (err) {
            allPassed = false;
            results.push(`💥 Error: ${err.message}`);
        }
    }

    return {
        passed: allPassed,
        output: results.join('\n'),
        passedCount: results.filter((r) => r.startsWith('✅')).length,
        totalCount: testCases.length,
    };
}

/**
 * Execute code once with the given input.
 */
function executeOnce(code, language, inputData) {
    return new Promise((resolve, reject) => {
        const timeout = config.game.codeExecTimeout;
        const tmpDir = os.tmpdir();

        let cmd, args, filePath;

        switch (language.toLowerCase()) {
            case 'python': {
                // Inject input_data as a variable
                const wrappedCode = `input_data = ${JSON.stringify(inputData)}\n${code}`;
                filePath = path.join(tmpDir, `br_${Date.now()}_${Math.random().toString(36).slice(2)}.py`);
                fs.writeFileSync(filePath, wrappedCode);
                cmd = 'python';
                args = [filePath];
                break;
            }
            case 'javascript': {
                const wrappedCode = `const input_data = ${JSON.stringify(inputData)};\n${code}`;
                filePath = path.join(tmpDir, `br_${Date.now()}_${Math.random().toString(36).slice(2)}.js`);
                fs.writeFileSync(filePath, wrappedCode);
                cmd = 'node';
                args = [filePath];
                break;
            }
            default: {
                // Fallback: try running as Python
                const wrappedCode = `input_data = ${JSON.stringify(inputData)}\n${code}`;
                filePath = path.join(tmpDir, `br_${Date.now()}_${Math.random().toString(36).slice(2)}.py`);
                fs.writeFileSync(filePath, wrappedCode);
                cmd = 'python';
                args = [filePath];
            }
        }

        const proc = execFile(cmd, args, { timeout, maxBuffer: 1024 * 1024 }, (error, stdout, stderr) => {
            // Clean up temp file
            try { fs.unlinkSync(filePath); } catch { }

            if (error) {
                if (error.killed) {
                    return reject(new Error(`Execution timed out (${timeout}ms)`));
                }
                return reject(new Error(stderr || error.message));
            }
            resolve({ stdout, stderr });
        });
    });
}

module.exports = { runCode };
