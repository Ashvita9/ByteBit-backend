/**
 * aiEvaluator.js — Placeholder for AI-powered time complexity analysis.
 *
 * In production, this would call an LLM (OpenAI / Gemini / Claude) with the
 * code and ask it to evaluate time complexity.  For now it returns a mock
 * analysis so the tournament logic can proceed.
 */

const COMPLEXITIES = ['O(1)', 'O(log n)', 'O(n)', 'O(n log n)', 'O(n²)', 'O(n³)', 'O(2^n)'];

// Lower index = better complexity
const COMPLEXITY_RANK = {};
COMPLEXITIES.forEach((c, i) => {
    COMPLEXITY_RANK[c] = i;
});

/**
 * Evaluate the time complexity of submitted code.
 *
 * @param {string} code   – The source code to analyse
 * @param {string} language – Programming language
 * @returns {Promise<{ complexity: string, score: number, explanation: string }>}
 */
async function evaluateComplexity(code, language = 'Python') {
    // ── PLACEHOLDER ─────────────────────────────────────────────────
    // Simple heuristic mock: look for nested loops, recursion, etc.
    const lines = code.split('\n');
    let loopDepth = 0;
    let maxDepth = 0;
    let hasRecursion = false;

    for (const line of lines) {
        const trimmed = line.trim();
        if (/\b(for|while)\b/.test(trimmed)) {
            loopDepth++;
            maxDepth = Math.max(maxDepth, loopDepth);
        }
        if (trimmed === '}' || trimmed === '') {
            loopDepth = Math.max(0, loopDepth - 1);
        }
        if (/\bdef\b.*\(/.test(trimmed) || /\bfunction\b/.test(trimmed)) {
            // Very naive recursion check — looks for function name in body
            hasRecursion = true;
        }
    }

    let complexity;
    if (hasRecursion && maxDepth >= 2) {
        complexity = 'O(2^n)';
    } else if (maxDepth >= 3) {
        complexity = 'O(n³)';
    } else if (maxDepth === 2) {
        complexity = 'O(n²)';
    } else if (maxDepth === 1) {
        complexity = 'O(n)';
    } else {
        complexity = 'O(1)';
    }
    // ── END PLACEHOLDER ─────────────────────────────────────────────

    return {
        complexity,
        score: COMPLEXITY_RANK[complexity] ?? 99,
        explanation: `[AI Placeholder] Detected ${maxDepth} nested loop(s). Estimated: ${complexity}`,
    };
}

/**
 * Compare two complexity evaluations. Returns -1 if a is better, 1 if b is better, 0 if equal.
 */
function compareComplexity(evalA, evalB) {
    if (evalA.score < evalB.score) return -1;
    if (evalA.score > evalB.score) return 1;
    return 0;
}

module.exports = { evaluateComplexity, compareComplexity, COMPLEXITIES, COMPLEXITY_RANK };
