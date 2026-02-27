/**
 * socket/index.js — Socket.io initialization with JWT auth guard.
 */

const jwt = require('jsonwebtoken');
const config = require('../config');
const roomHandler = require('./handlers/roomHandler');
const matchHandler = require('./handlers/matchHandler');
const adminHandler = require('./handlers/adminHandler');

/**
 * Initialize Socket.io on the given HTTP server.
 */
function initSocket(httpServer) {
    const { Server } = require('socket.io');

    const io = new Server(httpServer, {
        cors: {
            origin: config.corsOrigin === '*' ? true : config.corsOrigin.split(','),
            methods: ['GET', 'POST'],
            credentials: true,
        },
        pingInterval: 25000,
        pingTimeout: 60000,
    });

    // ── JWT Authentication Middleware ──────────────────────────────
    io.use((socket, next) => {
        const token =
            socket.handshake.auth?.token ||
            socket.handshake.headers?.authorization?.split(' ')[1];

        if (!token) {
            return next(new Error('Authentication required'));
        }

        try {
            const decoded = jwt.verify(token, config.jwt.secret, {
                algorithms: [config.jwt.algorithm],
            });

            socket.user = {
                userId: String(decoded.user_id),
                username: decoded.username || decoded.user_id,
                role: (decoded.role || 'STUDENT').toUpperCase(),
            };

            next();
        } catch (err) {
            return next(new Error('Invalid token'));
        }
    });

    // ── Connection Handler ────────────────────────────────────────
    io.on('connection', (socket) => {
        console.log(`⚡ Socket connected: ${socket.user.username} (${socket.id})`);

        // Join personal room for targeted messages
        socket.join(`user:${socket.user.userId}`);

        // Register all handlers
        roomHandler(io, socket);
        matchHandler(io, socket);
        adminHandler(io, socket);
    });

    return io;
}

module.exports = { initSocket };
