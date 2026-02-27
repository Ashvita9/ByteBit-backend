/**
 * routes/leaderboard.js — Battle Royale points leaderboard.
 */

const express = require('express');
const router = express.Router();
const { authenticate } = require('../middleware/auth');
const db = require('../db/knex');

/**
 * GET /api/leaderboard — Global Battle Royale points ranking.
 * Query: ?limit=20&offset=0
 */
router.get('/', authenticate, async (req, res) => {
    try {
        const limit = Math.min(parseInt(req.query.limit, 10) || 20, 100);
        const offset = parseInt(req.query.offset, 10) || 0;

        const leaderboard = await db('battle_royale_points')
            .orderBy('points', 'desc')
            .limit(limit)
            .offset(offset);

        const total = await db('battle_royale_points').count('id as cnt').first();

        res.json({
            leaderboard: leaderboard.map((entry, idx) => ({
                rank: offset + idx + 1,
                userId: entry.user_id,
                username: entry.username,
                points: entry.points,
                wins: entry.wins,
                losses: entry.losses,
                tournamentsPlayed: entry.tournaments_played,
            })),
            total: parseInt(total.cnt, 10),
        });
    } catch (err) {
        console.error('Leaderboard error:', err);
        res.status(500).json({ error: err.message });
    }
});

/**
 * GET /api/leaderboard/:userId — Single user's BR stats.
 */
router.get('/:userId', authenticate, async (req, res) => {
    try {
        const entry = await db('battle_royale_points')
            .where({ user_id: req.params.userId })
            .first();

        if (!entry) {
            return res.json({
                userId: req.params.userId,
                points: 0,
                wins: 0,
                losses: 0,
                tournamentsPlayed: 0,
                rank: null,
            });
        }

        // Calculate rank
        const rankResult = await db('battle_royale_points')
            .where('points', '>', entry.points)
            .count('id as cnt')
            .first();

        res.json({
            userId: entry.user_id,
            username: entry.username,
            points: entry.points,
            wins: entry.wins,
            losses: entry.losses,
            tournamentsPlayed: entry.tournaments_played,
            rank: parseInt(rankResult.cnt, 10) + 1,
        });
    } catch (err) {
        console.error('User stats error:', err);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
