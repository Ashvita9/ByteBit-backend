/**
 * index.js — Battle Royale server entry point.
 *
 * Express + Socket.io + PostgreSQL + Redis
 */

require('dotenv').config();

const http = require('http');
const express = require('express');
const cors = require('cors');
const config = require('./config');
const db = require('./db/knex');
const redis = require('./utils/redis');
const { initSocket } = require('./socket');

// ── Express App ─────────────────────────────────────────────────
const app = express();

app.use(cors({
    origin: config.corsOrigin === '*' ? true : config.corsOrigin.split(','),
    credentials: true,
}));
app.use(express.json());

// ── Health Check ────────────────────────────────────────────────
app.get('/health', async (req, res) => {
    try {
        await db.raw('SELECT 1');
        await redis.ping();
        res.json({
            status: 'healthy',
            service: 'battle-royale',
            uptime: process.uptime(),
            timestamp: new Date().toISOString(),
        });
    } catch (err) {
        res.status(503).json({
            status: 'unhealthy',
            error: err.message,
        });
    }
});

// ── REST Routes ─────────────────────────────────────────────────
const royaleRoutes = require('./routes/royale');
const matchRoutes = require('./routes/match');
const leaderboardRoutes = require('./routes/leaderboard');

app.use('/api/royale', royaleRoutes);
app.use('/api/match', matchRoutes);
app.use('/api/leaderboard', leaderboardRoutes);

// ── 404 fallback ────────────────────────────────────────────────
app.use((req, res) => {
    res.status(404).json({ error: 'Not found' });
});

// ── Error handler ───────────────────────────────────────────────
app.use((err, req, res, _next) => {
    console.error('Unhandled error:', err);
    res.status(500).json({ error: 'Internal server error' });
});

// ── HTTP + Socket.io Server ─────────────────────────────────────
const server = http.createServer(app);
const io = initSocket(server);
app.set('io', io);  // Make io accessible in routes

// ── Boot ────────────────────────────────────────────────────────
async function boot() {
    try {
        // Test PostgreSQL
        await db.raw('SELECT 1');
        console.log('✅ PostgreSQL connected');

        // Test Redis
        await redis.connect();
        console.log('✅ Redis connected');

        server.listen(config.port, () => {
            console.log(`\n🚀 Battle Royale server on port ${config.port}`);
            console.log(`   Environment: ${config.nodeEnv}`);
            console.log(`   Health: http://localhost:${config.port}/health\n`);
        });

        // Auto-start polling loop (runs every 5 seconds)
        const tournamentService = require('./services/tournamentService');
        setInterval(async () => {
            try {
                // Find tournaments that are waiting, have a start_time, and start_time <= now
                const toStart = await db('battle_royales')
                    .where('status', 'waiting')
                    .whereNotNull('start_time')
                    .where('start_time', '<=', db.fn.now());

                for (const royale of toStart) {
                    const participants = await db('battle_royale_participants')
                        .where({ royale_id: royale.id });
                    
                    if (participants.length >= 2) {
                        console.log(`auto-starting tournament ${royale.id} (${royale.title})`);
                        await tournamentService.startTournament(royale.id, io);
                    } else if (participants.length < 2) {
                        // If past start time and not enough players, maybe just cancel or wait?
                        // For now we do nothing, or we could extend start_time.
                        // We will delay the start time slightly to avoid spamming the DB or we cancel.
                        // Let's cancel it to keep it clean.
                        console.log(`cancelling tournament ${royale.id} due to insufficient players at start time`);
                        await db('battle_royales').where({ id: royale.id }).update({ status: 'cancelled' });
                        io.to(`royale:${royale.id}`).emit('tournament:cancelled', { reason: 'Not enough players to start.' });
                    }
                }
            } catch (err) {
                console.error('Auto-start polling error:', err);
            }
        }, 5000);

    } catch (err) {
        console.error('❌ Failed to start server:', err);
        process.exit(1);
    }
}

boot();

// ── Graceful Shutdown ───────────────────────────────────────────
process.on('SIGTERM', async () => {
    console.log('🛑 SIGTERM received — shutting down...');
    server.close();
    await redis.quit();
    await db.destroy();
    process.exit(0);
});

process.on('SIGINT', async () => {
    console.log('🛑 SIGINT received — shutting down...');
    server.close();
    await redis.quit();
    await db.destroy();
    process.exit(0);
});
