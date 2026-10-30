import {sqliteTable,text,integer,uniqueIndex} from 'drizzle-orm/sqlite-core';
export const submissions=sqliteTable('submissions',{
 userId:text('user_id').primaryKey(),data:text('data').notNull().default('{}'),markdown:text('markdown').notNull().default(''),status:text('status').notNull().default('draft'),cvKey:text('cv_key'),cvName:text('cv_name'),cvSize:integer('cv_size'),updatedAt:text('updated_at').notNull(),
});
// Additional device capabilities resolve to the original submission; recovery
// never renames an owner or moves its profile, messages, memories or commands.
export const residentAccessKeys=sqliteTable('resident_access_keys',{
 accessHash:text('access_hash').primaryKey(),
 ownerId:text('owner_id').notNull().references(()=>submissions.userId,{onDelete:'cascade'}),
 createdAt:integer('created_at').notNull(),
});
export const residentRecoveryCodes=sqliteTable('resident_recovery_codes',{
 ownerId:text('owner_id').primaryKey().references(()=>submissions.userId,{onDelete:'cascade'}),
 codeHash:text('code_hash').notNull().unique(),
 createdAt:integer('created_at').notNull(),expiresAt:integer('expires_at').notNull(),usedAt:integer('used_at'),
});
export const cvJobs=sqliteTable('cv_jobs',{
 id:text('id').primaryKey(),
 ownerId:text('owner_id').notNull().references(()=>submissions.userId,{onDelete:'cascade'}),
 cvKey:text('cv_key').notNull(),
 status:text('status').notNull().default('queued'),
 createdAt:integer('created_at').notNull(),
 claimedAt:integer('claimed_at'),
 completedAt:integer('completed_at'),
 leaseToken:text('lease_token'),
 result:text('result'),
 error:text('error'),
});
export const extractionService=sqliteTable('extraction_service',{
 id:text('id').primaryKey(),lastSeen:integer('last_seen').notNull(),model:text('model').notNull(),
});
export const residencySnapshots=sqliteTable('residency_snapshots',{
 ownerId:text('owner_id').primaryKey(),data:text('data').notNull(),updatedAt:integer('updated_at').notNull(),
});
export const residencyCommands=sqliteTable('residency_commands',{
 id:text('id').primaryKey(),ownerId:text('owner_id').notNull(),requestKey:text('request_key').notNull(),kind:text('kind').notNull(),payload:text('payload').notNull(),
 status:text('status').notNull().default('queued'),createdAt:integer('created_at').notNull(),claimedAt:integer('claimed_at'),leaseToken:text('lease_token'),completedAt:integer('completed_at'),result:text('result'),
},table=>[uniqueIndex('residency_command_deduplication').on(table.ownerId,table.requestKey)]);
