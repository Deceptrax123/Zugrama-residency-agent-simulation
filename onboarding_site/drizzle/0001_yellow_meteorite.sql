CREATE TABLE `cv_jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`cv_key` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`created_at` integer NOT NULL,
	`claimed_at` integer,
	`completed_at` integer,
	`lease_token` text,
	`result` text,
	`error` text,
	FOREIGN KEY (`owner_id`) REFERENCES `submissions`(`user_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `extraction_service` (
	`id` text PRIMARY KEY NOT NULL,
	`last_seen` integer NOT NULL,
	`model` text NOT NULL
);
