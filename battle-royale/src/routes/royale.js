/**
 * routes/royale.js — REST endpoints for Battle Royale CRUD + join.
 */

const express = require('express');
const router = express.Router();
const { authenticate } = require('../middleware/auth');
const { requireRole } = require('../middleware/roles');
const tournamentService = require('../services/tournamentService');

/**
 * POST /api/royale — Create a new Battle Royale.
 * Body: { title, difficulty?, maxPlayers?, type? }
 * Auth: ADMIN or TEACHER
 */
router.post('/', authenticate, requireRole('ADMIN', 'TEACHER'), async (req, res) => {
    try {
        const { title, difficulty, maxPlayers, type } = req.body;

        if (!title) {
            return res.status(400).json({ error: 'title is required' });
        }

        const royale = await tournamentService.createRoyale({
            title,
            difficulty,
            maxPlayers,
            type,
            user: req.user,
        });

        res.status(201).json({
            message: 'Battle Royale created',
            royale: {
                id: royale.id,
                code: royale.code,
                title: royale.title,
                difficulty: royale.difficulty,
                type: royale.type,
                status: royale.status,
                maxPlayers: royale.max_players,
                createdBy: royale.creator_username,
            },
        });
    } catch (err) {
        console.error('Create royale error:', err);
        res.status(500).json({ error: err.message });
    }
});

/**
 * GET /api/royale/:id — Get royale details + bracket + participants.
 * Auth: any authenticated user
 */
router.get('/:id', authenticate, async (req, res) => {
    try {
        const details = await tournamentService.getRoyaleDetails(req.params.id);
        if (!details) {
            return res.status(404).json({ error: 'Battle Royale not found' });
        }

        res.json({
            royale: {
                id: details.id,
                code: details.code,
                title: details.title,
                difficulty: details.difficulty,
                type: details.type,
                status: details.status,
                maxPlayers: details.max_players,
                currentRound: details.current_round,
                totalRounds: details.total_rounds,
                winner: details.winner_id
                    ? { userId: details.winner_id, username: details.winner_username }
                    : null,
                createdBy: details.creator_username,
                createdAt: details.created_at,
            },
            participants: details.participants.map((p) => ({
                userId: p.user_id,
                username: p.username,
                role: p.role,
                eliminatedInRound: p.eliminated_in_round,
                isConnected: p.is_connected,
            })),
            matches: details.matches.map((m) => ({
                id: m.id,
                roundNumber: m.round_number,
                matchIndex: m.match_index,
                player1: m.player1_id
                    ? { userId: m.player1_id, username: m.player1_username }
                    : null,
                player2: m.player2_id
                    ? { userId: m.player2_id, username: m.player2_username }
                    : null,
                winner: m.winner_id
                    ? { userId: m.winner_id, username: m.winner_username }
                    : null,
                status: m.status,
                questionTitle: m.question_title,
            })),
        });
    } catch (err) {
        console.error('Get royale error:', err);
        res.status(500).json({ error: err.message });
    }
});

/**
 * POST /api/royale/join — Join a royale by code.
 * Body: { code }
 * Auth: STUDENT
 */
router.post('/join', authenticate, async (req, res) => {
    try {
        const { code } = req.body;
        if (!code) {
            return res.status(400).json({ error: 'code is required' });
        }

        const { royale, playerCount } = await tournamentService.joinRoyale({
            code,
            user: req.user,
        });

        res.json({
            message: 'Joined Battle Royale',
            royale: {
                id: royale.id,
                title: royale.title,
                difficulty: royale.difficulty,
                status: royale.status,
                maxPlayers: royale.max_players,
                playerCount,
            },
        });
    } catch (err) {
        if (err.message.includes('Invalid') || err.message.includes('full') || err.message.includes('Already')) {
            return res.status(400).json({ error: err.message });
        }
        console.error('Join royale error:', err);
        res.status(500).json({ error: err.message });
    }
});

/**
 * POST /api/royale/:id/start — Force-start a tournament.
 * Auth: ADMIN or TEACHER (creator)
 */
router.post('/:id/start', authenticate, requireRole('ADMIN', 'TEACHER'), async (req, res) => {
    try {
        // Get the io instance from app
        const io = req.app.get('io');
        const result = await tournamentService.startTournament(req.params.id, io);

        res.json({
            message: 'Tournament started',
            totalRounds: result.bracket.totalRounds,
            matchCount: result.matches.length,
        });
    } catch (err) {
        if (err.message.includes('already') || err.message.includes('Need at least')) {
            return res.status(400).json({ error: err.message });
        }
        console.error('Start royale error:', err);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
