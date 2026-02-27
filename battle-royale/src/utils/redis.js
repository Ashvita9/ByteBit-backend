const Redis = require('ioredis');
const config = require('../config');

const redis = new Redis(config.redisUrl, {
    maxRetriesPerRequest: 3,
    retryStrategy(times) {
        const delay = Math.min(times * 200, 3000);
        return delay;
    },
    lazyConnect: true,
});

redis.on('error', (err) => {
    console.error('❌ Redis error:', err.message);
});

redis.on('connect', () => {
    console.log('✅ Redis connected');
});

module.exports = redis;
