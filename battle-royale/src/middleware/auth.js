const jwt = require('jsonwebtoken');
const config = require('../config');

/**
 * Express middleware — verifies the JWT from the Authorization header.
 * Attaches `req.user` with { userId, username, role }.
 */
function authenticate(req, res, next) {
    const header = req.headers.authorization;
    if (!header || !header.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Missing or malformed Authorization header' });
    }

    const token = header.split(' ')[1];

    try {
        const decoded = jwt.verify(token, config.jwt.secret, {
            algorithms: [config.jwt.algorithm],
        });

        // Django SimpleJWT puts user_id in the payload
        req.user = {
            userId: String(decoded.user_id),
            username: decoded.username || decoded.user_id,
            role: (decoded.role || 'STUDENT').toUpperCase(),
        };

        next();
    } catch (err) {
        return res.status(401).json({ error: 'Invalid or expired token' });
    }
}

module.exports = { authenticate };
