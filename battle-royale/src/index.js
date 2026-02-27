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
