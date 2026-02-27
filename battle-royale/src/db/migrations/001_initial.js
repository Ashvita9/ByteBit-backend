/**
 * 001_initial.js — Creates all Battle Royale tables.
 */
exports.up = async function (knex) {

    // ── battle_royales ──────────────────────────────────────────────
    await knex.schema.createTable('battle_royales', (t) => {
        t.uuid('id').primary().defaultTo(knex.fn.uuid());
        t.string('code', 8).notNullable().unique();
        t.string('title', 200).notNullable();
        t.string('created_by').notNullable();          // user ID from Django
        t.string('creator_username').notNullable();
        t.string('creator_role').notNullable();         // ADMIN | TEACHER
        t.enum('difficulty', ['Easy', 'Medium', 'Hard']).notNullable().defaultTo('Easy');
        t.enum('type', ['public', 'private']).notNullable().defaultTo('private');
        t.enum('status', ['waiting', 'in_progress', 'completed', 'cancelled'])
            .notNullable().defaultTo('waiting');
        t.integer('max_players').notNullable().defaultTo(10);
        t.integer('current_round').notNullable().defaultTo(0);
        t.integer('total_rounds').notNullable().defaultTo(0);
        t.string('winner_id').nullable();
        t.string('winner_username').nullable();
        t.timestamp('started_at').nullable();
        t.timestamp('completed_at').nullable();
        t.timestamps(true, true);                       // created_at, updated_at
    });

    // ── battle_royale_participants ──────────────────────────────────
    await knex.schema.createTable('battle_royale_participants', (t) => {
        t.uuid('id').primary().defaultTo(knex.fn.uuid());
        t.uuid('royale_id').notNullable()
            .references('id').inTable('battle_royales').onDelete('CASCADE');
        t.string('user_id').notNullable();
        t.string('username').notNullable();
        t.string('role').notNullable().defaultTo('STUDENT');
        t.integer('eliminated_in_round').nullable();
        t.boolean('is_connected').notNullable().defaultTo(true);
        t.timestamp('joined_at').defaultTo(knex.fn.now());
        t.unique(['royale_id', 'user_id']);              // prevent duplicate join
    });

    // ── matches ─────────────────────────────────────────────────────
    await knex.schema.createTable('matches', (t) => {
        t.uuid('id').primary().defaultTo(knex.fn.uuid());
        t.uuid('royale_id').notNullable()
            .references('id').inTable('battle_royales').onDelete('CASCADE');
        t.integer('round_number').notNullable();
        t.integer('match_index').notNullable();          // position within round
        t.string('player1_id').nullable();
        t.string('player1_username').nullable();
        t.string('player2_id').nullable();               // null = bye
        t.string('player2_username').nullable();
        t.string('winner_id').nullable();
        t.string('winner_username').nullable();
        // Question data (snapshot so it stays immutable)
        t.string('question_id').nullable();
        t.string('question_title').nullable();
        t.text('question_description').nullable();
        t.jsonb('test_cases').nullable();                 // [{ input, output, is_hidden }]
        t.enum('status', ['pending', 'active', 'completed']).notNullable().defaultTo('pending');
        t.timestamp('started_at').nullable();
        t.timestamp('completed_at').nullable();
        t.unique(['royale_id', 'round_number', 'match_index']);
    });

    // ── submissions ─────────────────────────────────────────────────
    await knex.schema.createTable('submissions', (t) => {
        t.uuid('id').primary().defaultTo(knex.fn.uuid());
        t.uuid('match_id').notNullable()
            .references('id').inTable('matches').onDelete('CASCADE');
        t.string('user_id').notNullable();
        t.string('username').notNullable();
        t.text('code').notNullable();
        t.string('language', 30).notNullable().defaultTo('Python');
        t.boolean('passed').notNullable().defaultTo(false);
        t.text('output').nullable();
        t.integer('time_taken_ms').nullable();            // ms from match start
        t.string('time_complexity').nullable();            // AI evaluated
        t.timestamp('submitted_at').defaultTo(knex.fn.now());
        t.unique(['match_id', 'user_id']);                 // one valid submission per user per match
    });

    // ── battle_royale_points ────────────────────────────────────────
    await knex.schema.createTable('battle_royale_points', (t) => {
        t.uuid('id').primary().defaultTo(knex.fn.uuid());
        t.string('user_id').notNullable().unique();
        t.string('username').notNullable();
        t.integer('points').notNullable().defaultTo(0);
        t.integer('wins').notNullable().defaultTo(0);
        t.integer('losses').notNullable().defaultTo(0);
        t.integer('tournaments_played').notNullable().defaultTo(0);
        t.timestamp('updated_at').defaultTo(knex.fn.now());
    });
};

exports.down = async function (knex) {
    await knex.schema.dropTableIfExists('submissions');
    await knex.schema.dropTableIfExists('matches');
    await knex.schema.dropTableIfExists('battle_royale_participants');
    await knex.schema.dropTableIfExists('battle_royale_points');
    await knex.schema.dropTableIfExists('battle_royales');
};
