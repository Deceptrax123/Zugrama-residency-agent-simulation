CREATE TABLE `resident_access_keys` (
	`access_hash` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`owner_id`) REFERENCES `submissions`(`user_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `resident_recovery_codes` (
	`owner_id` text PRIMARY KEY NOT NULL,
	`code_hash` text NOT NULL,
	`created_at` integer NOT NULL,
	`expires_at` integer NOT NULL,
	`used_at` integer,
	FOREIGN KEY (`owner_id`) REFERENCES `submissions`(`user_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `resident_recovery_codes_code_hash_unique` ON `resident_recovery_codes` (`code_hash`);