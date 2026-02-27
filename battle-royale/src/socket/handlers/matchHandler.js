/**
 * matchHandler.js — Socket handler for code submissions during a match.
 */

const matchService = require('../../services/matchService');
const E = require('../events');

module.exports = function matchHandler(io, socket) {
    const user = socket.user;

    /**
     * match:submit — Player submits their code solution.
     * Payload: { matchId: string, code: string, language: string }
     */
    socket.on(E.MATCH_SUBMIT, async ({ matchId, code, language }) => {
        try {
            if (!matchId || !code) {
                socket.emit(E.ERROR, { message: 'matchId and code are required' });
                return;
            }

            const { ack } = await matchService.submitSolution(
                {
                    matchId,
                    userId: user.userId,
                    username: user.username,
                    code,
                    language: language || 'Python',
                },
                io,
            );

            // Send acknowledgment back to submitter
            socket.emit(E.MATCH_SUBMISSION_ACK, ack);
        } catch (err) {
            socket.emit(E.ERROR, { message: err.message });
        }
    });
};
