/**
 * matchService.js — Individual match lifecycle management.
 *
 * Handles code submission, validation, winner determination,
 * and special final-round logic (time + complexity comparison).
 */

const db = require('../db/knex');
const redis = require('../utils/redis');
const { runCode } = require('./codeRunner');
const { evaluateComplexity, compareComplexity } = require('./aiEvaluator');
const tournamentService = require('./tournamentService');

/**
 * Process a code submission for a match.
 *
 * Normal rounds: first valid solution wins immediately.
 * Final round:   both must submit; compare time + complexity.
 */
async function submitSolution({ matchId, userId, username, code, language }, io) {
    const match = await db('matches').where({ id: matchId }).first();
    if (!match) throw new Error('Match not found');
    if (match.status !== 'active') throw new Error('Match is not active');

    // Verify player belongs to this match
    if (match.player1_id !== userId && match.player2_id !== userId) {
        throw new Error('You are not a participant in this match');
    }

    // Check for duplicate submission
    const existingSub = await db('submissions')
        .where({ match_id: matchId, user_id: userId })
        .first();
    if (existingSub) throw new Error('You have already submitted for this match');

    // Get match start time from Redis
    const matchState = await redis.hgetall(`match:${matchId}:state`);
    const startedAt = parseInt(matchState.startedAt || '0', 10);
    const timeTakenMs = startedAt ? Date.now() - startedAt : 0;
    const isFinal = matchState.isFinal === '1';

    // Run code against test cases
    const testCases = JSON.parse(match.test_cases || '[]');
    const result = await runCode(code, language, testCases);

    // AI complexity evaluation
    const complexityEval = await evaluateComplexity(code, language);

    // Save submission
    const [submission] = await db('submissions')
        .insert({
            match_id: matchId,
            user_id: userId,
            username,
            code,
            language,
            passed: result.passed,
            output: result.output,
            time_taken_ms: timeTakenMs,
            time_complexity: complexityEval.complexity,
        })
        .returning('*');

    // Acknowledge to submitter
    const ackPayload = {
        matchId,
        passed: result.passed,
        output: result.output,
        passedCount: result.passedCount,
        totalCount: result.totalCount,
        timeTakenMs,
        complexity: complexityEval.complexity,
    };

    // Notify opponent of progress
    const opponentId = match.player1_id === userId ? match.player2_id : match.player1_id;
    io.to(`user:${opponentId}`).emit('match:opponent_progress', {
        matchId,
        percentage: Math.round((result.passedCount / result.totalCount) * 100),
    });

    // ── Winner determination ─────────────────────────────────────────

    if (isFinal) {
        // FINAL ROUND: both must submit valid solutions to compare
        const allSubmissions = await db('submissions')
            .where({ match_id: matchId })
            .orderBy('submitted_at');

        const validSubmissions = allSubmissions.filter((s) => s.passed);

        if (validSubmissions.length === 2) {
            // Both solved it — compare
            const winner = determineFinalWinner(validSubmissions);
            await completeMatch(matchId, winner, match.royale_id, match.round_number, io);
        } else if (allSubmissions.length === 2) {
            // Both submitted but not both passed
            if (validSubmissions.length === 1) {
                // Only one passed — they win
                const winner = {
                    userId: validSubmissions[0].user_id,
                    username: validSubmissions[0].username,
                };
                await completeMatch(matchId, winner, match.royale_id, match.round_number, io);
            } else {
                // Neither passed — first to submit loses less badly? Pick player1 by default
                const winner = {
                    userId: match.player1_id,
                    username: match.player1_username,
                };
                await completeMatch(matchId, winner, match.royale_id, match.round_number, io);
            }
        }
        // Else: waiting for second submission
    } else {
        // NORMAL ROUND: first valid solution wins
        if (result.passed) {
            const winner = { userId: userId, username };
            await completeMatch(matchId, winner, match.royale_id, match.round_number, io);
        }
    }

    return { submission, ack: ackPayload };
}

/**
 * Compare two valid final-round submissions.
 * Priority: 1) time to complete   2) time complexity score
 */
function determineFinalWinner(submissions) {
    const [a, b] = submissions;

    // Compare time first
    if (a.time_taken_ms !== b.time_taken_ms) {
        const faster = a.time_taken_ms < b.time_taken_ms ? a : b;
        return { userId: faster.user_id, username: faster.username };
    }

    // Compare complexity
    const evalA = { score: getComplexityScore(a.time_complexity) };
    const evalB = { score: getComplexityScore(b.time_complexity) };
    const cmp = compareComplexity(evalA, evalB);

    if (cmp < 0) return { userId: a.user_id, username: a.username };
    if (cmp > 0) return { userId: b.user_id, username: b.username };

    // Absolute tie — first to submit wins
    return { userId: a.user_id, username: a.username };
}

function getComplexityScore(complexity) {
    const ranks = { 'O(1)': 0, 'O(log n)': 1, 'O(n)': 2, 'O(n log n)': 3, 'O(n²)': 4, 'O(n³)': 5, 'O(2^n)': 6 };
    return ranks[complexity] ?? 99;
}

/**
 * Mark a match as completed and trigger round progression.
 */
async function completeMatch(matchId, winner, royaleId, roundNumber, io) {
    await db('matches').where({ id: matchId }).update({
        status: 'completed',
        winner_id: winner.userId,
        winner_username: winner.username,
        completed_at: db.fn.now(),
    });

    // Mark loser as eliminated
    const match = await db('matches').where({ id: matchId }).first();
    const loserId = match.player1_id === winner.userId ? match.player2_id : match.player1_id;

    if (loserId) {
        await db('battle_royale_participants')
            .where({ royale_id: royaleId, user_id: loserId })
            .update({ eliminated_in_round: roundNumber });

        // Notify loser
        io.to(`user:${loserId}`).emit('tournament:eliminated', {
            round: roundNumber,
            defeatedBy: winner.username,
        });
    }

    // Emit match result
    io.to(`royale:${royaleId}`).emit('match:result', {
        matchId,
        roundNumber,
        winner: { userId: winner.userId, username: winner.username },
        loser: loserId
            ? { userId: loserId, username: match.player1_id === loserId ? match.player1_username : match.player2_username }
            : null,
    });

    // Clean up match state from Redis
    await redis.del(`match:${matchId}:state`);

    // Check if the entire round is done
    await tournamentService.checkRoundCompletion(royaleId, roundNumber, io);
}

module.exports = { submitSolution, completeMatch, determineFinalWinner };
