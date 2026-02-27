/**
 * routes/match.js — REST fallback for code submissions.
 */

const express = require('express');
const router = express.Router();
const { authenticate } = require('../middleware/auth');
const matchService = require('../services/matchService');

/**
 * POST /api/match/:id/submit — Submit a solution (REST fallback).
 * Body: { code, language? }
 * Auth: any authenticated student in the match
 */
router.post('/:id/submit', authenticate, async (req, res) => {
    try {
        const { code, language } = req.body;
        if (!code) {
            return res.status(400).json({ error: 'code is required' });
        }

        const io = req.app.get('io');
        const { submission, ack } = await matchService.submitSolution(
            {
                matchId: req.params.id,
                userId: req.user.userId,
                username: req.user.username,
                code,
                language: language || 'Python',
            },
            io,
        );

        res.json({
            message: 'Submission received',
            ...ack,
        });
    } catch (err) {
        if (err.message.includes('not found') || err.message.includes('not active') ||
            err.message.includes('not a participant') || err.message.includes('already submitted')) {
            return res.status(400).json({ error: err.message });
        }
        console.error('Match submit error:', err);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
