CREATE TABLE `submissions` (
	`user_id` text PRIMARY KEY NOT NULL,
	`data` text DEFAULT '{}' NOT NULL,
	`markdown` text DEFAULT '' NOT NULL,
	`status` text DEFAULT 'draft' NOT NULL,
	`cv_key` text,
	`cv_name` text,
	`cv_size` integer,
	`updated_at` text NOT NULL
);
