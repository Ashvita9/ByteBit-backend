const crypto = require('crypto');

/**
 * Generate a random alphanumeric room code.
 * @param {number} length – Code length (default 6)
 * @returns {string}
 */
function generateCode(length = 6) {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no O/0/1/I/l
    let code = '';
    const bytes = crypto.randomBytes(length);
    for (let i = 0; i < length; i++) {
        code += chars[bytes[i] % chars.length];
    }
    return code;
}

module.exports = { generateCode };
