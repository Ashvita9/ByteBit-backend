require('dotenv').config();

module.exports = {
    port: parseInt(process.env.PORT, 10) || 4000,
    nodeEnv: process.env.NODE_ENV || 'development',

    // PostgreSQL
    databaseUrl: process.env.DATABASE_URL || 'postgres://postgres:postgres@localhost:5432/bytebit_royale',

    // Redis
    redisUrl: process.env.REDIS_URL || 'redis://127.0.0.1:6379/2',

    // JWT  — must match the Django backend secret
    jwt: {
        secret: process.env.JWT_SECRET || 'django-insecure-smai)(%)s&v61xy(^e8jz%@5vg&2+g6(5yq%8_ciipy8k0ff@c',
        algorithm: process.env.JWT_ALGORITHM || 'HS256',
    },

    // Game defaults
    game: {
        defaultMaxPlayers: parseInt(process.env.DEFAULT_MAX_PLAYERS, 10) || 10,
        roundCountdown: parseInt(process.env.ROUND_COUNTDOWN_SECONDS, 10) || 5,
        matchTimeout: parseInt(process.env.MATCH_TIMEOUT_SECONDS, 10) || 600,
        codeExecTimeout: parseInt(process.env.CODE_EXECUTION_TIMEOUT_MS, 10) || 10000,
    },

    // CORS
    corsOrigin: process.env.CORS_ORIGIN || '*',
};
