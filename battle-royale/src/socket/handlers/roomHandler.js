/**
 * roomHandler.js — Socket handlers for joining / leaving a Battle Royale room.
 */

const tournamentService = require('../../services/tournamentService');
const redis = require('../../utils/redis');
const config = require('../../config');
const E = require('../events');

module.exports = function roomHandler(io, socket) {
    const user = socket.user;

    /**
     * royale:join  — Student joins a room using a code.
     * Payload: { code: string }
     */
    socket.on(E.ROYALE_JOIN, async ({ code }) => {
        try {
            // Prevent duplicate socket connections
            const existingSocket = await redis.get(`user:${user.userId}:socket`);
            if (existingSocket && existingSocket !== socket.id) {
                socket.emit(E.ERROR, { message: 'You are already connected from another session' });
                return;
            }

            const { royale, participant, playerCount } = await tournamentService.joinRoyale({
                code,
                user,
            });

            // Register socket → user mapping
            await redis.set(`user:${user.userId}:socket`, socket.id, 'EX', 7200);

            // Join socket rooms
            socket.join(`royale:${royale.id}`);
            socket.join(`user:${user.userId}`);
            socket.royaleId = royale.id;

            // Broadcast to room
            io.to(`royale:${royale.id}`).emit(E.ROYALE_PLAYER_JOINED, {
                user: { userId: user.userId, username: user.username },
                playerCount,
                maxPlayers: royale.max_players,
            });

            // Auto-start if room is full
            if (playerCount >= royale.max_players) {
                // Countdown
                let seconds = config.game.roundCountdown;
                const interval = setInterval(() => {
                    io.to(`royale:${royale.id}`).emit(E.ROYALE_COUNTDOWN, { seconds });
                    seconds--;
                    if (seconds < 0) {
                        clearInterval(interval);
                        tournamentService.startTournament(royale.id, io).catch((err) => {
                            io.to(`royale:${royale.id}`).emit(E.ERROR, { message: err.message });
                        });
                    }
                }, 1000);
            }
        } catch (err) {
            socket.emit(E.ERROR, { message: err.message });
        }
    });

    /**
     * royale:leave — Player voluntarily leaves the waiting room.
     */
    socket.on(E.ROYALE_LEAVE, async () => {
        try {
            if (socket.royaleId) {
                await redis.srem(`royale:${socket.royaleId}:players`, user.userId);
                await redis.hincrby(`royale:${socket.royaleId}:state`, 'playerCount', -1);
                await redis.del(`user:${user.userId}:socket`);

                const newCount = await redis.scard(`royale:${socket.royaleId}:players`);

                socket.leave(`royale:${socket.royaleId}`);
                io.to(`royale:${socket.royaleId}`).emit(E.ROYALE_PLAYER_LEFT, {
                    user: { userId: user.userId, username: user.username },
                    playerCount: newCount,
                });

                socket.royaleId = null;
            }
        } catch (err) {
            socket.emit(E.ERROR, { message: err.message });
        }
    });

    /**
     * Handle disconnection — clean up Redis state.
     */
    socket.on('disconnect', async () => {
        try {
            await redis.del(`user:${user.userId}:socket`);

            if (socket.royaleId) {
                await redis.srem(`royale:${socket.royaleId}:players`, user.userId);

                // Mark participant as disconnected
                const db = require('../../db/knex');
                await db('battle_royale_participants')
                    .where({ royale_id: socket.royaleId, user_id: user.userId })
                    .update({ is_connected: false });

                const newCount = await redis.scard(`royale:${socket.royaleId}:players`);
                io.to(`royale:${socket.royaleId}`).emit(E.ROYALE_PLAYER_LEFT, {
                    user: { userId: user.userId, username: user.username },
                    playerCount: newCount,
                    disconnected: true,
                });
            }
        } catch (err) {
            console.error('Disconnect cleanup error:', err.message);
        }
    });
};
