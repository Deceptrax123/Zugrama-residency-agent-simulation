CREATE TABLE `residency_commands` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`request_key` text NOT NULL,
	`kind` text NOT NULL,
	`payload` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`created_at` integer NOT NULL,
	`claimed_at` integer,
	`lease_token` text,
	`completed_at` integer,
	`result` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `residency_command_deduplication` ON `residency_commands` (`owner_id`,`request_key`);--> statement-breakpoint
CREATE TABLE `residency_snapshots` (
	`owner_id` text PRIMARY KEY NOT NULL,
	`data` text NOT NULL,
	`updated_at` integer NOT NULL
);
