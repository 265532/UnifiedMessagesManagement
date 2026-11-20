-- UnifiedMessagesManagement database design draft (MySQL 8)
-- This DDL is a confirmed design baseline for the preliminary submission, not proof that an implementation exists.

CREATE TABLE users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE platform_accounts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  platform VARCHAR(32) NOT NULL,
  account_name VARCHAR(128) NOT NULL,
  app_id VARCHAR(128) NOT NULL,
  encrypted_credentials TEXT NOT NULL,
  webhook_secret_ref VARCHAR(255) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'enabled',
  token_expires_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uk_platform_account (platform, account_name),
  KEY idx_platform_status (platform, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE conversations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  platform VARCHAR(32) NOT NULL,
  platform_conversation_id VARCHAR(128) NOT NULL,
  account_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(255) NULL,
  conversation_type VARCHAR(16) NOT NULL,
  last_message_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uk_platform_conversation (platform, platform_conversation_id),
  KEY idx_conversation_recent (platform, last_message_at DESC, id DESC),
  CONSTRAINT fk_conversations_account FOREIGN KEY (account_id) REFERENCES platform_accounts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE messages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  schema_version VARCHAR(16) NOT NULL,
  platform VARCHAR(32) NOT NULL,
  platform_event_id VARCHAR(191) NULL,
  platform_message_id VARCHAR(191) NULL,
  conversation_id BIGINT UNSIGNED NOT NULL,
  sender_platform_user_id VARCHAR(128) NOT NULL,
  sender_name VARCHAR(128) NULL,
  message_type VARCHAR(16) NOT NULL,
  content_text MEDIUMTEXT NULL,
  content_json JSON NULL,
  direction VARCHAR(16) NOT NULL,
  status VARCHAR(24) NOT NULL,
  reply_to_message_id BIGINT UNSIGNED NULL,
  client_request_id VARCHAR(128) NULL,
  version INT UNSIGNED NOT NULL DEFAULT 0,
  occurred_at DATETIME(6) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uk_inbound_event (platform, platform_event_id),
  UNIQUE KEY uk_reply_request (platform, conversation_id, client_request_id),
  KEY idx_message_list (platform, conversation_id, occurred_at DESC, id DESC),
  KEY idx_status_feedback (platform, conversation_id, status, updated_at DESC, id DESC),
  KEY idx_message_todo (message_type, status, occurred_at DESC),
  CONSTRAINT fk_messages_conversation FOREIGN KEY (conversation_id) REFERENCES conversations (id),
  CONSTRAINT fk_messages_reply_to FOREIGN KEY (reply_to_message_id) REFERENCES messages (id),
  CONSTRAINT chk_messages_direction CHECK (direction IN ('inbound', 'outbound')),
  CONSTRAINT chk_messages_type CHECK (message_type IN ('text', 'file', 'todo')),
  CONSTRAINT chk_messages_status CHECK (status IN ('received', 'stored', 'displayed', 'processed', 'replying', 'replied', 'confirmed', 'parse_failed', 'ignored', 'send_failed', 'dead'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE attachments (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  message_id BIGINT UNSIGNED NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  mime_type VARCHAR(128) NOT NULL,
  size_bytes BIGINT UNSIGNED NOT NULL,
  storage_path VARCHAR(512) NULL,
  platform_file_id VARCHAR(191) NULL,
  checksum_sha256 CHAR(64) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_attachments_message (message_id),
  CONSTRAINT fk_attachments_message FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE message_status_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  message_id BIGINT UNSIGNED NOT NULL,
  from_status VARCHAR(24) NULL,
  to_status VARCHAR(24) NOT NULL,
  reason VARCHAR(512) NULL,
  actor VARCHAR(64) NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_status_history_message (message_id, occurred_at),
  CONSTRAINT fk_status_history_message FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
  CONSTRAINT chk_history_to_status CHECK (to_status IN ('received', 'stored', 'displayed', 'processed', 'replying', 'replied', 'confirmed', 'parse_failed', 'ignored', 'send_failed', 'dead'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE outbox_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  aggregate_type VARCHAR(32) NOT NULL,
  aggregate_id BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  payload_json JSON NOT NULL,
  idempotency_key VARCHAR(191) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  attempts INT UNSIGNED NOT NULL DEFAULT 0,
  next_retry_at DATETIME(6) NULL,
  processed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uk_outbox_idempotency (idempotency_key),
  KEY idx_outbox_dispatch (status, next_retry_at, id),
  CONSTRAINT chk_outbox_status CHECK (status IN ('pending', 'sent', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
