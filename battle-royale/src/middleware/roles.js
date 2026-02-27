/**
 * Role guard middleware factory.
 * Usage:  router.post('/royale', authenticate, requireRole('ADMIN','TEACHER'), handler)
 *
 * @param  {...string} allowedRoles
 * @returns {Function} Express middleware
 */
function requireRole(...allowedRoles) {
    return (req, res, next) => {
        if (!req.user) {
            return res.status(401).json({ error: 'Not authenticated' });
        }

        const userRole = (req.user.role || '').toUpperCase();

        if (!allowedRoles.map((r) => r.toUpperCase()).includes(userRole)) {
            return res.status(403).json({
                error: `Requires one of: ${allowedRoles.join(', ')}. You are: ${userRole}`,
            });
        }

        next();
    };
}

module.exports = { requireRole };
