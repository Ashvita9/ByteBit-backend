/**
 * tournamentService.js — Core tournament lifecycle management.
 *
 * Handles creation, joining, starting, bracket progression, and completion.
 */

const db = require('../db/knex');
const redis = require('../utils/redis');
const { generateCode } = require('../utils/codeGenerator');
const { generateBracket } = require('../utils/bracketGenerator');
const config = require('../config');

const TTL = 7200; // 2 hours

// ── Questions Pool (stub) ──────────────────────────────────────────
// In production, pull from your Django CodingTask collection via API or shared DB.
const QUESTION_POOL = {
    Easy: [
        {
            id: 'easy_1',
            title: 'Reverse a String',
            description: 'Write code that prints the reverse of `input_data`.',
            test_cases: [
                { input_data: 'hello', output_data: 'olleh' },
                { input_data: 'world', output_data: 'dlrow' },
                { input_data: 'abc', output_data: 'cba' },
            ],
        },
        {
            id: 'easy_2',
            title: 'Sum of Digits',
            description: 'Print the sum of digits of the number given in `input_data`.',
            test_cases: [
                { input_data: '123', output_data: '6' },
                { input_data: '999', output_data: '27' },
                { input_data: '10', output_data: '1' },
            ],
        },
        {
            id: 'easy_3',
            title: 'Count Vowels',
            description: 'Print the number of vowels (a, e, i, o, u) in `input_data`.',
            test_cases: [
                { input_data: 'hello', output_data: '2' },
                { input_data: 'aeiou', output_data: '5' },
                { input_data: 'rhythm', output_data: '0' },
            ],
        },
    ],
    Medium: [
        {
            id: 'med_1',
            title: 'Palindrome Check',
            description: 'Print "True" if `input_data` is a palindrome, "False" otherwise.',
            test_cases: [
                { input_data: 'racecar', output_data: 'True' },
                { input_data: 'hello', output_data: 'False' },
                { input_data: 'madam', output_data: 'True' },
            ],
        },
        {
            id: 'med_2',
            title: 'FizzBuzz Single',
            description: 'Given a number in `input_data`, print "FizzBuzz" if divisible by 15, "Fizz" if by 3, "Buzz" if by 5, or the number itself.',
            test_cases: [
                { input_data: '15', output_data: 'FizzBuzz' },
                { input_data: '9', output_data: 'Fizz' },
                { input_data: '10', output_data: 'Buzz' },
                { input_data: '7', output_data: '7' },
            ],
        },
    ],
    Hard: [
        {
            id: 'hard_1',
            title: 'Prime Factorization',
            description: 'Print the prime factors of the integer in `input_data`, space-separated in ascending order.',
            test_cases: [
                { input_data: '12', output_data: '2 2 3' },
                { input_data: '100', output_data: '2 2 5 5' },
                { input_data: '17', output_data: '17' },
            ],
        },
        {
            id: 'hard_2',
            title: 'Longest Common Subsequence Length',
            description: 'Input has two strings comma-separated. Print the length of their longest common subsequence.',
            test_cases: [
                { input_data: 'abcde,ace', output_data: '3' },
                { input_data: 'abc,abc', output_data: '3' },
                { input_data: 'abc,def', output_data: '0' },
            ],
        },
    ],
};

/**
 * Pick a random question that hasn't been used in this tournament yet.
 */
function pickQuestion(difficulty, usedIds = []) {
    const pool = QUESTION_POOL[difficulty] || QUESTION_POOL.Easy;
    const available = pool.filter((q) => !usedIds.includes(q.id));
    if (available.length === 0) {
        // If all used, allow repeats
        return pool[Math.floor(Math.random() * pool.length)];
    }
    return available[Math.floor(Math.random() * available.length)];
}

// ── Create ──────────────────────────────────────────────────────────

async function createRoyale({ title, difficulty, maxPlayers, type, user }) {
    const code = generateCode();
    const royaleType = user.role === 'ADMIN' ? (type || 'public') : 'private';

    const [royale] = await db('battle_royales')
        .insert({
            code,
            title,
            created_by: user.userId,
            creator_username: user.username,
            creator_role: user.role,
            difficulty: difficulty || 'Easy',
            type: royaleType,
            max_players: Math.min(maxPlayers || config.game.defaultMaxPlayers, 10),
        })
        .returning('*');

    // Seed Redis state
    await redis.hset(`royale:${royale.id}:state`, {
        status: 'waiting',
        playerCount: '0',
        round: '0',
    });
    await redis.expire(`royale:${royale.id}:state`, TTL);

    return royale;
}

// ── Join ─────────────────────────────────────────────────────────────

async function joinRoyale({ code, user }) {
    const royale = await db('battle_royales').where({ code }).first();
    if (!royale) throw new Error('Invalid room code');
    if (royale.status !== 'waiting') throw new Error('Tournament already started or completed');

    // Check max players
    const participantCount = await db('battle_royale_participants')
        .where({ royale_id: royale.id })
        .count('id as cnt')
        .first();

    if (parseInt(participantCount.cnt, 10) >= royale.max_players) {
        throw new Error('Room is full');
    }

    // Check duplicate
    const existing = await db('battle_royale_participants')
        .where({ royale_id: royale.id, user_id: user.userId })
        .first();

    if (existing) throw new Error('Already joined this tournament');

    // Insert participant
    const [participant] = await db('battle_royale_participants')
        .insert({
            royale_id: royale.id,
            user_id: user.userId,
            username: user.username,
            role: user.role,
        })
        .returning('*');

    // Update Redis
    await redis.sadd(`royale:${royale.id}:players`, user.userId);
    await redis.hincrby(`royale:${royale.id}:state`, 'playerCount', 1);

    const newCount = await redis.scard(`royale:${royale.id}:players`);

    return { royale, participant, playerCount: newCount };
}

// ── Start Tournament ────────────────────────────────────────────────

async function startTournament(royaleId, io) {
    // Lock to prevent double-start
    const lockKey = `royale:${royaleId}:lock`;
    const locked = await redis.set(lockKey, '1', 'NX', 'EX', 30);
    if (!locked) throw new Error('Tournament is already starting');

    try {
        const royale = await db('battle_royales').where({ id: royaleId }).first();
        if (!royale) throw new Error('Tournament not found');
        if (royale.status !== 'waiting') throw new Error('Tournament already started');

        const participants = await db('battle_royale_participants')
            .where({ royale_id: royaleId })
            .select('user_id', 'username');

        if (participants.length < 2) throw new Error('Need at least 2 players');

        // Generate bracket
        const players = participants.map((p) => ({
            userId: p.user_id,
            username: p.username,
        }));

        const bracket = generateBracket(players);

        // Update royale status
        await db('battle_royales').where({ id: royaleId }).update({
            status: 'in_progress',
            current_round: 1,
            total_rounds: bracket.totalRounds,
            started_at: db.fn.now(),
        });

        // Store bracket in Redis
        await redis.set(`royale:${royaleId}:bracket`, JSON.stringify(bracket));
        await redis.hset(`royale:${royaleId}:state`, {
            status: 'in_progress',
            round: '1',
        });

        // Track used question IDs
        const usedQuestionIds = [];

        // Create match records for round 1
        const round1 = bracket.rounds[0];
        const matchRecords = [];

        for (const slot of round1) {
            const isBye = !slot.player2;
            const question = isBye ? null : pickQuestion(royale.difficulty, usedQuestionIds);
            if (question) usedQuestionIds.push(question.id);

            const [match] = await db('matches')
                .insert({
                    royale_id: royaleId,
                    round_number: 1,
                    match_index: slot.matchIndex,
                    player1_id: slot.player1?.userId || null,
                    player1_username: slot.player1?.username || null,
                    player2_id: slot.player2?.userId || null,
                    player2_username: slot.player2?.username || null,
                    question_id: question?.id || null,
                    question_title: question?.title || null,
                    question_description: question?.description || null,
                    test_cases: question ? JSON.stringify(question.test_cases) : null,
                    status: isBye ? 'completed' : 'active',
                    winner_id: isBye ? slot.player1?.userId : null,
                    winner_username: isBye ? slot.player1?.username : null,
                    started_at: isBye ? null : db.fn.now(),
                    completed_at: isBye ? db.fn.now() : null,
                })
                .returning('*');

            matchRecords.push(match);
        }

        // Store used questions for this tournament
        await redis.set(`royale:${royaleId}:usedQuestions`, JSON.stringify(usedQuestionIds));
        await redis.expire(`royale:${royaleId}:usedQuestions`, TTL);

        // Emit bracket to room
        io.to(`royale:${royaleId}`).emit('royale:starting', {
            bracket,
            totalRounds: bracket.totalRounds,
            currentRound: 1,
        });

        // Emit individual match start events
        for (const match of matchRecords) {
            if (match.status === 'active') {
                const matchRoom = `match:${match.id}`;

                // Store match start time in Redis
                await redis.hset(`match:${match.id}:state`, {
                    status: 'active',
                    startedAt: Date.now().toString(),
                    submissions: '0',
                });
                await redis.expire(`match:${match.id}:state`, TTL);

                // Emit to each player
                const question = {
                    id: match.question_id,
                    title: match.question_title,
                    description: match.question_description,
                    testCases: JSON.parse(match.test_cases).filter((tc) => !tc.is_hidden),
                };

                io.to(`user:${match.player1_id}`).emit('match:started', {
                    matchId: match.id,
                    roundNumber: match.round_number,
                    opponent: { userId: match.player2_id, username: match.player2_username },
                    question,
                });

                io.to(`user:${match.player2_id}`).emit('match:started', {
                    matchId: match.id,
                    roundNumber: match.round_number,
                    opponent: { userId: match.player1_id, username: match.player1_username },
                    question,
                });
            }
        }

        return { bracket, matches: matchRecords };
    } finally {
        await redis.del(lockKey);
    }
}

// ── Check Round Completion ──────────────────────────────────────────

async function checkRoundCompletion(royaleId, roundNumber, io) {
    const matches = await db('matches')
        .where({ royale_id: royaleId, round_number: roundNumber });

    const allCompleted = matches.every((m) => m.status === 'completed');
    if (!allCompleted) return false;

    const royale = await db('battle_royales').where({ id: royaleId }).first();
    const winners = matches.map((m) => ({
        userId: m.winner_id,
        username: m.winner_username,
    })).filter((w) => w.userId);

    // Check if tournament is done
    if (winners.length === 1) {
        // We have a champion!
        await completeTournament(royaleId, winners[0], io);
        return true;
    }

    // Start next round
    const nextRound = roundNumber + 1;
    await db('battle_royales').where({ id: royaleId }).update({
        current_round: nextRound,
    });
    await redis.hset(`royale:${royaleId}:state`, 'round', nextRound.toString());

    // Get used questions
    const usedRaw = await redis.get(`royale:${royaleId}:usedQuestions`);
    const usedQuestionIds = usedRaw ? JSON.parse(usedRaw) : [];
    const isFinalRound = winners.length === 2;

    // Create matches for next round
    const nextMatches = [];
    for (let i = 0; i < winners.length; i += 2) {
        const p1 = winners[i];
        const p2 = winners[i + 1] || null;
        const isBye = !p2;
        const question = isBye ? null : pickQuestion(royale.difficulty, usedQuestionIds);
        if (question) usedQuestionIds.push(question.id);

        const [match] = await db('matches')
            .insert({
                royale_id: royaleId,
                round_number: nextRound,
                match_index: Math.floor(i / 2),
                player1_id: p1.userId,
                player1_username: p1.username,
                player2_id: p2?.userId || null,
                player2_username: p2?.username || null,
                question_id: question?.id || null,
                question_title: question?.title || null,
                question_description: question?.description || null,
                test_cases: question ? JSON.stringify(question.test_cases) : null,
                status: isBye ? 'completed' : 'active',
                winner_id: isBye ? p1.userId : null,
                winner_username: isBye ? p1.username : null,
                started_at: isBye ? null : db.fn.now(),
                completed_at: isBye ? db.fn.now() : null,
            })
            .returning('*');

        nextMatches.push(match);
    }

    await redis.set(`royale:${royaleId}:usedQuestions`, JSON.stringify(usedQuestionIds));

    // Emit round advance
    io.to(`royale:${royaleId}`).emit('round:advance', {
        round: nextRound,
        isFinal: isFinalRound,
        matches: nextMatches.map((m) => ({
            matchId: m.id,
            player1: { userId: m.player1_id, username: m.player1_username },
            player2: m.player2_id
                ? { userId: m.player2_id, username: m.player2_username }
                : null,
            status: m.status,
        })),
    });

    // Emit match start to active players
    for (const match of nextMatches) {
        if (match.status === 'active') {
            await redis.hset(`match:${match.id}:state`, {
                status: 'active',
                startedAt: Date.now().toString(),
                submissions: '0',
                isFinal: isFinalRound ? '1' : '0',
            });
            await redis.expire(`match:${match.id}:state`, TTL);

            const question = {
                id: match.question_id,
                title: match.question_title,
                description: match.question_description,
                testCases: JSON.parse(match.test_cases).filter((tc) => !tc.is_hidden),
            };

            io.to(`user:${match.player1_id}`).emit('match:started', {
                matchId: match.id,
                roundNumber: nextRound,
                isFinal: isFinalRound,
                opponent: { userId: match.player2_id, username: match.player2_username },
                question,
            });

            io.to(`user:${match.player2_id}`).emit('match:started', {
                matchId: match.id,
                roundNumber: nextRound,
                isFinal: isFinalRound,
                opponent: { userId: match.player1_id, username: match.player1_username },
                question,
            });
        }
    }

    // If a bye caused round to auto-complete, check again
    const byeMatches = nextMatches.filter((m) => m.status === 'completed');
    if (byeMatches.length === nextMatches.length) {
        return checkRoundCompletion(royaleId, nextRound, io);
    }

    return false;
}

// ── Complete Tournament ─────────────────────────────────────────────

async function completeTournament(royaleId, winner, io) {
    await db('battle_royales').where({ id: royaleId }).update({
        status: 'completed',
        winner_id: winner.userId,
        winner_username: winner.username,
        completed_at: db.fn.now(),
    });

    // Award Battle Royale points
    const WINNER_POINTS = 100;
    const existing = await db('battle_royale_points')
        .where({ user_id: winner.userId })
        .first();

    if (existing) {
        await db('battle_royale_points')
            .where({ user_id: winner.userId })
            .update({
                points: db.raw('points + ?', [WINNER_POINTS]),
                wins: db.raw('wins + 1'),
                tournaments_played: db.raw('tournaments_played + 1'),
                updated_at: db.fn.now(),
            });
    } else {
        await db('battle_royale_points').insert({
            user_id: winner.userId,
            username: winner.username,
            points: WINNER_POINTS,
            wins: 1,
            tournaments_played: 1,
        });
    }

    // Update all other participants' losses + tournaments_played
    const participants = await db('battle_royale_participants')
        .where({ royale_id: royaleId })
        .whereNot({ user_id: winner.userId });

    for (const p of participants) {
        const exists = await db('battle_royale_points')
            .where({ user_id: p.user_id })
            .first();

        if (exists) {
            await db('battle_royale_points')
                .where({ user_id: p.user_id })
                .update({
                    losses: db.raw('losses + 1'),
                    tournaments_played: db.raw('tournaments_played + 1'),
                    updated_at: db.fn.now(),
                });
        } else {
            await db('battle_royale_points').insert({
                user_id: p.user_id,
                username: p.username,
                points: 0,
                losses: 1,
                tournaments_played: 1,
            });
        }
    }

    // Emit tournament complete
    io.to(`royale:${royaleId}`).emit('tournament:complete', {
        winner: { userId: winner.userId, username: winner.username },
        pointsAwarded: WINNER_POINTS,
    });

    // Clean up Redis (delayed)
    setTimeout(async () => {
        const keys = await redis.keys(`royale:${royaleId}:*`);
        if (keys.length) await redis.del(...keys);
    }, 30000);
}

// ── Get royale details ──────────────────────────────────────────────

async function getRoyaleDetails(royaleId) {
    const royale = await db('battle_royales').where({ id: royaleId }).first();
    if (!royale) return null;

    const participants = await db('battle_royale_participants')
        .where({ royale_id: royaleId })
        .orderBy('joined_at');

    const matches = await db('matches')
        .where({ royale_id: royaleId })
        .orderBy(['round_number', 'match_index']);

    return { ...royale, participants, matches };
}

module.exports = {
    createRoyale,
    joinRoyale,
    startTournament,
    checkRoundCompletion,
    completeTournament,
    getRoyaleDetails,
    pickQuestion,
};
