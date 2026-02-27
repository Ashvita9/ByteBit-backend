/**
 * Socket event name constants — single source of truth.
 */
module.exports = {
    // Client → Server
    ROYALE_JOIN: 'royale:join',
    ROYALE_LEAVE: 'royale:leave',
    ROYALE_READY: 'royale:ready',
    MATCH_SUBMIT: 'match:submit',
    ADMIN_START: 'admin:start',
    ADMIN_KICK: 'admin:kick',

    // Server → Client
    ROYALE_PLAYER_JOINED: 'royale:player_joined',
    ROYALE_PLAYER_LEFT: 'royale:player_left',
    ROYALE_STARTING: 'royale:starting',
    ROYALE_COUNTDOWN: 'royale:countdown',
    MATCH_STARTED: 'match:started',
    MATCH_OPPONENT_PROGRESS: 'match:opponent_progress',
    MATCH_RESULT: 'match:result',
    MATCH_SUBMISSION_ACK: 'match:submission_ack',
    ROUND_ADVANCE: 'round:advance',
    TOURNAMENT_COMPLETE: 'tournament:complete',
    TOURNAMENT_ELIMINATED: 'tournament:eliminated',
    ERROR: 'error',
};
