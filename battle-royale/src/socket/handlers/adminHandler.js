/**
 * adminHandler.js — Socket handler for admin/teacher actions.
 */

const tournamentService = require('../../services/tournamentService');
const config = require('../../config');
const E = require('../events');

module.exports = function adminHandler(io, socket) {
    const user = socket.user;

    /**
     * admin:start — Force-start a tournament before room is full.
     * Only ADMIN or TEACHER who created the royale can start it.
     * Payload: { royaleId: string }
     */
    socket.on(E.ADMIN_START, async ({ royaleId }) => {
        try {
            if (!['ADMIN', 'TEACHER'].includes(user.role)) {
                socket.emit(E.ERROR, { message: 'Only admins and teachers can start tournaments' });
                return;
            }

            // Countdown before starting
            let seconds = config.game.roundCountdown;
            const interval = setInterval(() => {
                io.to(`royale:${royaleId}`).emit(E.ROYALE_COUNTDOWN, { seconds });
                seconds--;
                if (seconds < 0) {
                    clearInterval(interval);
                    tournamentService.startTournament(royaleId, io).catch((err) => {
                        socket.emit(E.ERROR, { message: err.message });
                    });
                }
            }, 1000);
        } catch (err) {
            socket.emit(E.ERROR, { message: err.message });
        }
    });

    /**
     * admin:kick — Kick a player from the waiting room.
     * Payload: { royaleId: string, userId: string }
     */
    socket.on(E.ADMIN_KICK, async ({ royaleId, userId }) => {
        try {
            if (!['ADMIN', 'TEACHER'].includes(user.role)) {
                socket.emit(E.ERROR, { message: 'Only admins and teachers can kick players' });
                return;
            }

            const redis = require('../../utils/redis');
            const db = require('../../db/knex');

            // Remove from DB
            await db('battle_royale_participants')
                .where({ royale_id: royaleId, user_id: userId })
                .del();

            // Remove from Redis
            await redis.srem(`royale:${royaleId}:players`, userId);
            await redis.hincrby(`royale:${royaleId}:state`, 'playerCount', -1);

            // Disconnect their socket
            const targetSocketId = await redis.get(`user:${userId}:socket`);
            if (targetSocketId) {
                const targetSocket = io.sockets.sockets.get(targetSocketId);
                if (targetSocket) {
                    targetSocket.emit(E.ERROR, { message: 'You have been removed from the tournament' });
                    targetSocket.leave(`royale:${royaleId}`);
                    targetSocket.royaleId = null;
                }
                await redis.del(`user:${userId}:socket`);
            }

            const newCount = await redis.scard(`royale:${royaleId}:players`);
            io.to(`royale:${royaleId}`).emit(E.ROYALE_PLAYER_LEFT, {
                user: { userId },
                playerCount: newCount,
                kicked: true,
            });
        } catch (err) {
            socket.emit(E.ERROR, { message: err.message });
        }
    });
};
