/**
 * bracketGenerator.js
 *
 * Generates a single-elimination tournament bracket.
 * Handles non-power-of-2 counts by assigning byes in round 1.
 */

/**
 * Shuffle an array in-place (Fisher-Yates).
 */
function shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
}

/**
 * Next power of 2 >= n.
 */
function nextPow2(n) {
    let p = 1;
    while (p < n) p <<= 1;
    return p;
}

/**
 * Build a bracket from a list of players.
 *
 * @param {Array<{userId: string, username: string}>} players
 * @returns {{ totalRounds: number, rounds: Array<Array<{matchIndex, player1, player2}>> }}
 *
 * - Players are randomly seeded.
 * - For non-power-of-2 counts, top-seeded players get byes (player2 = null).
 * - Each round halves the remaining players until the final.
 */
function generateBracket(players) {
    const shuffled = shuffle([...players]);
    const size = nextPow2(shuffled.length);
    const totalRounds = Math.log2(size);
    const byeCount = size - shuffled.length;

    // Round 1 pairings
    const round1 = [];
    let idx = 0;

    // Players with byes advance automatically
    for (let i = 0; i < byeCount; i++) {
        round1.push({
            matchIndex: idx++,
            player1: shuffled[i],
            player2: null,    // bye
        });
    }

    // Remaining players paired normally
    const remaining = shuffled.slice(byeCount);
    for (let i = 0; i < remaining.length; i += 2) {
        round1.push({
            matchIndex: idx++,
            player1: remaining[i],
            player2: remaining[i + 1] || null,
        });
    }

    // Build placeholder rounds (future rounds are empty until results come in)
    const rounds = [round1];
    let matchesInRound = Math.ceil(round1.length / 2);
    for (let r = 1; r < totalRounds; r++) {
        const roundSlots = [];
        for (let m = 0; m < matchesInRound; m++) {
            roundSlots.push({
                matchIndex: m,
                player1: null,
                player2: null,
            });
        }
        rounds.push(roundSlots);
        matchesInRound = Math.ceil(matchesInRound / 2);
    }

    return { totalRounds, rounds };
}

module.exports = { generateBracket, shuffle, nextPow2 };
